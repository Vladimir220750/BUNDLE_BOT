from aiogram import Bot, Dispatcher

from .handlers import routers
from .config import load_config
from .facade import BabloController
from .settings import SETTINGS


def create_dispatcher() -> Dispatcher:
    """Создать Dispatcher и подключить все роутеры."""
    dp = Dispatcher()
    for router in routers:
        dp.include_router(router)
    return dp


async def run() -> None:
    """Запустить бота."""
    if not SETTINGS.bot_token:
        raise RuntimeError("BOT_TOKEN not provided in env")

    bot = Bot(token=SETTINGS.bot_token, parse_mode=None)
    dp = create_dispatcher()

    cfg = load_config()
    admin_ids = getattr(SETTINGS, "admin_ids", [])
    admin_id = admin_ids[0] if admin_ids else None
    controller = BabloController(cfg, bot, admin_id)
    bot["controller"] = controller

    await dp.start_polling(bot)
