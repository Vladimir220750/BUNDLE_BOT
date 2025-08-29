# app/core/bablo.py
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

import httpx
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import transfer, TransferParams, create_account, CreateAccountParams
from solders.instruction import Instruction
from spl.token.instructions import (
    create_associated_token_account,
    create_idempotent_associated_token_account,
    get_associated_token_address,
    mint_to_checked, MintToCheckedParams,
    set_authority, SetAuthorityParams, AuthorityType,
    sync_native, SyncNativeParams, close_account, CloseAccountParams
)
from .dto import TokenDTO, LiquidityPoolData
from .client import SolanaClient
from .constants import (
    TOKEN_DECIMALS, TOKEN_WITH_DECIMALS,
    TOKEN_PROGRAM_2022_ID,
    TOKEN_PROGRAM_ID,
    SOL_WRAPPED_MINT,
    LAMPORTS_PER_SOL,
    MILLION,
    RAYDIUM_CP_PROGRAM_ID, HELIUS_HTTPS
)
from .ix_builders import (
    build_initialize_transfer_fee_config_ix,
    build_initialize_metadata_pointer_ix,
    build_initialize_mint_ix,
    build_initialize_token_metadata_ix,
    build_initialize_pool_ix,
    build_withdraw_ix,
)
from .ws_hub import WsHub
from .utils import (
    sol_to_lamports,
    lamports_to_sol,
    tokens_base_units_to_ui,
    tokens_ui_to_base_units,
    calculate_lp_tokens,
    get_token_amount_after_fee,
    get_amm_config_address,
    get_pool_address,
    get_authority_address,
    get_pool_vault_address,
    get_oracle_account_address,
    get_pool_lp_mint_address,
    get_creator_lp_mint
)

@dataclass
class BabloConfig:
    token_amount_ui: list[int]
    wsol_amount_ui: list[float]
    profit_threshold_sol: float = 0.05
    cycle_timeout_sec: int = 120
    mode: str = "manual"

OnStatus = Callable[[str], Awaitable[None]]
OnAlert = Callable[[str], Awaitable[None]]
GetCA = Callable[[], Awaitable[str]]

CREATE_MINT_ACCOUNT_LAMPORTS = 5_066_880
CREATE_MINT_ACCOUNT_SPACE = 346
LAUNCH_COST_SOL = 0.217

MAX_TRANSFER_FEE = 1_000_000_000
TRANSFER_FEE_BPS = 1000

class Bablo:
    def __init__(
        self,
        cfg: BabloConfig,
        *,
        on_status: Optional[OnStatus] = None,
        on_alert: Optional[OnAlert] = None,
        get_ca: Optional[GetCA] = None,
    ):
        self.cfg = cfg
        self.on_status: OnStatus = on_status or (lambda s: asyncio.sleep(0))
        self.on_alert: OnAlert = on_alert or (lambda s: asyncio.sleep(0))
        self.get_ca: Optional[GetCA] = get_ca

        self._client = SolanaClient(HELIUS_HTTPS, max_calls=50)
        self._ws = WsHub()

        self._stop_event = asyncio.Event()
        self._worker_task: Optional[asyncio.Task] = None
        self._pnl_task: Optional[asyncio.Task] = None

        self.original_mint: Optional[Pubkey] = None
        self.token: Optional[TokenDTO] = None
        self.dev: Optional[Keypair] = None
        self.pool: Optional[LiquidityPoolData] = None
        self.tx_create_token: Optional[str] = None
        self.tx_init_pool: Optional[str] = None
        self.tx_withdraw: Optional[str] = None

        self.token_amount = 0
        self.token_amount_ui = 0.0
        self.lamports_amount = 0
        self.wsol_amount_ui = 0.0

        self.decimals = TOKEN_DECIMALS

    def set_token_amount(self):
        self.token_amount_ui = self.cfg.token_amount_ui[0] #Randomize this
        self.token_amount = tokens_ui_to_base_units(self.token_amount_ui, self.decimals)

    def set_wsol_amount(self):
        self.wsol_amount_ui = self.cfg.wsol_amount_ui[0] #Randomize this
        self.lamports_amount = sol_to_lamports(self.wsol_amount_ui)

    def start(self):
        if self._worker_task and not self._worker_task.done():
            return
        self._stop_event.clear()
        self._worker_task = asyncio.create_task(self.working_loop(), name="bablo-working-loop")

    async def stop(self):
        self._stop_event.set()
        if self._pnl_task and not self._pnl_task.done():
            self._pnl_task.cancel()
            try:
                await self._pnl_task
            except asyncio.CancelledError:
                pass
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def working_loop(self):
        try:
            if self._stopped(): return
            self.set_token_amount()
            self.set_wsol_amount()

            ca = await self.get_contract_address()
            await self._say(f"CA получен: `{ca}`")
            self.original_mint = Pubkey.from_string(ca)

            self.token = await self._copy_token_metadata(ca)
            await self._say(f"Метаданные: {self.token.name} ({self.token.symbol})")

            self.tx_create_token = await self.create_token()
            await self._say(f"Создан mint: `{self.token.keypair.pubkey()}`; tx: `{self.tx_create_token}`")

            self.pool = await self.prepare_liquidity_pool()
            self.tx_init_pool = await self.initialize_pool()
            await self._say(f"Пул инициирован: `{self.pool.pool_state}`; tx: `{self.tx_init_pool}`")

            await self.start_monitoring_liquidity()

            timer = asyncio.create_task(asyncio.sleep(self.cfg.cycle_timeout_sec), name="bablo-timer")
            pnl_event = asyncio.Event()

            self._pnl_task = asyncio.create_task(
                self._monitor_pnl_wrapper(pnl_event),
                name="bablo-pnl"
            )

            done, _ = await asyncio.wait({timer, pnl_event.wait()},
                                         return_when=asyncio.FIRST_COMPLETED)

            self.tx_withdraw = await self.withdraw_liquidity()
            await self._say(f"Withdraw выполнен. tx: `{self.tx_withdraw}`")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            await self._yel(f"Ошибка: `{e}`")
        finally:
            if self._pnl_task and not self._pnl_task.done():
                self._pnl_task.cancel()
                try:
                    await self._pnl_task
                except asyncio.CancelledError:
                    pass

    async def get_contract_address(self) -> str:
        if self.cfg.mode == "manual":
            if not self.get_ca:
                raise RuntimeError("get_ca callback не передан для manual-режима")
            return await self.get_ca()
        elif self.cfg.mode == "auto":
            raise NotImplementedError("Auto-режим ещё не реализован в этом классе.")
        else:
            raise ValueError(f"Неизвестный режим: {self.cfg.mode}")

    @staticmethod
    async def _copy_token_metadata(original_mint_str: str) -> TokenDTO:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                follow_redirects=True,
                url=HELIUS_HTTPS,
                headers={'Content-Type': 'application/json'},
                json={"jsonrpc": "2.0", "id": "1", "method": "getAsset", "params": {"id": original_mint_str}},
            )
            resp.raise_for_status()
            result = resp.json().get('result', {})
            json_uri = result.get('content', {}).get('json_uri')
            if not json_uri:
                raise RuntimeError("json_uri не найден в контенте ассета")

            meta_resp = await client.get(url=json_uri)
            meta_resp.raise_for_status()
            meta = meta_resp.json()

        mint_kp = Keypair()
        return TokenDTO(
            name=meta.get("name") or "ClonedToken",
            symbol=meta.get("symbol") or "CLONE",
            uri=json_uri,
            keypair=mint_kp,
        )

    async def create_token(self) -> str:
        assert self.token and self.dev

        ixs: list[Instruction] = []

        ixs.append(create_account(CreateAccountParams(
            from_pubkey=self.dev.pubkey(),
            to_pubkey=self.token.keypair.pubkey(),
            lamports=CREATE_MINT_ACCOUNT_LAMPORTS,
            space=CREATE_MINT_ACCOUNT_SPACE,
            owner=TOKEN_PROGRAM_2022_ID
        )))
        ixs.append(build_initialize_transfer_fee_config_ix(
            mint=self.token.keypair.pubkey(),
            authority=self.dev.pubkey(),
            basis_points=1000,
            max_fee=1_000_000_000 * TOKEN_WITH_DECIMALS,
        ))
        ixs.append(build_initialize_metadata_pointer_ix(
            mint=self.token.keypair.pubkey(),
            authority=self.dev.pubkey(),
            metadata_address=self.token.keypair.pubkey()
        ))
        ixs.append(build_initialize_mint_ix(
            mint=self.token.keypair.pubkey(),
            mint_authority=self.dev.pubkey(),
            freeze_authority=self.dev.pubkey(),
            decimals=TOKEN_DECIMALS,
        ))
        ixs.append(build_initialize_token_metadata_ix(
            metadata=self.token.keypair.pubkey(),
            update_authority=self.dev.pubkey(),
            mint=self.token.keypair.pubkey(),
            mint_authority=self.dev.pubkey(),
            name=self.token.name,
            symbol=self.token.symbol,
            uri=self.token.uri,
        ))
        ixs.append(create_associated_token_account(
            payer=self.dev.pubkey(),
            owner=self.dev.pubkey(),
            mint=self.token.keypair.pubkey(),
            token_program_id=TOKEN_PROGRAM_2022_ID,
        ))
        ixs.append(mint_to_checked(MintToCheckedParams(
            program_id=TOKEN_PROGRAM_2022_ID,
            mint=self.token.keypair.pubkey(),
            dest=get_associated_token_address(
                owner=self.dev.pubkey(),
                mint=self.token.keypair.pubkey(),
                token_program_id=TOKEN_PROGRAM_2022_ID,
            ),
            mint_authority=self.dev.pubkey(),
            amount=self.cfg.token_amount_ui * TOKEN_WITH_DECIMALS * MILLION,
            decimals=TOKEN_DECIMALS,
        )))
        ixs.append(set_authority(SetAuthorityParams(
            program_id=TOKEN_PROGRAM_2022_ID,
            account=self.token.keypair.pubkey(),
            authority=AuthorityType.MINT_TOKENS,
            current_authority=self.dev.pubkey(),
            new_authority=None,
        )))
        ixs.append(set_authority(SetAuthorityParams(
            program_id=TOKEN_PROGRAM_2022_ID,
            account=self.token.keypair.pubkey(),
            authority=AuthorityType.FREEZE_ACCOUNT,
            current_authority=self.dev.pubkey(),
            new_authority=None,
        )))

        sig, _ = await self._client.build_and_send_transaction(
            instructions=ixs,
            msg_signer=self.dev,
            signers_keypairs=[self.token.keypair, self.dev],
            label="CREATE TOKEN-2022",
            max_retries=1,
            max_confirm_retries=10,
            priority_fee=10_000,
        )
        return str(sig)

    async def prepare_liquidity_pool(self) -> LiquidityPoolData:
        assert self.dev and self.token
        created_token_mint = self.token.keypair.pubkey()
        creator = self.dev.pubkey()

        token_ata = get_associated_token_address(owner=creator, mint=created_token_mint, token_program_id=TOKEN_PROGRAM_2022_ID)
        wsol_ata = get_associated_token_address(owner=creator, mint=SOL_WRAPPED_MINT)

        is_token_first = bytes(created_token_mint) < bytes(SOL_WRAPPED_MINT)
        token_mint0 = created_token_mint if is_token_first else SOL_WRAPPED_MINT
        token_mint1 = SOL_WRAPPED_MINT if is_token_first else created_token_mint

        token_0_program = TOKEN_PROGRAM_2022_ID if is_token_first else TOKEN_PROGRAM_ID
        token_1_program = TOKEN_PROGRAM_ID if is_token_first else TOKEN_PROGRAM_2022_ID

        token_mint0_amount = self.token_amount if is_token_first else self.lamports_amount
        token_mint1_amount = self.lamports_amount if is_token_first else self.token_amount

        token_0_ata = token_ata if is_token_first else wsol_ata
        token_1_ata = wsol_ata if is_token_first else token_ata

        program_id = RAYDIUM_CP_PROGRAM_ID
        amm_config = get_amm_config_address(index=0, program_id=program_id)
        authority = get_authority_address(program_id=program_id)
        pool_state = get_pool_address(amm_config=amm_config, token_mint0=token_mint0, token_mint1=token_mint1, program_id=program_id)
        lp_mint = get_pool_lp_mint_address(pool_state, program_id)
        creator_lp_token = get_associated_token_address(owner=creator, mint=lp_mint)
        token0_vault = get_pool_vault_address(pool=pool_state, vault_token_mint=token_mint0, program_id=program_id)
        token1_vault = get_pool_vault_address(pool=pool_state, vault_token_mint=token_mint1, program_id=program_id)
        observation = get_oracle_account_address(pool=pool_state, program_id=program_id)

        liq_vault = token1_vault if is_token_first else token0_vault

        self.pool = LiquidityPoolData(
            creator_kp=self.dev,
            token_mint0=token_mint0,
            token_mint1=token_mint1,
            token_0_program=token_0_program,
            token_1_program=token_1_program,
            token_mint0_amount=token_mint0_amount,
            token_mint1_amount=token_mint1_amount,
            pool_state=pool_state,
            authority=authority,
            lp_mint=lp_mint,
            creator_lp_token=creator_lp_token,
            token0_vault=token0_vault,
            token1_vault=token1_vault,
            observation=observation,
            creator_token0=token_0_ata,
            creator_token1=token_1_ata,
            token_0_ata=token_0_ata,
            token_1_ata=token_1_ata,
            liq_vault=liq_vault,
            lp_amount=calculate_lp_tokens(get_token_amount_after_fee(self.token_amount, TRANSFER_FEE_BPS), self.lamports_amount),
        )
        return self.pool

    async def initialize_pool(self) -> str:
        assert self.pool and self.dev and self.token
        dev = self.dev

        wsol_ata = get_associated_token_address(owner=dev.pubkey(), mint=SOL_WRAPPED_MINT)

        create_wsol_ata_ix = create_idempotent_associated_token_account(
            payer=dev.pubkey(), owner=dev.pubkey(), mint=SOL_WRAPPED_MINT
        )
        transfer_sol_ix = transfer(TransferParams(from_pubkey=dev.pubkey(), to_pubkey=wsol_ata, lamports=self.lamports_amount))
        sync_native_ix = sync_native(SyncNativeParams(account=wsol_ata, program_id=TOKEN_PROGRAM_ID))
        init_ix = build_initialize_pool_ix(tx_data=self.pool, open_time_unix=int(time.time()))
        ixs = [create_wsol_ata_ix, transfer_sol_ix, sync_native_ix, init_ix]

        sig, _ = await self._client.build_and_send_transaction(
            instructions=ixs,
            msg_signer=dev,
            signers_keypairs=[dev],
            priority_fee=50_000,
            label="INIT POOL",
        )
        return str(sig)

    async def start_monitoring_liquidity(self) -> None:
        if not self.pool:
            raise RuntimeError("Пул не подготовлен")

    async def withdraw_liquidity(self) -> str:
        assert self.pool
        txd = self.pool
        withdraw_ix = build_withdraw_ix(tx_data=txd, lp_token_amount=txd.lp_amount or 0)
        create_wsol_ata_ix = create_idempotent_associated_token_account(payer=txd.creator_kp.pubkey(),
                                                                        owner=txd.creator_kp.pubkey(),
                                                                        mint=SOL_WRAPPED_MINT)
        wsol_ata = get_associated_token_address(owner=txd.creator_kp.pubkey(), mint=SOL_WRAPPED_MINT)
        close_wsol_ata_ix = close_account(
            CloseAccountParams(
                program_id=TOKEN_PROGRAM_ID,
                account=wsol_ata,
                dest=txd.creator_kp.pubkey(),
                owner=txd.creator_kp.pubkey()
            )
        )
        sig, _ = await self._client.build_and_send_transaction(
            instructions=[create_wsol_ata_ix, withdraw_ix, close_wsol_ata_ix],
            msg_signer=txd.creator_kp,
            signers_keypairs=[txd.creator_kp],
            priority_fee=100_000,
            max_retries=3,
            max_confirm_retries=10,
            label="WITHDRAW",
        )
        return str(sig)

    async def _monitor_pnl_wrapper(self, event: asyncio.Event):
        assert self.pool
        sol_vault = self.pool.liq_vault

        async def on_value(lamports: int):
            current_sol = lamports / LAMPORTS_PER_SOL
            pnl = current_sol - lamports_to_sol(self.lamports_amount) - LAUNCH_COST_SOL
            log.info("WS: SOL=%.6f, PnL=%.6f", current_sol, pnl)
            if pnl >= self.cfg.profit_threshold_sol:
                event.set()

        stop = asyncio.Event()
        try:
            await self._ws.monitor_account_lamports(str(sol_vault), stop_event=stop, on_value=on_value)
        except asyncio.CancelledError:
            pass
        finally:
            stop.set()

    async def _wait_funding(self, pubkey: Pubkey, *, min_sol: float, timeout: int) -> bool:
        ddl = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < ddl and not self._stopped():
            bal = await self._client.get_balance_sol(pubkey)
            await self._say(f"Баланс `{pubkey}`: {bal:.4f} SOL")
            if bal >= min_sol:
                return True
            await asyncio.sleep(2.0)
        return False

    async def _say(self, text: str):
        try:
            await self.on_status(text)
        except Exception:
            pass

    async def _yel(self, text: str):
        try:
            await self.on_alert(text)
        except Exception:
            pass

    def _stopped(self) -> bool:
        return self._stop_event.is_set()
