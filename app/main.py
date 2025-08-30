from __future__ import annotations

import os
import asyncio
import signal
import logging
from typing import Optional

from core.config import settings
from core.bablo_bot import Bablo, BabloConfig
from core.logger import logger as log
from core.cli_config import get_cfg_from_user_cli, ainput

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from bot.logs import TelegramErrorHandler

_ca_queue: asyncio.Queue[str] = asyncio.Queue()


def _install_signal_handlers(stop_event: asyncio.Event) -> bool:
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
        return True
    except (NotImplementedError, RuntimeError):
        return False

async def on_status(text: str):
    log.info(text)

async def on_alert(text: str):
    log.error(text)

async def get_ca_manual() -> str:
    ca = await _ca_queue.get()
    return ca

async def get_ca_auto() -> Optional[str]:
    return None

def build_bablo(cfg: BabloConfig) -> Bablo:
    b = Bablo(
        cfg=cfg,
        on_status=on_status,
        on_alert=on_alert,
        get_ca=get_ca_manual,
        get_ca_auto=get_ca_auto,
    )
    return b

async def run_cli():
    log.info("RUN_MODE=cli. Type 'help' for commands.")
    bablo = build_bablo(
        await get_cfg_from_user_cli(
            BabloConfig(
                token_amount_ui=[1000, 900, 800, 700],
                wsol_amount_ui=[5,4,3,2],
                profit_threshold_sol=0.05,
                cycle_timeout_sec=5,
                mode="manual",
                auto_sleep_sec=300
            )
        )
    )

    stop_event = asyncio.Event()
    has_signals = _install_signal_handlers(stop_event)

    bablo.start()

    try:
        while not stop_event.is_set():
            try:
                cmd = (await ainput("> ")).strip()
            except KeyboardInterrupt:
                stop_event.set()
                break

            if not cmd:
                continue

            parts = cmd.split()
            head = parts[0].lower()

            if head in ("quit", "exit"):
                break

            if head == "help":
                print(
                    "commands:\n"
                    "  start                  - start bablo loop\n"
                    "  stop                   - stop bablo loop\n"
                    "  ca <MINT>              - push contract address for manual mode\n"
                    "  mode manual|auto       - change bablo mode (applies next idle)\n"
                    "  status                 - print brief status\n"
                    "  exit                   - quit\n"
                    "  withdraw               - withdraw from dev to fund\n"
                )
                continue

            if head == "start":
                bablo.start()
                print("bablo started")
                continue

            if head == "stop":
                await bablo.stop()
                print("bablo stopped")
                continue

            if head == "status":
                cfg = bablo.get_config()
                print(f"mode={cfg.mode}  token_amounts={cfg.token_amount_ui}  wsol_amounts={cfg.wsol_amount_ui}")
                continue

            if head == "mode" and len(parts) >= 2:
                new_mode = parts[1].lower()
                await bablo.stop()
                new_cfg = bablo.get_config()
                new_cfg.mode = new_mode
                bablo.set_config(new_cfg)
                print(f"mode set to {new_mode}")
                continue

            if head == "ca" and len(parts) >= 2:
                mint = parts[1]
                await _ca_queue.put(mint)
                print(f"queued CA: {mint}")
                continue

            if head == "withdraw":
                await bablo.handle_withdraw_to_fund()
                print("withdraw")
                continue

            print("unknown command. Type 'help'.")
    finally:
        await bablo.stop()
        log.info("CLI stopped.")

async def run_bot():
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN not provided in env")

    bot = Bot(token=settings.bot_token, parse_mode=None)
    dp = Dispatcher()

    bablo = build_bablo()
    status_chat_id: Optional[int] = None
    log_handler: Optional[logging.Handler] = None

    async def bot_on_status(text: str):
        await on_status(text)

    async def bot_on_alert(text: str):
        nonlocal status_chat_id
        await on_alert(text)
        if status_chat_id:
            try:
                await bot.send_message(status_chat_id, f"⚠️ {text}")
            except Exception:
                pass

    bablo.on_status = bot_on_status
    bablo.on_alert = bot_on_alert

    @dp.message(Command("start"))
    async def cmd_start(m: Message):
        nonlocal status_chat_id, log_handler
        status_chat_id = m.chat.id
        await m.answer("hi. use /start_bablo, /stop_bablo, /status, /mode <manual|auto>, /ca <mint>")
        if log_handler is None:
            handler = TelegramErrorHandler(bot.send_message, status_chat_id)
            logging.getLogger("app.core").addHandler(handler)
            log_handler = handler
        await bot_on_status("Linked chat for status updates.")

    @dp.message(Command("status"))
    async def cmd_status(m: Message):
        cfg = bablo.get_config()
        await m.answer(
            f"mode={cfg.mode}\n"
            f"token_amounts={cfg.token_amount_ui}\n"
            f"wsol_amounts={cfg.wsol_amount_ui}\n"
            f"profit_threshold={cfg.profit_threshold_sol}\n"
            f"timeout={cfg.cycle_timeout_sec}s\n"
            f"auto_sleep={cfg.auto_sleep_sec}s"
        )

    @dp.message(Command("start_bablo"))
    async def cmd_start_bablo(m: Message):
        bablo.start()
        await m.answer("bablo started")

    @dp.message(Command("stop_bablo"))
    async def cmd_stop_bablo(m: Message):
        await bablo.stop()
        await m.answer("bablo stopped")

    @dp.message(Command("mode"))
    async def cmd_mode(m: Message):
        args = (m.text or "").split()
        if len(args) < 2:
            await m.answer("usage: /mode manual|auto")
            return
        await bablo.stop()
        cfg = bablo.get_config()
        cfg.mode = args[1].lower()
        bablo.set_config(cfg)
        await m.answer(f"mode set to {cfg.mode}")

    @dp.message(F.text.regexp(r"^/ca\s+([1-9A-HJ-NP-Za-km-z]{32,44})$"))
    async def cmd_ca(m: Message):
        mint = m.text.split()[1]
        await _ca_queue.put(mint)
        await m.answer(f"queued CA: {mint}")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    bablo.start()
    try:
        await dp.start_polling(bot, stop_signal=stop_event.wait())
    finally:
        await bablo.stop()
        log.info("Bot stopped.")

def main():
    if settings.run_mode.lower() == "bot":
        asyncio.run(run_bot())
    else:
        asyncio.run(run_cli())


if __name__ == "__main__":
    main()
