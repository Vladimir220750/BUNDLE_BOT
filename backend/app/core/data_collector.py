from __future__ import annotations

import contextlib
import struct
from typing import Final
import asyncio

from typing import List, Optional

from construct import Struct, Int64ul, Flag, Bytes
from solders.pubkey import Pubkey
from spl.token.instructions import get_associated_token_address

from .wallet_manager import WalletManager
from ..core.wallet_manager import Wallet
from ..core.client import SolanaClient
from ..core.logger import logger
from ..core.constants import LAMPORTS_PER_SOL, DECIMALS
from ..services.tokens import get_token
from ..enums import Role

EXPECTED_DISCRIMINATOR: Final[bytes] = struct.pack("<Q", 6966180631402821399)

class BondingCurveState:
    _STRUCT = Struct(
        "virtual_token_reserves" / Int64ul,
        "virtual_sol_reserves" / Int64ul,
        "real_token_reserves" / Int64ul,
        "real_sol_reserves" / Int64ul,
        "token_total_supply" / Int64ul,
        "complete" / Flag,
        "creator" / Bytes(32),
    )

    def __init__(self, data: bytes) -> None:
        """Parse bonding curve data."""
        if data[:8] != EXPECTED_DISCRIMINATOR:
            raise ValueError("Invalid curve state discriminator")

        parsed = self._STRUCT.parse(data[8:])
        self.virtual_token_reserves = parsed["virtual_token_reserves"]
        self.virtual_sol_reserves = parsed["virtual_sol_reserves"]
        self.real_token_reserves = parsed["real_token_reserves"]
        self.real_sol_reserves = parsed["real_sol_reserves"]
        self.token_total_supply = parsed["token_total_supply"]
        self.complete = parsed["complete"]
        self.creator = parsed["creator"]

        if hasattr(self, 'creator') and isinstance(self.creator, bytes):
            self.creator = Pubkey.from_bytes(self.creator)


class DataCollector:
    """
    Централизованный агрегатор данных для WalletManager и фронта.
    Всё, что не критично, идёт в Solana public RPC; всё критичное – остаётся на Helius.
    """

    def __init__(
        self,
        solana_client: SolanaClient,
        wm: WalletManager,
    ) -> None:
        self.wm = wm
        self._solana_client = solana_client
        self._lock   = asyncio.Lock()
        self._ws_clients: List[asyncio.Queue[dict]] = []
        self._running = False
        self._bg_task: Optional[asyncio.Task] = None
        self.curve_state: Optional[BondingCurveState] = None
        self.price: float = 0.0

        asyncio.create_task(self.update_lamports_balances(wm.wallets))

    @staticmethod
    def _get_ui_lamports(lamports: int) -> float:
        return lamports / LAMPORTS_PER_SOL

    @staticmethod
    def _get_ui_tokens(tokens: int):
        return float((tokens / 10 ** DECIMALS) / 10 ** DECIMALS)

    async def start(self) -> None:
        """Запускает фоновые задачи: ping + рассылка снапшотов."""
        if self._running:
            return
        self._running = True
        self.actual_data = False
        logger.info("DataCollector started")

    async def stop(self) -> None:
        """Останавливает фоновые задачи и очищает подписчиков."""
        self._running = False
        if self._bg_task:
            self._bg_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._bg_task
        self._ws_clients.clear()
        logger.info("DataCollector stopped")

    async def _update_curve_state(self, curve_address):
        asyncio.Lock()
        try:
            value = await self._solana_client.get_account_info(curve_address)
        except ValueError:
            raise ValueError("Invalid curve state: No data")
        if not value.data:
            raise ValueError("Invalid curve state: No data")

        data = value.data
        if data[:8] != EXPECTED_DISCRIMINATOR:
            raise ValueError("Invalid curve state discriminator")

        curve_state = BondingCurveState(data)
        self.curve_state = curve_state

        await self._send_curve_state()

    async def update_lamports_balances(self, wallets: list[Wallet]) -> None:
        lamports = await self._solana_client.get_multiple_accounts_lamports_balances(
            [w.pubkey for w in wallets]
        )
        wallet_balance_map = {}
        for w, b in zip(wallets, lamports):
            w.lamports_balance = b
            wallet_balance_map[w.name] = self._get_ui_lamports(b)
        data = {"lam": wallet_balance_map}
        await self._send_ws_data(data)

    async def get_total_ui_sol_balances(self):
        lamports = await self._solana_client.get_multiple_accounts_lamports_balances(
            [w.pubkey for w in self.wm.wallets]
        )
        total = 0
        for b in lamports:
            total += b
        return self._get_ui_lamports(total)

    async def update_token_balances(self, wallets: list[Wallet]) -> None:
        wallet_balance_map = {}
        for w in wallets:
            if w.ata_address is None:
                token_info = await get_token()
                w.ata_address = w.get_ata(Pubkey.from_string(token_info.mint_address))
            tokens = await self._solana_client.get_token_account_balance(w.ata_address)
            w.token_balance = tokens or 0
            logger.info(f"Wallet {w.name} have {tokens / 10 ** 12} mln tokens")
            wallet_balance_map[w.name] = tokens
        data = {"token": wallet_balance_map}
        await self._send_ws_data(data)

    async def get_token_balance(self, wallet: Wallet) -> int:
        if wallet.ata_address is None:
            token_info = await get_token()
            wallet.ata_address = wallet.get_ata(Pubkey.from_string(token_info.mint_address))
        tokens = await self._solana_client.get_token_account_balance(wallet.ata_address) or 0
        wallet.token_balance = tokens
        return tokens

    async def get_price(self, curve_address: Pubkey) -> float:
        await self._update_curve_state(curve_address)
        price = ((self.curve_state.virtual_sol_reserves / LAMPORTS_PER_SOL) /
                (self.curve_state.virtual_token_reserves / 10 ** DECIMALS))
        self.price = price
        return price

    async def get_liquidity(self) -> float:
        return self._get_ui_lamports(self.curve_state.real_sol_reserves)

    async def _get_market_cap(self):
        return self.price * self.curve_state.token_total_supply / 10 ** DECIMALS

    async def subscribe(self) -> asyncio.Queue[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=32)
        self._ws_clients.append(q)

        # Sending init data
        await self._send_sol_balances()
        await self._send_token_balances()

        if self.curve_state:
            await self._send_curve_state()

        return q

    async def _send_sol_balances(self):
        await self._send_ws_data({
            "lam": {
                w.name: self._get_ui_lamports(w.lamports_balance) for w in self.wm.wallets
            }
        })

    async def _send_token_balances(self):
        await self._send_ws_data({
            "token": {
                w.name: self._get_ui_tokens(w.token_balance) for w in self.wm.wallets
            }
        })

    async def _send_curve_state(self):
        await self._send_ws_data({
            "curve_state": {
                "mcap": await self._get_market_cap(),
                "liq": await self.get_liquidity(),
            }
        })

    async def _send_ws_data(self, data: dict):
        if not self._ws_clients:
            return
        for q in self._ws_clients:
            if not q.full():
                await q.put(data)
        logger.info(f"SEND WS DATA: {data}")

    async def handle_command(self, command: str, *args):
        logger.info(f"receiving command {command}")
        commands_map = {
            "refresh": self.refresh_data
        }
        await commands_map[command]()

    async def refresh_data(self):
        # update self data
        await self.update_lamports_balances(self.wm.wallets)

        #update external data
        await self._send_sol_balances()
        await self._send_token_balances()

        if self.curve_state:
            await self._send_curve_state()
