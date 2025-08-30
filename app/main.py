from __future__ import annotations

import argparse
import asyncio
import signal
from typing import Optional

from core.config import settings
from core.bablo_bot import Bablo, BabloConfig
from core.logger import logger as log
from core.cli_config import get_cfg_from_user_cli, ainput

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run_mode", help="Run mode: cli or bot")
    args = parser.parse_args()

    mode = (args.run_mode or settings.run_mode).lower()

    if mode == "bot":
        from app.bot.runner import run as run_bot

        asyncio.run(run_bot())
    else:
        asyncio.run(run_cli())


if __name__ == "__main__":
    main()
