# app/bot/main.py
import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums.parse_mode import ParseMode

# load .env from the bot folder (if present)
try:
    from dotenv import load_dotenv  # type: ignore
    DOTENV_PATH = Path(__file__).resolve().with_name(".env")
    if DOTENV_PATH.exists():
        load_dotenv(DOTENV_PATH)
    else:
        load_dotenv()  # fallback to usual behavior
except Exception:
    pass

from .settings import SETTINGS
from .config import load_config
from .controller import BabloController
from .handlers import router as handlers_router

# ─── DRY MODE ─────────────────────────────────────────────────────────────────
DRY_MODE = SETTINGS.dry_mode
if DRY_MODE:
    # заглушки для безопасного оффлайнового прогона
    try:
        from .drykit import apply_dry_mode
        apply_dry_mode()
    except Exception as e:
        logging.warning("Failed to apply drykit: %s", e)

# ─── ЛОГИ ─────────────────────────────────────────────────────────────────────
def setup_logging():
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s:%(lineno)d | %(message)s",
    )
    logging.getLogger("aiogram.event").setLevel(level)
    logging.getLogger("aiogram.dispatcher").setLevel(level)
    logging.info("Logging initialized. DRY_MODE=%s", DRY_MODE)

# ─── Middleware для DI контроллера ────────────────────────────────────────────
class ControllerMiddleware(BaseMiddleware):
    def __init__(self, controller: BabloController):
        super().__init__()
        self.controller = controller

    async def __call__(self, handler, event, data):
        # прокидываем controller в kwargs всех хендлеров
        data["controller"] = self.controller
        return await handler(event, data)

# ─── entrypoint ───────────────────────────────────────────────────────────────
async def main():
    setup_logging()
    if (not SETTINGS.bot_token or not SETTINGS.admin_ids) and not DRY_MODE:
        raise RuntimeError("BOT_TOKEN and ADMIN_IDS must be set when dry_mode is False")

    bot = Bot(token=SETTINGS.bot_token, parse_mode=ParseMode.HTML)
    dp = Dispatcher(storage=MemoryStorage())

    # Контроллер приложения
    cfg = load_config()
    admin_chat_id = SETTINGS.admin_ids[0] if SETTINGS.admin_ids else 0
    controller = BabloController(cfg=cfg, bot=bot, admin_chat_id=admin_chat_id)

    # --- fallback: положим контроллер в диспетчер data, чтобы его можно было получить из handlers ---
    # (это работает как запасной вариант, если middleware по какой-то причине не проходит)
    try:
        dp["controller"] = controller
    except Exception:
        # dp may not support item assignment in some versions — then set attribute
        setattr(dp, "controller", controller)

    # Middleware: делаем controller доступным во всех хендлерах как аргумент
    try:
        dp.update.outer_middleware(ControllerMiddleware(controller))
    except Exception:
        # некоторые версии aiogram могут иметь другой API — в этом случае мы всё ещё
        # имеем controller в dp.data (см. выше), и можно править handlers чтобы доставать его
        logging.warning("outer_middleware registration failed — controller will be available via dp['controller'].")

    # Регистрация роутеров
    dp.include_router(handlers_router)

    # Удаляем webhook (защита от блокировки polling)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass

    logging.info("Bot polling started…")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
