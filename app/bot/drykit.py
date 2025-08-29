# bot/drykit.py
from __future__ import annotations
import asyncio
import time
from typing import Tuple
from solders.keypair import Keypair

from app.core.bablo import Bablo
from app.core.constants import LAMPORTS_PER_SOL, TokenDTO
from app.core.client import SolanaClient
from app.core.ws_hub import WsHub

def _sim_sig(prefix: str) -> str:
    return f"SIM_{prefix}_{int(time.time())}"

def apply_dry_mode() -> None:
    # 1) getAsset → фейковые метаданные
    async def fake_copy_token_metadata(original_mint_str: str) -> TokenDTO:
        return TokenDTO(name="DryClone", symbol="DRY", uri="https://example.com/meta.json", keypair=Keypair())
    Bablo._copy_token_metadata = staticmethod(fake_copy_token_metadata)  # type: ignore[attr-defined]

    # 2) Отправка транзакций → фейковые сигнатуры
    async def fake_build_and_send_transaction(self: SolanaClient, **kwargs) -> Tuple[str, bool]:  # type: ignore[override]
        label = kwargs.get("label", "TX")
        return _sim_sig(label.replace(" ", "_")), True
    SolanaClient.build_and_send_transaction = fake_build_and_send_transaction  # type: ignore[assignment]

    # 3) Мониторинг ликвидности → имитируем рост баланса
    async def fake_monitor_account_lamports(self: WsHub, pubkey: str, *, on_value, **kwargs):  # type: ignore[override]
        for sol in (0.10, 0.35, 0.50):
            await on_value(int(sol * LAMPORTS_PER_SOL))
            await asyncio.sleep(0.3)
    WsHub.monitor_account_lamports = fake_monitor_account_lamports  # type: ignore[assignment]

    # 4) Явные фейк-сигнатуры ключевых шагов
    async def fake_create_token(self: Bablo) -> str: return _sim_sig("CREATE_TOKEN")
    async def fake_initialize_pool(self: Bablo) -> str: return _sim_sig("INIT_POOL")
    async def fake_withdraw(self: Bablo) -> str: return _sim_sig("WITHDRAW")
    Bablo.create_token = fake_create_token           # type: ignore[assignment]
    Bablo.initialize_pool = fake_initialize_pool     # type: ignore[assignment]
    Bablo.withdraw_liquidity = fake_withdraw         # type: ignore[assignment]
