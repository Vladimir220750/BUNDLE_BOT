from html import escape

from aiogram import Router, types, F
from aiogram.filters import Command

from ..storage import admin_check
from ..facade import maybe_await
from ..reporting import format_status

router = Router()


@router.callback_query(F.data == "action:status")
async def action_status(query: types.CallbackQuery) -> None:
    if not admin_check(query.from_user.id):
        await query.answer("Access denied.", show_alert=True)
        return
    controller = query.bot.get("controller")
    if controller and hasattr(controller, "status"):
        try:
            st = await maybe_await(controller.status())
            await query.message.reply(format_status(escape(str(st))), parse_mode="HTML")
        except Exception as e:
            await query.message.reply(f"Error retrieving status: {escape(str(e))}")
    else:
        cfg = getattr(controller, "cfg", None)
        await query.message.reply(f"<b>Controller:</b>\n<pre>{escape(str(cfg))}</pre>", parse_mode="HTML")
    await query.answer()


@router.callback_query(F.data == "action:show_config")
async def action_show_config(query: types.CallbackQuery) -> None:
    if not admin_check(query.from_user.id):
        await query.answer("Access denied.", show_alert=True)
        return
    controller = query.bot.get("controller")
    cfg = getattr(controller, "cfg", None)
    await query.message.reply(f"<b>Config:</b>\n<pre>{escape(str(cfg))}</pre>", parse_mode="HTML")
    await query.answer()


@router.message(Command("status"))
async def cmd_status(message: types.Message) -> None:
    if not admin_check(message.from_user.id):
        await message.reply("Access denied.")
        return
    controller = message.bot.get("controller")
    if controller and hasattr(controller, "status"):
        try:
            st = await maybe_await(controller.status())
            await message.reply(format_status(escape(str(st))), parse_mode="HTML")
            return
        except Exception as e:
            await message.reply(f"Error retrieving status: {escape(str(e))}")
            return
    await message.reply(
        f"Controller cfg: <pre>{escape(str(getattr(controller,'cfg',None)))}</pre>", parse_mode="HTML"
    )
