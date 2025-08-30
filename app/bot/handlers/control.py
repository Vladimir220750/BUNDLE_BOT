from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from ..keyboards import main_menu_kb
from ..storage import admin_check
from ..facade import maybe_await

router = Router()


@router.callback_query(F.data == "action:run")
async def action_run(query: types.CallbackQuery) -> None:
    if not admin_check(query.from_user.id):
        await query.answer("Access denied.", show_alert=True)
        return
    controller = getattr(query.bot, "controller", None)
    if controller and hasattr(controller, "start"):
        await maybe_await(controller.start())
        await query.message.reply("Controller.start() called.")
    else:
        await query.message.reply("No controller.start available.")
    await query.answer()


@router.callback_query(F.data == "action:stop")
async def action_stop(query: types.CallbackQuery) -> None:
    if not admin_check(query.from_user.id):
        await query.answer("Access denied.", show_alert=True)
        return
    controller = getattr(query.bot, "controller", None)
    if controller and hasattr(controller, "stop"):
        await maybe_await(controller.stop())
        await query.message.reply("Controller.stop() called.")
    else:
        await query.message.reply("No controller.stop available.")
    await query.answer()


@router.callback_query(F.data == "action:toggle_autorun")
async def action_toggle_autorun(query: types.CallbackQuery) -> None:
    if not admin_check(query.from_user.id):
        await query.answer("Access denied.", show_alert=True)
        return
    controller = getattr(query.bot, "controller", None)
    if controller and hasattr(controller, "cfg"):
        cfg = controller.cfg
        autorun = getattr(cfg, "autorun", False)
        new = not autorun
        try:
            setattr(cfg, "autorun", new)
        except Exception:
            pass
        await query.message.reply(f"Autorun set to: {new}")
    else:
        await query.message.reply("Controller configuration not available.")
    await query.answer()


@router.callback_query(F.data == "action:back")
async def action_back(query: types.CallbackQuery) -> None:
    if not admin_check(query.from_user.id):
        await query.answer("Access denied.", show_alert=True)
        return
    await query.message.edit_text("Main menu", reply_markup=main_menu_kb())
    await query.answer()


@router.message(F.text == "/run")
async def cmd_run(message: types.Message) -> None:
    if not admin_check(message.from_user.id):
        await message.reply("Access denied.")
        return
    controller = getattr(message.bot, "controller", None)
    if controller and hasattr(controller, "start"):
        await maybe_await(controller.start())
        await message.reply("Run requested.")
    else:
        await message.reply("Controller.start not available.")


@router.message(F.text == "/stop")
async def cmd_stop(message: types.Message) -> None:
    if not admin_check(message.from_user.id):
        await message.reply("Access denied.")
        return
    controller = getattr(message.bot, "controller", None)
    if controller and hasattr(controller, "stop"):
        await maybe_await(controller.stop())
        await message.reply("Stop requested.")
    else:
        await message.reply("Controller.stop not available.")
