import httpx
from typing import Optional
import uuid
import asyncio
import contextlib
import json
import websockets

from solders.solders import Pubkey

from .client import SolanaClient
from .logger import logger
from .constants import RPC_WS_URL, LAMPORTS_PER_SOL
from ..services.liquidity_pool import load_from_json
from ..services.withdraw import withdraw
from ..core.dto import Wallet
from ..core.config import settings
from ..utils import load_config


class DataCollector:
    def __init__(self, solana_client: SolanaClient):
        self.init_lamports = int(load_config().initial_balance * LAMPORTS_PER_SOL)
        self.solana_client = solana_client
        self._liq_vault: Pubkey = load_from_json().liq_vault
        self._ws_clients: list[asyncio.Queue[dict]] = []
        self.wallets: list[Wallet] = []
        self._running = False
        self._track_task: Optional[asyncio.Task] = None
        self._last_lamports: int = 0
        self._sub_wallet_map: dict = {}

        asyncio.create_task(self.update_wallets())

    async def start(self):
        if self._running:
            return
        self._running = True
        self._liq_vault = load_from_json().liq_vault
        await self.update_wallet_balances()
        await self._fetch_liquidity()
        self.init_lamports = int(load_config().initial_balance * LAMPORTS_PER_SOL)
        self._track_task = asyncio.create_task(self._track_liquidity())
        logger.info("DataCollector started")

    async def stop(self):
        self._running = False
        if self._track_task:
            self._track_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._track_task
        self._ws_clients.clear()
        await self.account_unsub()
        logger.info("DataCollector stopped")

    async def update_wallets(self):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{settings.pumpfun_backend}/export-wallets/")
                self.wallets = [Wallet.from_dict(w) for w in resp.json().get("wallets")]
        except Exception as e:
            logger.exception(f"Error while collecting Wallets: {e}")

    async def update_wallet_balances(self):
        wallets = self.wallets
        lamports = await self.solana_client.get_multiple_accounts_lamports_balances(
            [w.pubkey for w in wallets]
        )
        for w, b in zip(wallets, lamports):
            w.lamports_balance = b

    async def subscribe(self) -> asyncio.Queue[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=32)
        self._ws_clients.append(q)
        logger.info(f"New subscriber added, total: {len(self._ws_clients)}")
        await self._send_init_data()
        return q

    async def _send_init_data(self):
        await self.update_wallet_balances()
        await self._fetch_liquidity()
        await self._broadcast(self.UI_data)

    async def _broadcast(self, payload: dict):
        for q in self._ws_clients:
            try:
                while not q.empty():
                    q.get_nowait()
                await q.put({
                    "type": "update",
                    "payload": payload
                })
            except asyncio.QueueFull:
                logger.warning("Queue is full — skipping client update")

    async def _fetch_liquidity(self, retries: int = 1, delay: float = 0.2) -> None:
        balance = 0
        for i in range(retries):
            balance = await self.solana_client.get_token_account_balance(self._liq_vault)
            if balance > 0:
                self._last_lamports = balance
                return
            await asyncio.sleep(delay)
        logger.debug("[DC] fetch_liquidity failed to get non-zero balance")
        self._last_lamports = balance

    @property
    def liquidity_ui(self):
        return self._last_lamports / LAMPORTS_PER_SOL

    @property
    def pnl_digit(self) -> float:
        """Raw profit/loss in SOL"""
        if self._last_lamports is None:
            return 0.0
        total_now = self._last_lamports + self.total_lamports_balance
        pnl = (total_now - self.init_lamports) / LAMPORTS_PER_SOL
        if pnl >= 0.5:
            pass
        return pnl

    @property
    def pnl_percent(self) -> float:
        """Profit/loss in percent relative to initial value"""
        if self._last_lamports is None or self.init_lamports == 0:
            return 0.0
        total_now = self._last_lamports + self.total_lamports_balance
        return ((total_now / self.init_lamports) - 1) * 100

    @property
    def total_lamports_balance(self):
        balance: int = 0
        for w in self.wallets:
            balance += w.lamports_balance
        return balance

    @property
    def UI_data(self):
        return {
            "liquidity": self.liquidity_ui,
            "pnl_digit": self.pnl_digit,
            "pnl_percent": self.pnl_percent,
            "total_balance": self.total_lamports_balance / LAMPORTS_PER_SOL
        }

    async def _track_liquidity(self):
        logger.info("Tracking liquidity...")
        while self._running:
            try:
                async with websockets.connect(RPC_WS_URL, ping_interval=20, ping_timeout=10) as ws_conn:
                    async def subscribe(pubkey: str) -> int:
                        request_id = str(uuid.uuid4())
                        await ws_conn.send(json.dumps({
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "method": "accountSubscribe",
                            "params": [
                                pubkey,
                                {
                                    "encoding": "base64",
                                    "commitment": "confirmed"
                                }
                            ]
                        }))
                        while True:
                            raw_ = await ws_conn.recv()
                            msg_ = json.loads(raw_)
                            if msg_.get("id") == request_id:
                                return msg_["result"]

                    self._sub_wallet_map[await subscribe(str(self._liq_vault))] = self._liq_vault
                    for wallet in self.wallets:
                        self._sub_wallet_map[await subscribe(str(wallet.pubkey))] = wallet

                    await self._broadcast(self.UI_data)
                    while self._running:
                        try:
                            raw = await asyncio.wait_for(ws_conn.recv(), timeout=30)
                            msg = json.loads(raw)

                            if msg.get("method") == "accountNotification":
                                value = msg["params"]["result"]["value"]
                                lamports = value.get("lamports")
                                subscription = msg["params"]["subscription"]

                                account = self._sub_wallet_map.get(subscription)

                                if isinstance(account, Pubkey):
                                    if self._last_lamports is None or lamports != self._last_lamports:
                                        self._last_lamports = lamports
                                        logger.info(f"[WSOL] UI DATA: {self.UI_data}")
                                        await self._broadcast(self.UI_data)
                                elif isinstance(account, Wallet):
                                    wallet = self._sub_wallet_map.get(subscription)
                                    if wallet:
                                        wallet.lamports_balance = lamports
                                        await self._broadcast(self.UI_data)

                        except asyncio.TimeoutError:
                            logger.warning("WS receive timeout — reconnecting")
                            self._sub_id = None
                            break
                        except Exception as e:
                            logger.warning(f"track_liquidity inner error: {e}")
                            await asyncio.sleep(1)
                            break
            except Exception as outer_e:
                logger.error(f"Failed to connect to Solana WS: {outer_e}")
                await asyncio.sleep(5)

    async def account_unsub(self):
        if not self._sub_wallet_map:
            return
        async with websockets.connect(RPC_WS_URL) as ws_conn:
            for sub in self._sub_wallet_map.keys():
                await ws_conn.send(json.dumps({
                      "jsonrpc": "2.0",
                      "id": 1,
                      "method": "accountUnsubscribe",
                      "params": [sub]
                    }))
            self._sub_wallet_map = {}
