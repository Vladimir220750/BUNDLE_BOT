from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import yaml
import os
import html

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

# импорт SETTINGS (админы) — предполагается, что bot/settings.py экспортирует SETTINGS
try:
    from .settings import SETTINGS
except Exception:
    SETTINGS = None

router = Router()  # этот router должен быть зарегистрирован в main.py / dp.include_router(...)


# ---- States ----
class EditState(StatesGroup):
    waiting_for_value = State()
    waiting_for_ca = State()


# ---- Helpers ----
def admin_check(user_id: int) -> bool:
    if not SETTINGS:
        return False
    return user_id in getattr(SETTINGS, "admin_ids", [])


def main_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Status", callback_data="action:status"),
         InlineKeyboardButton(text="⚙️ Show config", callback_data="action:show_config")],
        [InlineKeyboardButton(text="📝 Set CA", callback_data="action:set_ca"),
         InlineKeyboardButton(text="🔧 Set param", callback_data="action:choose_param")],
        [InlineKeyboardButton(text="▶️ Run", callback_data="action:run"),
         InlineKeyboardButton(text="⏹ Stop", callback_data="action:stop")],
        [InlineKeyboardButton(text="🔁 Toggle autorun", callback_data="action:toggle_autorun")],
    ])
    return kb


def params_keyboard() -> InlineKeyboardMarkup:
    # перечисли параметры, которые ожидаешь менять
    choices = [
        ("token_amount_ui", "token_amount_ui"),
        ("wsol_amount_ui", "wsol_amount_ui"),
        ("profit", "profit"),
        ("timeout", "timeout"),
        ("interval", "interval"),
        ("mode", "mode"),
        ("active_hours", "active_hours"),
    ]
    rows = []
    for label, key in choices:
        rows.append([InlineKeyboardButton(text=label, callback_data=f"param:{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="action:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _apply_config(controller, key: str, value: str) -> tuple[bool, str]:
    """
    Try several ways to apply config:
    1) If controller has update_config(key, value) -> call it
    2) else: try to mutate controller.cfg (if attribute exists)
    3) fallback: try to set controller.cfg.__dict__[key] = casted_value
    Returns (success, message)
    """
    # Try controller.update_config
    try:
        if hasattr(controller, "update_config"):
            await maybe_await(controller.update_config(key, value))
            return True, f"Param <b>{html.escape(key)}</b> updated via controller.update_config."
    except Exception as e:
        return False, f"update_config failed: {html.escape(str(e))}"

    # Fallback: direct cfg edit
    try:
        cfg = getattr(controller, "cfg", None)
        if cfg is None:
            return False, "Controller has no cfg attribute; cannot apply."
        # Try to coerce numeric types simply
        cast_val = cast_string_to_type(value)
        if hasattr(cfg, key):
            setattr(cfg, key, cast_val)
            return True, f"Param <b>{html.escape(key)}</b> set to <code>{html.escape(str(value))}</code> on cfg."
        else:
            # if cfg is dataclass with dict-like fields, try set anyway
            try:
                setattr(cfg, key, cast_val)
                return True, f"Param <b>{html.escape(key)}</b> created/updated on cfg."
            except Exception as e:
                return False, f"Cannot set attribute {html.escape(key)} on cfg: {html.escape(str(e))}"
    except Exception as e:
        return False, f"Failed to apply config: {html.escape(str(e))}"


def cast_string_to_type(s: str):
    s = s.strip()
    # integers
    if s.isdigit():
        return int(s)
    # float
    try:
        if "." in s:
            return float(s)
    except Exception:
        pass
    # boolean
    if s.lower() in ("true", "1", "yes", "on"):
        return True
    if s.lower() in ("false", "0", "no", "off"):
        return False
    # lists (space or comma separated)
    if " " in s or "," in s:
        parts = [p.strip() for p in (s.replace(",", " ").split()) if p.strip()]
        # try numeric list conversion
        converted = []
        for p in parts:
            if p.isdigit():
                converted.append(int(p))
            else:
                try:
                    converted.append(float(p))
                except Exception:
                    converted.append(p)
        return converted
    return s


async def maybe_await(maybe_awaitable):
    if hasattr(maybe_awaitable, "__await__"):
        return await maybe_awaitable
    return maybe_awaitable


# ---- Commands ----
@router.message(Command(commands=["start"]))
async def cmd_start(m: types.Message, state: FSMContext):
    if not admin_check(m.from_user.id):
        await m.reply("Access denied.")
        return
    text = (
        "<b>Pump.fun Volume Controller</b>\n\n"
        "Команды:\n"
        "/status — показать конфиг\n"
        "/set_ca <code>&lt;MINT&gt;</code> — задать исходный CA\n"
        "/set <code>&lt;key&gt;</code> <code>&lt;value&gt;</code> — обновить параметр (можно задавать через кнопки)\n"
        "/run — запустить один цикл\n"
        "/stop — остановить текущий цикл\n\n"
        "Или используйте меню ниже."
    )
    await m.reply(text, reply_markup=main_menu_kb(), parse_mode="HTML")
    await state.clear()


@router.callback_query(lambda c: c.data and c.data.startswith("action:"))
async def cb_main_actions(query: types.CallbackQuery, state: FSMContext):
    if not admin_check(query.from_user.id):
        await query.answer("Access denied.", show_alert=True)
        return
    action = query.data.split(":", 1)[1]

    # try to obtain controller from bot/dispatcher context
    try:
        controller = query.bot["controller"]
    except Exception:
        controller = None

    if action == "status":
        # try to get state from controller
        if controller and hasattr(controller, "status"):
            try:
                st = await maybe_await(controller.status())
                await query.message.reply(f"<b>Status:</b>\n<pre>{html.escape(str(st))}</pre>", parse_mode="HTML")
                await query.answer()
                return
            except Exception as e:
                # fallthrough to fallback
                await query.message.reply(f"Error retrieving status: {html.escape(str(e))}")
                await query.answer()
                return
        # fallback: print cfg if present
        cfg = getattr(controller, "cfg", None)
        await query.message.reply(f"<b>Controller:</b>\n<pre>{html.escape(str(cfg))}</pre>", parse_mode="HTML")
        await query.answer()
        return

    if action == "show_config":
        cfg = getattr(controller, "cfg", None)
        await query.message.reply(f"<b>Config:</b>\n<pre>{html.escape(str(cfg))}</pre>", parse_mode="HTML")
        await query.answer()
        return

    if action == "set_ca":
        await query.message.reply("Send CA / original mint address (single line).")
        await state.set_state(EditState.waiting_for_ca)
        await query.answer()
        return

    if action == "choose_param":
        await query.message.edit_text("Выберите параметр для редактирования:", reply_markup=params_keyboard())
        await query.answer()
        return

    if action == "run":
        if controller and hasattr(controller, "start"):
            try:
                await maybe_await(controller.start())
                await query.message.reply("Controller.start() called.")
                await query.answer()
                return
            except Exception as e:
                await query.message.reply(f"Error calling start(): {html.escape(str(e))}")
                await query.answer()
                return
        await query.message.reply("No controller.start available.")
        await query.answer()
        return

    if action == "stop":
        if controller and hasattr(controller, "stop"):
            try:
                await maybe_await(controller.stop())
                await query.message.reply("Controller.stop() called.")
                await query.answer()
                return
            except Exception as e:
                await query.message.reply(f"Error calling stop(): {html.escape(str(e))}")
                await query.answer()
                return
        await query.message.reply("No controller.stop available.")
        await query.answer()
        return

    if action == "toggle_autorun":
        if controller and hasattr(controller, "cfg"):
            try:
                cfg = controller.cfg
                autorun = getattr(cfg, "autorun", False)
                new = not autorun
                try:
                    setattr(cfg, "autorun", new)
                except Exception:
                    pass
                await query.message.reply(f"Autorun set to: {html.escape(str(new))}")
                await query.answer()
                return
            except Exception as e:
                await query.message.reply(f"Error toggling autorun: {html.escape(str(e))}")
                await query.answer()
                return
        await query.message.reply("Controller configuration not available.")
        await query.answer()
        return

    if action == "back":
        await query.message.edit_text("Main menu", reply_markup=main_menu_kb())
        await query.answer()
        return

    await query.answer("Unknown action", show_alert=True)


@router.callback_query(lambda c: c.data and c.data.startswith("param:"))
async def cb_param_choose(query: types.CallbackQuery, state: FSMContext):
    if not admin_check(query.from_user.id):
        await query.answer("Access denied.", show_alert=True)
        return
    key = query.data.split(":", 1)[1]
    await state.update_data(param_key=key)
    await state.set_state(EditState.waiting_for_value)
    await query.message.reply(
        f"Send new value for <b>{html.escape(key)}</b>. You can send numbers, strings or lists (space/comma separated).",
        parse_mode="HTML"
    )
    await query.answer()


@router.message(EditState.waiting_for_value)
async def receive_param_value(m: types.Message, state: FSMContext):
    if not admin_check(m.from_user.id):
        await m.reply("Access denied.")
        await state.clear()
        return
    data = await state.get_data()
    key = data.get("param_key")
    if not key:
        await m.reply("Internal error: no param in state.")
        await state.clear()
        return

    # get controller from dispatcher context
    controller = m.bot.get("controller")  # requires dp["controller"] set in main
    success, msg = await _apply_config(controller, key, m.text)
    # always escape the returned message
    await m.reply(html.escape(msg), parse_mode="HTML")
    await state.clear()


@router.message(EditState.waiting_for_ca)
async def receive_ca(m: types.Message, state: FSMContext):
    if not admin_check(m.from_user.id):
        await m.reply("Access denied.")
        await state.clear()
        return
    ca = m.text.strip()
    controller = m.bot.get("controller")
    # prefer controller.set_ca if exists
    if controller and hasattr(controller, "set_ca"):
        try:
            await maybe_await(controller.set_ca(ca))
            await m.reply(f"CA set to <code>{html.escape(ca)}</code> via controller.set_ca()", parse_mode="HTML")
            await state.clear()
            return
        except Exception as e:
            await m.reply(f"set_ca failed: {html.escape(str(e))}")
    # fallback: set in cfg
    if controller and hasattr(controller, "cfg"):
        try:
            setattr(controller.cfg, "default_ca", ca)
            await m.reply(f"CA set to <code>{html.escape(ca)}</code> on controller.cfg", parse_mode="HTML")
            await state.clear()
            return
        except Exception as e:
            await m.reply(f"Failed to set CA on cfg: {html.escape(str(e))}")
            await state.clear()
            return

    await m.reply("No controller available to set CA.")
    await state.clear()


# ---- Simple textual commands (helpful) ----
@router.message(Command(commands=["status"]))
async def cmd_status(m: types.Message):
    if not admin_check(m.from_user.id):
        await m.reply("Access denied.")
        return
    controller = m.bot.get("controller")
    if controller and hasattr(controller, "status"):
        try:
            st = await maybe_await(controller.status())
            await m.reply(f"<pre>{html.escape(str(st))}</pre>", parse_mode="HTML")
            return
        except Exception as e:
            await m.reply(f"Error retrieving status: {html.escape(str(e))}")
            return
    await m.reply(f"Controller cfg: <pre>{html.escape(str(getattr(controller,'cfg',None)))}</pre>", parse_mode="HTML")


@router.message(Command(commands=["run"]))
async def cmd_run(m: types.Message):
    if not admin_check(m.from_user.id):
        await m.reply("Access denied.")
        return
    controller = m.bot.get("controller")
    if controller and hasattr(controller, "start"):
        await maybe_await(controller.start())
        await m.reply("Run requested.")
    else:
        await m.reply("Controller.start not available.")


@router.message(Command(commands=["stop"]))
async def cmd_stop(m: types.Message):
    if not admin_check(m.from_user.id):
        await m.reply("Access denied.")
        return
    controller = m.bot.get("controller")
    if controller and hasattr(controller, "stop"):
        await maybe_await(controller.stop())
        await m.reply("Stop requested.")
    else:
        await m.reply("Controller.stop not available.")
