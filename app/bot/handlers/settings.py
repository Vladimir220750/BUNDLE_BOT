from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from ..keyboards import params_keyboard
from ..storage import EditState, admin_check
from ..facade import _apply_config

router = Router()


@router.callback_query(F.data == "action:choose_param")
async def choose_param(query: types.CallbackQuery, state: FSMContext) -> None:
    if not admin_check(query.from_user.id):
        await query.answer("Access denied.", show_alert=True)
        return
    await query.message.edit_text("Выберите параметр для редактирования:", reply_markup=params_keyboard())
    await query.answer()


@router.callback_query(F.data.startswith("param:"))
async def param_selected(query: types.CallbackQuery, state: FSMContext) -> None:
    if not admin_check(query.from_user.id):
        await query.answer("Access denied.", show_alert=True)
        return
    key = query.data.split(":", 1)[1]
    await state.update_data(param_key=key)
    await state.set_state(EditState.waiting_for_value)
    await query.message.reply(
        f"Send new value for <b>{key}</b>. You can send numbers, strings or lists (space/comma separated).",
        parse_mode="HTML",
    )
    await query.answer()


@router.message(EditState.waiting_for_value)
async def receive_param_value(message: types.Message, state: FSMContext) -> None:
    if not admin_check(message.from_user.id):
        await message.reply("Access denied.")
        await state.clear()
        return
    data = await state.get_data()
    key = data.get("param_key")
    controller = message.bot.get("controller")
    success, msg = await _apply_config(controller, key, message.text)
    await message.reply(msg, parse_mode="HTML")
    await state.clear()
