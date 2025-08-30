from aiogram import Bot, Dispatcher

from .handlers import routers


def create_dispatcher() -> Dispatcher:
    """Создать Dispatcher и подключить все роутеры."""
    dp = Dispatcher()
    for router in routers:
        dp.include_router(router)
    return dp


async def run(bot: Bot) -> None:
    """Запустить бота."""
    dp = create_dispatcher()
    await dp.start_polling(bot)
