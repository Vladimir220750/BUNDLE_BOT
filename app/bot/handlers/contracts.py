from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from ..storage import EditState, admin_check
from ..facade import maybe_await

router = Router()


@router.callback_query(F.data == "action:set_ca")
async def set_ca_prompt(query: types.CallbackQuery, state: FSMContext) -> None:
    if not admin_check(query.from_user.id):
        await query.answer("Access denied.", show_alert=True)
        return
    await query.message.reply("Send CA / original mint address (single line).")
    await state.set_state(EditState.waiting_for_ca)
    await query.answer()


@router.message(EditState.waiting_for_ca)
async def receive_ca(message: types.Message, state: FSMContext) -> None:
    if not admin_check(message.from_user.id):
        await message.reply("Access denied.")
        await state.clear()
        return
    ca = message.text.strip()
    controller = message.bot.get("controller")
    if controller and hasattr(controller, "set_ca"):
        try:
            await maybe_await(controller.set_ca(ca))
            await message.reply(f"CA stored: <code>{ca}</code>", parse_mode="HTML")
            await state.clear()
            return
        except Exception as e:
            await message.reply(f"set_ca failed: {e}")
    if controller and hasattr(controller, "cfg"):
        try:
            setattr(controller.cfg, "default_ca", ca)
            await message.reply(f"CA set to <code>{ca}</code> on controller.cfg", parse_mode="HTML")
            await state.clear()
            return
        except Exception as e:
            await message.reply(f"Failed to set CA on cfg: {e}")
            await state.clear()
            return
    await message.reply("No controller available to set CA.")
    await state.clear()
