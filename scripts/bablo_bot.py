import asyncio
import time
from dataclasses import dataclass
from typing import Optional, Any, Tuple, Callable

PROFIT_THRESHOLD_SOL: float = 0.05
TIMEOUT_SECONDS: int = 4
POLL_INTERVAL_SEC: float = 0.25

@dataclass
class TokenBlueprint:
    """Результат 'копирования' исходной монеты — всё, что нужно для выпуска новой."""
    name: str
    symbol: str
    decimals: int
    metadata_uri: Optional[str] = None
    extra: Optional[dict] = None

@dataclass
class Mint:
    address: str

@dataclass
class Pool:
    address: str
    mint: Mint

@dataclass
class PnL:
    """PnL пула в SOL."""
    value_sol: float
    ts: float

async def copy_token_contract(source_contract: str) -> TokenBlueprint:
    """
    TODO: Скопируй токен: подтяни метаданные, decimals, возможно правила fee/transfer и т.д.
    """
    await asyncio.sleep(0.05)
    return TokenBlueprint(
        name="ClonedToken",
        symbol="CLONE",
        decimals=9,
        metadata_uri=None,
        extra={"source": source_contract},
    )

async def create_token(blueprint: TokenBlueprint) -> Mint:
    """
    TODO: Создай новый mint по скопированным параметрам. Верни адрес mint.
    """
    await asyncio.sleep(0.1)
    return Mint(address="Mint111111111111111111111111111111111111111")

async def create_pool(mint: Mint) -> Pool:
    """
    TODO: Создай пул ликвидности для указанного mint (например, на Raydium/Orca и т.п.).
    Верни адрес пула.
    """
    await asyncio.sleep(0.1)
    return Pool(address="Pool111111111111111111111111111111111111111", mint=mint)

async def get_pool_pnl_sol(pool: Pool) -> PnL:
    """
    TODO: Верни текущий PnL пула в SOL. Положительное значение — в плюс.
    """
    now = time.time()
    growth = max(0.0, (now % 10) / 100.0)
    return PnL(value_sol=growth, ts=now)

async def pull_liquidity(pool: Pool) -> str:
    """
    TODO: Дёрнуть ликвидность из пула. Верни сигнатуру/ид транзы.
    """
    await asyncio.sleep(0.05)
    return "Sig111111111111111111111111111111111111111111111111111111111111"

def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

class OneShot:
    """Гарантирует, что действие выполнится не более одного раза (даже при гонке задач)."""
    def __init__(self):
        self._done = False
        self._lock = asyncio.Lock()

    async def run_once(self, coro_factory: Callable[[], "asyncio.Future[Any]"]) -> Any:
        async with self._lock:
            if self._done:
                return None
            self._done = True
        return await coro_factory()

async def condition_timeout() -> Tuple[str, Optional[float]]:
    """Сработает, когда пройдёт TIMEOUT_SECONDS."""
    log(f"Таймер: ждём {TIMEOUT_SECONDS} cек…")
    await asyncio.sleep(TIMEOUT_SECONDS)
    log("Таймер: условие выполнено — прошло 4 секунды.")
    return ("timeout", None)

async def condition_profit(pool: Pool) -> Tuple[str, Optional[float]]:
    """Сработает, когда PnL >= PROFIT_THRESHOLD_SOL."""
    log(f"PNL: ждём порог {PROFIT_THRESHOLD_SOL:.4f} SOL… (poll={POLL_INTERVAL_SEC}s)")
    while True:
        pnl = await get_pool_pnl_sol(pool)
        log(f"PNL: {pnl.value_sol:.6f} SOL")
        if pnl.value_sol >= PROFIT_THRESHOLD_SOL:
            log("PNL: условие выполнено — в плюс по порогу.")
            return ("profit", pnl.value_sol)
        await asyncio.sleep(POLL_INTERVAL_SEC)

async def orchestrate() -> None:
    source_contract = input("Введи адрес контракта/минта исходной монеты: ").strip()
    if not source_contract:
        raise SystemExit("Пустой адрес контракта — выходим.")

    log(f"Старт: исходный контракт = {source_contract}")

    blueprint = await copy_token_contract(source_contract)
    log(f"Скопировано: {blueprint.name} ({blueprint.symbol}), decimals={blueprint.decimals}")

    mint = await create_token(blueprint)
    log(f"Создан mint: {mint.address}")

    pool = await create_pool(mint)
    log(f"Создан пул: {pool.address}")

    once = OneShot()

    async def do_pull():
        log("Пытаемся дёрнуть ликвидность…")
        sig = await pull_liquidity(pool)
        log(f"Ликвидность дёрнута. Tx: {sig}")
        return sig

    timeout_task = asyncio.create_task(condition_timeout(), name="timeout")
    profit_task  = asyncio.create_task(condition_profit(pool), name="profit")

    done, pending = await asyncio.wait(
        {timeout_task, profit_task},
        return_when=asyncio.FIRST_COMPLETED
    )

    reason, value = next(iter(done)).result()
    if reason == "timeout":
        log("Триггер: прошло 4 секунды.")
    elif reason == "profit":
        log(f"Триггер: PnL достиг {value:.6f} SOL (≥ {PROFIT_THRESHOLD_SOL:.6f}).")

    await once.run_once(do_pull)

    for p in pending:
        p.cancel()
        try:
            await p
        except asyncio.CancelledError:
            pass

    log("Готово.")

if __name__ == "__main__":
    try:
        asyncio.run(orchestrate())
    except KeyboardInterrupt:
        log("Остановлено пользователем.")
