from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
import json
from base58 import b58encode
from dataclasses import dataclass
from typing import Optional

from solders.hash import Hash
from solders.message import Message
from solana.rpc.types import TokenAccountOpts
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.solders import Signature
from solders.system_program import TransferParams, transfer
from spl.token.instructions import get_associated_token_address, create_idempotent_associated_token_account
from solders.instruction import Instruction
from spl.token.instructions import BurnParams, CloseAccountParams, burn, close_account

from spl.token.instructions import (
    TransferCheckedParams, transfer_checked,
)

from ..core.constants import MILLION
from .client import SolanaClient
from ..dto import WalletDTO
from ..enums import Role
from ..core.config import settings
from ..core.logger import logger
from ..core.constants import LAMPORTS_PER_SOL, SAVE_FEE_AMOUNT, TOKEN_PROGRAM_ID, TOKEN_PROGRAM_2022_ID

MAX_INSTRUCTIONS_PER_TRANSFER_TX = 9
MAX_INSTRUCTIONS_PER_CREATE_ATA_TX = 5
MAX_INSTRUCTIONS_PER_CLOSE_ATA_TX = 10
MAX_IX_PER_HIDE_SUPPLY = 30

@dataclass
class Wallet:
    """
    Represents a single wallet used in the system.
    """
    name: str
    group: Role
    pubkey: Pubkey
    keypair: Keypair
    ata_address: Optional[Pubkey] = None
    lamports_balance: int = 0
    token_balance: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "Wallet":
        return cls(
            group=Role(data["group"]),
            name=data["name"],
            pubkey=Pubkey.from_string(data["pubkey"]),
            keypair=Keypair.from_bytes(bytes(data["private_key"])),
        )

    @classmethod
    def from_export(cls, data: dict) -> "Wallet":
        return cls(
            group=Role(data["group"]),
            name=data["name"],
            pubkey=Pubkey.from_string(data["pubkey"]),
            keypair=Keypair.from_base58_string(data["private_key"]),
        )

    def to_dict(self) -> dict:
        return {
            "group": self.group.value,
            "name": self.name,
            "pubkey": str(self.pubkey),
            "private_key": list(self.keypair.to_bytes()),
            "private_base58": b58encode(self.keypair.to_bytes()).decode()
        }

    def to_export(self) -> dict:
        return {
            "group": self.group.value,
            "name": self.name,
            "pubkey": str(self.pubkey),
            "private_key": b58encode(self.keypair.to_bytes()).decode(),
            "balance": self.lamports_balance * LAMPORTS_PER_SOL
        }

    @classmethod
    def from_keypair(cls, kp: Keypair) -> "Wallet":
        return Wallet(
            keypair=kp,
            pubkey=kp.pubkey(),
            name=str(kp.pubkey())[:6],
            group=Role.group2,
        )

    def get_ata(self, mint: Pubkey, token_program = TOKEN_PROGRAM_ID) -> Pubkey:
        """
        Get associated token account address for this wallet and the given mint.
        """
        return get_associated_token_address(self.pubkey, mint, token_program_id=token_program)

    def to_wallet_dto(self) -> WalletDTO:
        return WalletDTO(
            address=str(self.pubkey),
            group=self.group,
            name=self.name,
            sol_balance=self.lamports_balance / LAMPORTS_PER_SOL,
            token_balance=self.token_balance,
        )

class WalletManager:
    """Manages all wallets in the system: balances, ATA, and group organization."""
    def __init__(
        self,
        solana_client: SolanaClient
    ) -> None:
        self.solana_client = solana_client
        self.wallets: list[Wallet] = []
        # init
        self.load_wallets()

    def load_wallets(self) -> None:
        """
        Load all wallets from filesystem and initialize Wallet objects.
        """
        self.wallets = []
        for path in settings.wallets_dir.glob("*.json"):
            with open(path) as f:
                data = json.load(f)
                self.wallets.append(Wallet.from_dict(data))

    def archive_wallet_by_pubkey(self, pubkey: Pubkey) -> bool:
        """
        Move wallet JSON from `wallets_dir` to `archive_wallets_dir` by pubkey.
        Returns True if success, False if not found.
        """
        pub_str = str(pubkey)
        source_file = settings.wallets_dir / f"{pub_str}.json"
        target_file = settings.archive_wallets_dir / f"{pub_str}.json"

        if not source_file.exists():
            logger.warning(f"Wallet file {source_file} not found for archiving.")
            return False

        settings.archive_wallets_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(source_file), str(target_file))
            self.wallets.remove(self.get_wallet_by_pubkey(pubkey))
            logger.info(f"Wallet {pubkey} archived successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to archive wallet {pubkey}: {e}")
            return False

    async def get_wallets_by_group(self, group: Role) -> list[Wallet]:
        """
        Return wallets belonging to a specific role/group.
        """
        return [w for w in self.wallets if w.group == group]

    def get_wallet_by_pubkey(self, pubkey: Pubkey) -> Optional[Wallet]:
        """
        Return wallet by public key.
        """
        return next((w for w in self.wallets if w.pubkey == pubkey), None)

    async def create_wallets(
        self,
        dev: bool = False,
        fund: bool = False,
        group1: Optional[int] = None,
        group2: Optional[int] = None
    ) -> list[WalletDTO]:
        """Create multiple wallets according to provided parameters."""
        created = []
        if dev:
            cr = await self._create_wallet(Role.dev)
            created.append(cr)
        if fund:
            cr = await self._create_wallet(Role.fund)
            created.append(cr)
        if group1:
            for _ in range(group1):
                cr = await self._create_wallet(Role.group1)
                created.append(cr)
        if group2:
            for _ in range(group2):
                cr = await self._create_wallet(Role.group2)
                created.append(cr)
        return created

    async def list_wallets_dto(self) -> list[WalletDTO]:
        return [w.to_wallet_dto() for w in self.wallets]

    async def withdraw_to_fund(self):
        fund_wallet = (await self.get_wallets_by_group(Role.fund))[0]
        all_wallets = [w for w in self.wallets if w.group != Role.fund]

        ixs: list[Instruction] = []
        signers: list[Keypair] = [fund_wallet.keypair]

        plan_for_log: dict[str, float] = {}
        for wallet in all_wallets:
            ixs.append(transfer(TransferParams(
                from_pubkey=wallet.pubkey,
                to_pubkey=fund_wallet.pubkey,
                lamports=wallet.lamports_balance,
            )))
            signers.append(wallet.keypair)
            plan_for_log[wallet.name] = wallet.lamports_balance / LAMPORTS_PER_SOL
        if not ixs:
            logger.warning("No lamports to withdraw to fund.")
            return {"success": False, "plan": None}

        all_success = True
        for i in range(0, len(ixs), MAX_INSTRUCTIONS_PER_TRANSFER_TX):
            chunk_ixs = ixs[i:i + MAX_INSTRUCTIONS_PER_TRANSFER_TX]
            chunk_signers = signers[:1] + signers[i + 1:i + 1 + MAX_INSTRUCTIONS_PER_TRANSFER_TX]
            try:
                sig, success = await self.solana_client.build_and_send_transaction(
                    instructions=chunk_ixs,
                    msg_signer=fund_wallet.keypair,
                    signers_keypairs=chunk_signers,
                    label="Sent withdrawal"
                )
                all_success = all_success and success
            except Exception as e:
                logger.error(f"Failed to send withdrawal TX: {e}")
                all_success = False

        if all_success:
            msg = "\n\n✅ WITHDRAWAL PLAN TO FUND:\n"
            for k, v in plan_for_log.items():
                msg += f"{k} -> Fund : {v:.4f} SOL\n"
            logger.info(msg)
            return {"success": True, "plan": plan_for_log}
        else:
            logger.error("🚨 Partial or full failure in withdraw_to_fund")
            return {"success": False, "plan": plan_for_log}

    async def distribute_from_fund(
        self,
        dev: float = 0,
        group1: float = 0,
        group2: float = 0,
    ):
        fund_wallet: Wallet = (await self.get_wallets_by_group(Role.fund))[0]
        distribution_plan = await self._build_distribution_plan({
            Role.dev: dev,
            Role.group1: group1,
            Role.group2: group2,
        })
        if not distribution_plan:
            logger.warning("Empty distribution plan.")
            return {"success": False, "plan": None}
        ixs, signers, plan_for_log = self._build_transfer_instructions(
            sender=fund_wallet,
            plan=distribution_plan
        )
        all_success = True
        for i in range(0, len(ixs), MAX_INSTRUCTIONS_PER_TRANSFER_TX):
            chunk_ixs = ixs[i:i + MAX_INSTRUCTIONS_PER_TRANSFER_TX]
            chunk_signers = signers[:1] + signers[i + 1:i + 1 + MAX_INSTRUCTIONS_PER_TRANSFER_TX]
            try:
                sig, success = await self.solana_client.build_and_send_transaction(
                    instructions=chunk_ixs,
                    msg_signer=fund_wallet.keypair,
                    max_retries=5,
                    max_confirm_retries=10,
                    signers_keypairs=chunk_signers,
                    label="Sent distribute"
                )
                all_success = all_success and success
            except Exception as e:
                logger.error(f"Failed to send distribute TX: {e}")
                all_success = False

        if all_success:
            msg = "\n\n✅ PLAN FOR DISTRIBUTE:\n"
            for k, v in plan_for_log.items():
                msg += f"Fund -> {k} : {v:.4f} SOL\n"
            logger.info(msg)
            return {"success": True, "plan": plan_for_log}
        else:
            logger.error("🚨 Partial or full failure in distribute_from_fund")
            return {"success": False, "plan": plan_for_log}

    async def _build_distribution_plan(self, amounts: dict[Role, float]) -> dict[str, int]:
        """
        Return a plan: Wallet → lamports to send.
        """
        plan: dict[str, int] = {}
        for role, total_amount in amounts.items():
            if total_amount <= 0:
                continue
            wallets = await self.get_wallets_by_group(role)
            if not wallets:
                continue
            per_wallet = (total_amount * LAMPORTS_PER_SOL) / len(wallets)
            for wlt in wallets:
                have = wlt.lamports_balance
                if have < per_wallet + SAVE_FEE_AMOUNT:
                    logger.warning(f"💰 Not enough lamports for wallet {wlt.name}")
                plan[str(wlt.pubkey)] = int(per_wallet)
        return plan

    def _build_transfer_instructions(
        self,
        sender: Wallet,
        plan: dict[str, int],
    ) -> tuple[
        list[Instruction],
        list[Keypair],
        dict[str, float]
    ]:
        ixs: list[Instruction] = []
        signers: list[Keypair] = [sender.keypair]
        plan_for_log: dict[str, float] = {}
        for pubkey, lamports in plan.items():
            wallet = self.get_wallet_by_pubkey(Pubkey.from_string(pubkey))
            ixs.append(transfer(TransferParams(
                from_pubkey=sender.pubkey,
                to_pubkey=wallet.pubkey,
                lamports=lamports,
            )))
            signers.append(wallet.keypair)
            plan_for_log[wallet.name] = lamports / LAMPORTS_PER_SOL
        return ixs, signers, plan_for_log

    @staticmethod
    async def _create_wallet(role: Role) -> WalletDTO:
        """Create a wallet and store its keys and group."""
        kp = Keypair()
        pub = kp.pubkey()
        filepath = settings.wallets_dir / f"{kp.pubkey()}.json"
        wallet = Wallet(
            name=str(pub)[:6],
            group=role,
            pubkey=pub,
            keypair=kp,
        )
        with open(filepath, "w") as f:
            json.dump(wallet.to_dict(), f, indent=2)

        return wallet.to_wallet_dto()

    async def create_ata_accounts(
        self,
        wallets: list[Wallet],
        mint: Pubkey,
        max_per_tx = MAX_INSTRUCTIONS_PER_CREATE_ATA_TX,
    ):
        ata_ixs = []
        for w in wallets:
            ix = create_idempotent_associated_token_account(
                payer=w.pubkey,
                owner=w.pubkey,
                mint=mint,
            )
            ata_ixs.append(ix)
            w.ata_address = w.get_ata(mint)
        success = False
        for i in range(0, len(ata_ixs), max_per_tx):
            signers = [w.keypair for w in wallets]
            signers_batch = signers[i:i + max_per_tx]
            try:
                sig, success = await self.solana_client.build_and_send_transaction(
                    instructions=ata_ixs[i:i + max_per_tx],
                    msg_signer=signers_batch[0],
                    signers_keypairs=signers_batch,
                    label="Sent Create ATA"
                )
            except Exception as e:
                logger.error(f"Failed to Sent Create ATA tx: {e}")

        return {"success": success}

    async def close_all_ata_accounts(
        self,
        max_per_tx=MAX_INSTRUCTIONS_PER_CLOSE_ATA_TX,
    ):
        current_ixs: list[Instruction] = []
        current_signers: set[Keypair] = set()
        success = False

        for w in self.wallets:
            try:
                client = await self.solana_client.get_client()

                token_accounts = await client.get_token_accounts_by_owner_json_parsed(
                    w.pubkey,
                    TokenAccountOpts(
                        encoding='jsonParsed',
                        program_id=TOKEN_PROGRAM_ID
                    )
                )
                token_accounts_2022 = await client.get_token_accounts_by_owner_json_parsed(
                    w.pubkey,
                    TokenAccountOpts(
                        encoding='jsonParsed',
                        program_id=TOKEN_PROGRAM_2022_ID
                    )
                )
                mints_program_map = {
                    TOKEN_PROGRAM_ID: token_accounts.value,
                    TOKEN_PROGRAM_2022_ID: token_accounts_2022.value,
                }
            except Exception as e:
                logger.error(f"Failed to fetch token accounts for {w.name}: {e}")
                continue

            for program_id, accounts in mints_program_map.items():
                for ata_info in accounts:
                    try:
                        ata_pubkey = ata_info.pubkey
                        info = ata_info.account.data.parsed["info"]
                        mint = Pubkey.from_string(info["mint"])
                        amount = int(info["tokenAmount"]["amount"])

                        logger.info(f"{ata_pubkey=}\n{ata_info=}\n{str(mint)=}\n{amount=}")

                        if amount > 0:
                            logger.info(f"Burning {amount} from {w.name} ({ata_pubkey})")
                            burn_ix = burn(BurnParams(
                                account=ata_pubkey,
                                mint=mint,
                                owner=w.pubkey,
                                amount=amount,
                                program_id=program_id,
                            ))
                            current_ixs.append(burn_ix)

                        logger.info(f"Closing ATA {ata_pubkey} for {w.name}")
                        close_ix = close_account(CloseAccountParams(
                            account=ata_pubkey,
                            dest=w.pubkey,
                            owner=w.pubkey,
                            program_id=program_id,
                        ))
                        current_ixs.append(close_ix)
                        current_signers.add(w.keypair)

                        if len(current_ixs) >= max_per_tx:
                            try:
                                sig, success = await self.solana_client.build_and_send_transaction(
                                    instructions=current_ixs[:max_per_tx],
                                    msg_signer=next(iter(current_signers)),
                                    signers_keypairs=list(current_signers),
                                    label="Sent CLOSE ATA",
                                    max_retries=1,
                                    max_confirm_retries=0,
                                )
                            except Exception as e:
                                logger.error(f"Failed to send CLOSE ATA tx: {e}")
                            current_ixs = []
                            current_signers = set()
                    except Exception as e:
                        logger.error(f"Parsing/token op failed for wallet {w.name}: {e}")
                        continue
        if current_ixs:
            try:
                sig, success = await self.solana_client.build_and_send_transaction(
                    instructions=current_ixs,
                    msg_signer=next(iter(current_signers)),
                    signers_keypairs=list(current_signers),
                    label="Sent CLOSE ATA",
                    max_retries=1,
                    max_confirm_retries=0,
                )
            except Exception as e:
                logger.error(f"Failed to send CLOSE ATA tx: {e}")

        return {"success": success}

    @staticmethod
    async def _create_temp_wallet() -> Wallet:
        """
        Создаёт временный (archive) кошелёк и сразу пишет его JSON
        в settings.archive_wallets_dir. Возвращает объект Wallet.
        """
        kp = Keypair()
        pub = kp.pubkey()
        w = Wallet(
            name=str(pub)[:6],
            group=Role.group1,
            pubkey=pub,
            keypair=kp,
        )
        path: Path = settings.temp_wallets_dir / f"{pub}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump(w.to_dict(), f, indent=2)
        return w

    async def distribute_via_chain(
        self,
        transfers: dict[str, float],          # pubkey -> amount SOL
        *,
        fee_lamports: int = 5_000,            # «стандартная» комиссия одной TX
    ) -> dict:
        """
        Для каждого назначения:
          • создаёт 3 временных кошелька (`Role.archive`);
          • прогоняет сумму через 4 последовательные транзакции
            fund → tmp1 → tmp2 → tmp3 → destination,
            добавляя fee_lamports к каждому промежуточному переводу так,
            чтобы у tmp-кошельков хватило на комиссию своей исходящей TX;
          • подтверждает каждую транзакцию.

        Возвращает
        {
            "success": bool,                   # true если все TX всех адресов ok
            "plan": {
                <dest_pubkey>: {
                    "amount_sol": float,       # целевая сумма (без комиссий)
                    "path": [tmp1, tmp2, tmp3],
                    "signatures": [sig1, sig2, sig3, sig4]
                },
                ...
            }
        }
        """
        fund_wallet: Wallet = (await self.get_wallets_by_group(Role.fund))[0]
        overall_ok = True
        report: dict[str, dict] = {}

        for dest_str, amount_sol in transfers.items():
            try:
                base_amount = int(amount_sol * LAMPORTS_PER_SOL)
                dest_pubkey = Pubkey.from_string(dest_str)
                dest_wallet = self.get_wallet_by_pubkey(dest_pubkey)

                tmp_wallets: list[Wallet] = [await self._create_temp_wallet()
                                             for _ in range(3)]

                hops: list[tuple[Wallet, Wallet]] = [
                    (fund_wallet,      tmp_wallets[0]),
                    (tmp_wallets[0],   tmp_wallets[1]),
                    (tmp_wallets[1],   tmp_wallets[2]),
                    (tmp_wallets[2],   dest_wallet),
                ]

                amounts: list[int] = []
                total_hops = len(hops)                         # = 4
                for i in range(total_hops):
                    downstream = total_hops - i - 1            # 3,2,1,0
                    amounts.append(base_amount + downstream * fee_lamports)

                sigs: list[Signature] = []
                for (sender, receiver), lamports in zip(hops, amounts):
                    to_pub = receiver.pubkey
                    ix = transfer(TransferParams(
                        from_pubkey=sender.pubkey,
                        to_pubkey=to_pub,
                        lamports=lamports,
                    ))

                    sig, ok = await self.solana_client.build_and_send_transaction(
                        instructions=[ix],
                        msg_signer=sender.keypair,
                        signers_keypairs=[sender.keypair],
                        max_retries=5,
                        max_confirm_retries=10,
                    )
                    logger.info(f"TX {sig}  {sender.name} → {receiver.name} amount:{lamports / LAMPORTS_PER_SOL} OK={ok}")
                    overall_ok &= ok
                    sigs.append(sig)

                report[dest_str] = {
                    "amount_sol": float(amount_sol),
                    "path": [str(w.pubkey) for w in tmp_wallets],
                    "signatures": [str(s) for s in sigs],
                }

            except Exception as exc:
                overall_ok = False
                logger.error(f"distribute_via_chain failed for {dest_str}: {exc}")
                report[dest_str] = {"error": str(exc)}


        logger.info(f"success: {overall_ok}, plan: {report}")
        return {"success": overall_ok, "plan": report}

    @staticmethod
    def _gross_net_for_target_net(
        target_net: int,
        fee_bps: int,
        *,
        max_gross: int | None = None,
        max_fee: int | None = None,
    ) -> list[int]:
        """
        Строит план полных хопов (dev->tmp->...->dev), пока net после хопа не станет <= target_net.
        Возвращает список gross-сумм для КАЖДОГО хопа.
        Требование непрерывности цепочки соблюдается: gross[i+1] == net(gross[i]).

        Параметры:
          target_net — целевой net после ПОСЛЕДНЕГО хопа (<= target_net).
          fee_bps    — комиссия в б.п. (0..10000).
          max_gross  — исходный доступный баланс источника для первого хопа (обязателен для плана).

        Возвращает:
          list[int] gross_list — список сумм, которые надо отправить по порядку.

        Примечания:
          * Здесь НЕТ частичных «подгоночных» отправок — только полные переливы.
          * Если fee_bps == 0 — достаточно одного хопа с gross = min(max_gross, target_net).
          * Если max_gross не задан или <= 0 — план пуст.
        """
        if target_net <= 0:
            return []
        if max_gross is None or max_gross <= 0:
            return []
        if fee_bps < 0 or fee_bps > 100_000:
            raise ValueError("fee_bps out of range")

        if fee_bps == 0:
            g = min(max_gross, target_net)
            return [g] if g > 0 else []

        gross_list: list[int] = []
        g = int(max_gross)
        hop = 0
        MAX_HOPS = 100

        while g > 0 and hop < MAX_HOPS:
            hop += 1
            fee = (g * fee_bps) // 10_000
            fee = int(fee if (max_fee == 0 or fee <= max_fee) else max_fee)
            net = g - fee
            if net < 0:
                net = 0

            if net <= target_net or net == 0:
                break
            gross_list.append(g)

            g = net

        if hop >= MAX_HOPS:
            raise RuntimeError("too many hops (guard)")

        for i in range(len(gross_list) - 1):
            gi = gross_list[i]
            fee_i = (gi * fee_bps) // 10_000
            net_i = gi - fee_i
            if gross_list[i + 1] != net_i:
                raise AssertionError(
                    f"chain continuity violated at hop {i + 1}: "
                    f"expected next gross {net_i}, got {gross_list[i + 1]}"
                )

        return gross_list

    async def hide_supply(
        self,
        dev_wallet: Wallet,
        initial_supply_ui: int,
        mint: Pubkey,
        amount_after: float,
        *,
        max_hops_limit: int = 100,
    ) -> dict:

        PACKET_LIMIT = 1232

        logger.info("hide_supply: start")

        def fee_of(g: int, bps: int, _fee_max: int) -> int:
            f = (g * bps) // 10_000
            return f if (fee_max == 0 or f <= _fee_max) else fee_max

        def net_of(g: int, bps: int, _fee_max: int) -> int:
            return g - fee_of(g, bps, _fee_max)

        def est_size(payer: Pubkey, ixs: list[Instruction], signer_cnt: int) -> int:
            msg = Message.new_with_blockhash(ixs, payer, Hash.default())
            return len(bytes(msg)) + 1 + 64 * max(1, signer_cnt)

        batch_ixs: list[Instruction] = []
        batch_signers: set[Keypair] = set()
        sigs: list[str] = []

        async def flush(label: str):
            nonlocal batch_ixs, batch_signers, sigs
            if not batch_ixs:
                return
            all_signers = list({*batch_signers, dev_wallet.keypair})

            try:
                sig, _ok = await self.solana_client.build_and_send_transaction(
                    instructions=batch_ixs,
                    msg_signer=dev_wallet.keypair,
                    signers_keypairs=all_signers,
                    label=label,
                    max_retries=1,
                    max_confirm_retries=10,
                )
            except Exception as e:
                logger.error(f"Error while sending hide_supply TX: {e}")
                sig = ""
            sigs.append(str(sig))
            batch_ixs.clear()
            batch_signers.clear()

        async def push(ix: Instruction, signers: set[Keypair], label: str):
            new_ixs = batch_ixs + [ix]
            new_sigs = set(batch_signers) | set(signers) | {dev_wallet.keypair}
            if est_size(dev_wallet.pubkey, new_ixs, len(new_sigs)) > PACKET_LIMIT:
                await flush(label)
                batch_ixs.append(ix)
                batch_signers.update(signers)
            else:
                batch_ixs.append(ix)
                batch_signers.update(signers)

        try:
            client = await self.solana_client.get_client()
            mint_acc = await client.get_account_info_json_parsed(mint)
            if mint_acc.value is None:
                return {"success": False, "error": "mint account not found"}

            if mint_acc.value.owner != TOKEN_PROGRAM_2022_ID:
                return {"success": False, "error": "only Token-2022 supported"}

            info = mint_acc.value.data.parsed["info"]
            decimals = int(info["decimals"])
            extensions = info.get("extensions", [])

            fee_bps = 0
            fee_max = 0
            for ext in extensions:
                if ext.get("extension") == "transferFeeConfig":
                    st = ext.get("state", {})
                    newer = st.get("newerTransferFee", {})
                    fee_max = int(newer.get("maximumFee"))
                    fee_bps = int(newer.get("transferFeeBasisPoints"))
                    break
            if fee_bps <= 0:
                return {"success": False, "error": "transfer fee is not enabled on mint"}
        except Exception as e:
            return {"success": False, "error": f"rpc error: {e}"}

        program_id = TOKEN_PROGRAM_2022_ID
        supply_machine = int(initial_supply_ui * MILLION * (10 ** decimals))
        target_machine = int(amount_after * MILLION * (10 ** decimals))
        if target_machine <= 0 or target_machine > supply_machine:
            return {"success": False, "error": "target out of range"}

        hops: list[int] = self._gross_net_for_target_net(
            target_machine, fee_bps, max_gross=supply_machine, max_fee=fee_max
        )
        if not hops:
            return {"success": False, "error": "planning failed: empty hops"}

        dev_ata = dev_wallet.get_ata(mint, token_program=program_id)

        src_w = dev_wallet
        src_ata = dev_ata

        for i, gross in enumerate(hops):
            is_last = (i == len(hops) - 1)
            print(f"I = {i}, lenhops= {len(hops) - 1}")

            if not is_last:
                tmp_w = await self._create_temp_wallet()
                tmp_ata = get_associated_token_address(tmp_w.pubkey, mint, program_id)

                await push(
                    create_idempotent_associated_token_account(
                        payer=dev_wallet.pubkey,
                        owner=tmp_w.pubkey,
                        mint=mint,
                        token_program_id=program_id,
                    ),
                    signers={dev_wallet.keypair},
                    label="create ATA",
                )

                await push(
                    transfer_checked(
                        TransferCheckedParams(
                            program_id=program_id,
                            source=src_ata,
                            mint=mint,
                            dest=tmp_ata,
                            owner=src_w.pubkey,
                            amount=int(gross),
                            decimals=decimals,
                        )
                    ),
                    signers={src_w.keypair},
                    label=f"transfer hop {i + 1}",
                )
                src_w, src_ata = tmp_w, tmp_ata
            else:
                await push(
                    transfer_checked(
                        TransferCheckedParams(
                            program_id=program_id,
                            source=src_ata,
                            mint=mint,
                            dest=dev_ata,
                            owner=src_w.pubkey,
                            amount=int(gross),
                            decimals=decimals,
                        )
                    ),
                    signers={src_w.keypair},
                    label=f"transfer hop {i + 1} (to dev)",
                )
        last_net = net_of(hops[-1], fee_bps, fee_max)
        burn_delta = max(0, last_net - target_machine)
        if burn_delta > 0:
            await push(
                burn(
                    BurnParams(
                        program_id=program_id,
                        account=dev_ata,
                        mint=mint,
                        owner=dev_wallet.pubkey,
                        amount=int(burn_delta),
                    )
                ),
                signers={dev_wallet.keypair},
                label="burn delta to target",
            )

        await flush("final")

        return {
            "success": True,
            "hops_count": len(hops),
            "last_net": int(last_net),
            "target": int(target_machine),
            "burn_delta": int(burn_delta),
            "tx_signatures": sigs,
        }