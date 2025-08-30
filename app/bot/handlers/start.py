from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from ..keyboards import main_menu_kb
from ..texts import START_MESSAGE
from ..storage import admin_check

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext) -> None:
    """Стартовое сообщение и основное меню."""
    if not admin_check(message.from_user.id):
        await message.reply("Access denied.")
        return
    await message.reply(START_MESSAGE, reply_markup=main_menu_kb(), parse_mode="HTML")
    await state.clear()
