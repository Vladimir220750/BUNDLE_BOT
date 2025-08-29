from __future__ import annotations
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums.parse_mode import ParseMode

from .settings import SETTINGS
from .controller import BabloController
from .config import load_config

router = Router()

def _is_admin(message: Message) -> bool:
    uid = message.from_user.id if message.from_user else 0
    return uid in SETTINGS.admin_ids

def admin_required(func):
    async def wrapper(message: Message, controller: BabloController, *args, **kwargs):
        if not _is_admin(message):
            await message.answer("🚫 Access denied.")
            return
        return await func(message, controller, *args, **kwargs)
    return wrapper

@router.message(Command("start", "help"))
async def cmd_start(message: Message):
    if not _is_admin(message):
        await message.answer("👋 Hi! You are not allowed here.")
        return
    text = (
        "<b>Pump.fun Volume Controller</b>\n\n"
        "<b>Команды:</b>\n"
        "/status — показать конфиг\n"
        "/set_ca &lt;MINT&gt; — задать исходный CA\n"
        "/set &lt;key&gt; &lt;value&gt; — обновить параметр (см. ниже)\n"
        "/run — запустить один цикл\n"
        "/stop — остановить текущий цикл\n\n"
        "<b>Параметры /set:</b>\n"
        "token_amount_ui 10 20 50\n"
        "wsol_amount_ui 0.2 0.3\n"
        "profit 0.05\n"
        "timeout 120\n"
        "mode manual|auto\n"
        "interval 600\n"
        "active 09:00-23:00\n"
        "autorun on|off\n"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)

@router.message(Command("status"))
@admin_required
async def cmd_status(message: Message, controller: BabloController):
    cfg = controller.cfg.bablo
    dev = controller.wallets.dev_pubkey if controller.wallets else "—"
    text = (
        "<b>Текущая конфигурация</b>\n"
        f"CA: <code>{cfg.last_ca or '—'}</code>\n"
        f"mode: <code>{cfg.mode}</code>\n"
        f"token_amount_ui: <code>{cfg.token_amount_ui}</code>\n"
        f"wsol_amount_ui: <code>{cfg.wsol_amount_ui}</code>\n"
        f"profit_threshold_sol: <code>{cfg.profit_threshold_sol}</code>\n"
        f"cycle_timeout_sec: <code>{cfg.cycle_timeout_sec}</code>\n"
        f"autorun: <code>{'on' if cfg.schedule.enabled else 'off'}</code>\n"
        f"interval: <code>{cfg.schedule.interval_sec}s</code>\n"
        f"active: <code>{cfg.schedule.active_from}-{cfg.schedule.active_to}</code>\n"
        f"dev pubkey: <code>{dev}</code>\n"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)

@router.message(Command("set_ca"))
@admin_required
async def cmd_set_ca(message: Message, controller: BabloController):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Формат: /set_ca <MINT>")
        return
    await controller.set_ca(parts[1].strip())

@router.message(Command("set"))
@admin_required
async def cmd_set(message: Message, controller: BabloController):
    # /set key value...
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Формат: /set <key> <value>")
        return
    key, value = parts[1], parts[2]
    try:
        await controller.set_param(key, value)
        await cmd_status(message, controller)
    except Exception as e:
        await message.answer(f"❌ {e}")

@router.message(Command("run"))
@admin_required
async def cmd_run(message: Message, controller: BabloController):
    await controller.run_once()

@router.message(Command("stop"))
@admin_required
async def cmd_stop(message: Message, controller: BabloController):
    await controller.stop()
