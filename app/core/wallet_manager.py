from __future__ import annotations

import asyncio
import base58

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import transfer, TransferParams
from spl.token.instructions import get_associated_token_address, create_idempotent_associated_token_account

from .client import SolanaClient
from .constants import SOL_WRAPPED_MINT

load_dotenv(override=False)

WALLETS_DIR_DEFAULT = os.getenv("WALLETS_DIR", "wallets")
FUND_PRIVATE_KEY_ENV = os.getenv("FUND_PRIVATE_KEY")

@dataclass
class DevWallet:
    keypair: Keypair

class WalletManager:
    """
    Управление фондом и dev-кошельком.
    - Фонд: приватник берём из .env (FUND_PRIVATE_KEY)
    - Dev: создаём при инициализации и через update_dev()
    - Любой созданный ключ сохраняем в wallets/{PUBKEY}.txt (внутри — base58 secret)
    - Переводы:
        * distribute_lamports(lamports): Фонд → Dev
        * withdraw_to_fund(lamports=None): Dev → Фонд (если None — весь баланс, можно оставить пыль keep_rent_lamports)
    - После цикла:
        * rollover_dev(seed_lamports): Dev→Fund → create new Dev → Fund→NewDev(seed)
    """
    def __init__(self, client: SolanaClient, wallets_dir: str = WALLETS_DIR_DEFAULT):
        if not FUND_PRIVATE_KEY_ENV:
            raise RuntimeError("FUND_PRIVATE_KEY not set in .env")

        self.client = client
        self.wallets_dir = wallets_dir
        os.makedirs(self.wallets_dir, exist_ok=True)

        self._fund = Keypair.from_base58_string(FUND_PRIVATE_KEY_ENV)
        self._persist_wallet(self._fund)

        self._dev = self._create_dev()

        self._dev_lock = asyncio.Lock()

    @property
    def fund(self) -> Keypair:
        return self._fund

    @property
    def fund_pubkey(self) -> Pubkey:
        return self._fund.pubkey()

    @property
    def dev(self) -> Keypair:
        return self._dev.keypair

    @property
    def dev_pubkey(self) -> Pubkey:
        return self._dev.keypair.pubkey()

    async def _distribute_lamports_unlocked(self, lamports: int) -> str:
        if lamports <= 0:
            raise ValueError("lamports must be > 0")
        ix = transfer(TransferParams(
            from_pubkey=self.fund_pubkey,
            to_pubkey=self.dev_pubkey,
            lamports=lamports
        ))
        sig, _ = await self.client.build_and_send_transaction(
            instructions=[ix],
            msg_signer=self._fund,
            signers_keypairs=[self._fund],
            max_retries=1,
            max_confirm_retries=10,
            label="FUND -> DEV",
            priority_fee=10_000,
        )
        return str(sig)

    async def _withdraw_to_fund_unlocked(
        self,
        lamports: Optional[int] = None,
        *,
        from_dev: Optional[Keypair] = None,
        wait_if_zero: bool = True,
    ) -> str:
        dev_kp = from_dev or self._dev.keypair
        dev_pk = dev_kp.pubkey()

        bal = (await self.client.get_multiple_accounts_lamports_balances([dev_pk]))[0]
        if bal == 0 and wait_if_zero:
            bal = await self._wait_nonzero_balance(dev_pk)

        amount = lamports if lamports is not None else max(0, bal)
        if amount <= 0:
            raise RuntimeError(f"Nothing to withdraw from dev wallet: {str(dev_pk)}")

        ix = transfer(TransferParams(from_pubkey=dev_pk, to_pubkey=self.fund_pubkey, lamports=amount))
        sig, _ = await self.client.build_and_send_transaction(
            instructions=[ix],
            msg_signer=self._fund,
            signers_keypairs=[self._fund, dev_kp],
            max_retries=1,
            max_confirm_retries=10,
            label="DEV -> FUND",
            priority_fee=10_000,
        )
        return str(sig)

    async def distribute_lamports(self, lamports: int) -> str:
        async with self._dev_lock:
            return await self._distribute_lamports_unlocked(lamports)

    async def withdraw_to_fund(
        self,
        lamports: Optional[int] = None,
        from_dev: Optional[Keypair] = None,
        wait_if_zero: bool = True,
    ) -> str:
        async with self._dev_lock:
            return await self._withdraw_to_fund_unlocked(
                lamports=lamports,
                from_dev=from_dev,
                wait_if_zero=wait_if_zero,
            )

    async def _wait_nonzero_balance(
        self,
        pubkey: Pubkey,
        *,
        min_lamports: int = 1,
        timeout_sec: float = 5.0,
        poll_interval: float = 1.0,
    ) -> int:

        deadline = asyncio.get_running_loop().time() + timeout_sec
        last = 0
        while asyncio.get_running_loop().time() < deadline:
            bal = (await self.client.get_multiple_accounts_lamports_balances([pubkey]))[0]
            last = bal
            if bal >= min_lamports:
                return bal
            await asyncio.sleep(poll_interval)
        return last

    def update_dev(self) -> Keypair:
        self._dev = self._create_dev()
        return self._dev.keypair

    async def rollover_dev(
            self, seed_lamports: int, *, from_dev: Optional[Keypair] = None
    ) -> tuple[str, str]:
        old_dev = from_dev or self._dev.keypair
        async with self._dev_lock:
            #sig1 = await self._withdraw_to_fund_unlocked(from_dev=old_dev)
            self.update_dev()
            sig2 = await self._distribute_lamports_unlocked(seed_lamports)
            return "", sig2

    class _DevCycleCtx:
        def __init__(self, wm: "WalletManager"):
            self.wm = wm
            self.dev_snapshot: Optional[Keypair] = None

        async def __aenter__(self):
            await self.wm._dev_lock.acquire()
            self.dev_snapshot = self.wm._dev.keypair
            return self.dev_snapshot

        async def __aexit__(self, exc_type, exc, tb):
            self.wm._dev_lock.release()

    def dev_cycle(self) -> "_DevCycleCtx":
        return WalletManager._DevCycleCtx(self)

    @staticmethod
    def get_wsol_ata(owner: Pubkey) -> Pubkey:
        return get_associated_token_address(owner=owner, mint=SOL_WRAPPED_MINT)

    @staticmethod
    def build_create_wsol_ata_ix(payer: Pubkey):
        return create_idempotent_associated_token_account(payer=payer, owner=payer, mint=SOL_WRAPPED_MINT)

    def _create_dev(self) -> DevWallet:
        kp = Keypair()
        self._persist_wallet(kp)
        return DevWallet(keypair=kp)

    def _persist_wallet(self, kp: Keypair) -> None:
        try:
            secret_b58 = base58.b58encode(kp.to_bytes()).decode()
        except AttributeError as e:
            raise RuntimeError(e)

        path = os.path.join(self.wallets_dir, f"{kp.pubkey()}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(secret_b58)
