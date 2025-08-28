import asyncio
import time
from dataclasses import dataclass
from typing import Optional, Any, Tuple, Callable
import json

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
    """Загрузить метаданные существующего токена.

    В проекте уже существует готовая реализация –
    :func:`backend.app.services.tokens.copy_token`. Здесь мы лишь
    используем её и преобразуем ответ в локальный ``TokenBlueprint``.
    """

    from backend.app.core.constants import TOKEN_DECIMALS
    from backend.app.services import tokens as token_service

    # ``copy_token`` возвращает ``JSONResponse`` с нужными полями.
    resp = await token_service.copy_token(source_contract)
    if hasattr(resp, "body"):
        meta = json.loads(resp.body)
    else:  # уже dict
        meta = resp

    extra: dict[str, Any] = {}
    for key in ("description", "telegram", "twitter", "website", "image", "image_base64"):
        if meta.get(key) is not None:
            extra[key] = meta[key]

    return TokenBlueprint(
        name=meta.get("name") or "",
        symbol=meta.get("symbol") or "",
        decimals=TOKEN_DECIMALS,
        metadata_uri=meta.get("image"),
        extra=extra,
    )

async def create_token(blueprint: TokenBlueprint) -> Mint:
    """Создание нового mint на основе скопированного токена.

    Использует сервис ``tokens.create_token_raydium``. Перед созданием
    сервис читает параметры токена из подготовленного файла. Поэтому
    здесь мы просто делегируем выполнение существующей функции и
    извлекаем адрес созданного mint через ``tokens.get_token``.
    """

    from backend.app.core.client import SolanaClient
    from backend.app.core.config import settings
    from backend.app.core.wallet_manager import WalletManager
    from backend.app.services.tokens import create_token_raydium, get_token

    solana_client = SolanaClient(settings.helius_rpc_url)
    wm = WalletManager(solana_client)

    # Сама логика создания токена уже реализована в сервисе
    await create_token_raydium(solana_client, wm)

    # Сервис сохраняет информацию о токене в файле, получаем её оттуда
    token_info = await get_token("token_raydium.json")
    return Mint(address=token_info.mint_address)

async def create_pool(mint: Mint) -> Pool:
    """Создать пул ликвидности для указанного mint.

    В проекте уже есть сложный сервис инициализации пула Raydium –
    :func:`raydium.app.services.initialize_pool.initialize_pool`. Он
    сохраняет параметры пула в ``liq_pool/latest_pool.json``. После
    вызова этой функции мы загружаем данные из файла и возвращаем адрес
    пула.
    """

    from backend.app.core.client import SolanaClient
    from backend.app.core.config import settings
    from backend.app.core.wallet_manager import WalletManager
    from backend.app.enums import Role
    from raydium.app.services.initialize_pool import initialize_pool
    from raydium.app.services.liquidity_pool import load_from_json

    solana_client = SolanaClient(settings.helius_rpc_url)
    wm = WalletManager(solana_client)
    dev_wallet = (await wm.get_wallets_by_group(Role.dev))[0]

    # Минимальные параметры для старта пула. Полная логика находится в сервисе
    await initialize_pool(
        solana_client=solana_client,
        token_amount_ui=1,
        wsol_amount_ui=1.0,
        dev_wallet=dev_wallet,
        sniper_wallets=[],
        snipe_amount_ui=None,
        created_token_string=mint.address,
        random_pool_id=None,
        transfer_fee=0,
    )

    pool_data = load_from_json()
    return Pool(address=str(pool_data.pool_state), mint=mint)

async def get_pool_pnl_sol(pool: Pool) -> PnL:
    """Получить текущий PnL пула в SOL.

    Для расчётов используется ``DataCollector`` – центральный агрегатор
    данных в проекте. Он предоставляет информацию о состоянии bonding
    curve и текущей ликвидности. Здесь мы обновляем состояние кривой и
    считаем разницу между текущей ликвидностью и первоначальными
    вложениями (по умолчанию 1 SOL при создании пула в ``create_pool``).
    """

    from solders.pubkey import Pubkey
    from backend.app.core.client import SolanaClient
    from backend.app.core.config import settings
    from backend.app.core.wallet_manager import WalletManager
    from backend.app.core.data_collector import DataCollector
    from backend.app.services.tokens import get_token

    solana_client = SolanaClient(settings.helius_rpc_url)
    wm = WalletManager(solana_client)
    dc = DataCollector(solana_client, wm)

    token_info = await get_token("token_raydium.json")
    bonding_curve = Pubkey.from_string(token_info.bonding_curve)

    # get_price обновит состояние кривой внутри DataCollector
    await dc.get_price(bonding_curve)
    liquidity = await dc.get_liquidity()

    pnl_val = liquidity - 1.0  # 1 SOL вложен при создании
    return PnL(value_sol=pnl_val, ts=time.time())

async def pull_liquidity(pool: Pool) -> str:
    """Вывод ликвидности из пула.

    Реализация основана на сервисе ``raydium.app.services.withdraw``.
    Там уже есть логика подготовки инструкций и отправки транзакций, но
    функция не возвращает сигнатуру. Здесь мы повторяем её шаги и
    возвращаем подпись отправленной транзакции.
    """

    from spl.token.constants import WRAPPED_SOL_MINT
    from spl.token.instructions import create_idempotent_associated_token_account
    from raydium.app.instructions.amm_pool import build_withdraw_ix
    from raydium.app.services.liquidity_pool import load_from_json
    from backend.app.core.client import SolanaClient
    from backend.app.core.config import settings

    solana_client = SolanaClient(settings.helius_rpc_url)

    tx_data = load_from_json()
    owner_lp_balance = await solana_client.get_token_account_balance(tx_data.creator_lp_token)
    if owner_lp_balance == 0:
        owner_lp_balance = tx_data.lp_amount

    withdraw_ix = build_withdraw_ix(tx_data=tx_data, lp_token_amount=owner_lp_balance)
    create_wsol_ata_ix = create_idempotent_associated_token_account(
        payer=tx_data.creator_kp.pubkey(),
        owner=tx_data.creator_kp.pubkey(),
        mint=WRAPPED_SOL_MINT,
    )

    sig = await solana_client.build_and_send_transaction(
        instructions=[create_wsol_ata_ix, withdraw_ix],
        msg_signer=tx_data.creator_kp,
        signers_keypairs=[tx_data.creator_kp],
        priority_fee=50_000,
        max_retries=1,
        label="WITHDRAW",
        jito_tip=500_000,
    )
    return str(sig)

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
