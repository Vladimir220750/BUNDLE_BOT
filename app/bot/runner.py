from aiogram import Bot, Dispatcher

from .handlers import routers
from .config import load_config
from .facade import BabloController
from .keyboards import main_menu_kb
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
    admin_id = SETTINGS.admin_ids[0] if SETTINGS.admin_ids else None
    controller = BabloController(cfg, bot, admin_id)
    bot.controller = controller
    dp.controller = controller
    boot_chat_id = SETTINGS.boot_chat_id or admin_id
    if boot_chat_id:
        await bot.send_message(boot_chat_id, "✅ Bot up (mode=bot)")
        await bot.send_message(boot_chat_id, "Меню настроек", reply_markup=main_menu_kb())

    await dp.start_polling(bot)
