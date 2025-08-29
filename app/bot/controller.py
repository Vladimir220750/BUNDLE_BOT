from __future__ import annotations
import asyncio
import logging
from datetime import datetime, time as dtime
from typing import Optional, Callable
import os
from solders.keypair import Keypair

from aiogram import Bot

# Импорты из твоего core:
from app.core.bablo_bot import Bablo, BabloConfig
from app.core.constants import LAMPORTS_PER_SOL
from app.core.utils import lamports_to_sol  # если потребуется
from app.core.wallet_manager import WalletManager     # у тебя этот класс в utils.py
from app.core.client import SolanaClient     # как в твоих модулях

from .config import AppConfig, save_config
from .telelog import TelegramLogHandler

log = logging.getLogger("tg-controller")

class BabloController:
    """
    Оркестратор: держит конфиг, кошельки, инстанс Bablo, шлёт статусы в ТГ,
    даёт команды start/stop и управляет автозапусками по расписанию.
    """
    def __init__(self, cfg: AppConfig, bot: Bot, admin_chat_id: int):
        self.cfg = cfg
        self.bot = bot
        self.admin_chat_id = admin_chat_id

        # Ссылки на рабочие объекты
        self.wallets: Optional[WalletManager] = None
        self.bablo: Optional[Bablo] = None

        # Фоновые задачи
        self._autorun_task: Optional[asyncio.Task] = None
        self._run_lock = asyncio.Lock()

        # Лог в ТГ
        self._install_telemetry_logger()

    # ---------- Logger to Telegram ----------
    def _install_telemetry_logger(self):
        handler = TelegramLogHandler(
            send_fn=self.bot.send_message,
            chat_id=self.admin_chat_id,
            level=logging.INFO
        )
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        handler.setFormatter(formatter)
        logging.getLogger().addHandler(handler)

    # ---------- Helpers ----------
    async def _send(self, text: str):
        await self.bot.send_message(self.admin_chat_id, text)

    def _build_bablo(self) -> Bablo:
        bc = self.cfg.bablo
        # BabloConfig из твоего core
        bablo_cfg = BabloConfig(
            token_amount_ui=bc.token_amount_ui,
            wsol_amount_ui=bc.wsol_amount_ui,
            profit_threshold_sol=bc.profit_threshold_sol,
            cycle_timeout_sec=bc.cycle_timeout_sec,
            mode=bc.mode,
        )

        # Коллбэки в ТГ
        async def on_status(msg: str):
            await self.bot.send_message(self.admin_chat_id, f"🟢 <b>Status</b>\n{msg}", parse_mode="HTML")

        async def on_alert(msg: str):
            await self.bot.send_message(self.admin_chat_id, f"🟠 <b>Alert</b>\n{msg}", parse_mode="HTML")

        async def get_ca() -> str:
            ca = self.cfg.bablo.last_ca
            if not ca:
                raise RuntimeError("CA не задан. Используй /set_ca <MINT>")
            return ca

        b = Bablo(
            cfg=bablo_cfg,
            on_status=on_status,
            on_alert=on_alert,
            get_ca=get_ca,
        )
        return b

    async def _ensure_wallets(self):
        if self.wallets is None:
            # В твоей базе WalletManager требует SolanaClient
            # Берём такой же endpoint, как использует твой core (Bablo сам делает свой клиент — ок).
            client = SolanaClient  # заглушка если нужна; либо создай экземпляр, если твой SolanaClient класс — не статический
            # Твой WalletManager принимает экземпляр клиента; здесь оставим None если не требуется.
            # Простой путь: сделать WalletManager «ленивым» от твоего кода (он создаёт dev сам).
            self.wallets = WalletManager(client=None)  # type: ignore[arg-type]
        return self.wallets

    # ---------- Public API ----------
    async def set_ca(self, ca: str):
        self.cfg.bablo.last_ca = ca.strip()
        save_config(self.cfg)
        await self._send(f"📌 Установлен CA: <code>{self.cfg.bablo.last_ca}</code>")

    async def set_param(self, key: str, value: str):
        bcfg = self.cfg.bablo
        k = key.lower()

        if k == "token_amount_ui":
            bcfg.token_amount_ui = [int(v) for v in value.replace(",", " ").split()]
        elif k == "wsol_amount_ui":
            bcfg.wsol_amount_ui = [float(v) for v in value.replace(",", " ").split()]
        elif k == "profit":
            bcfg.profit_threshold_sol = float(value)
        elif k == "timeout":
            bcfg.cycle_timeout_sec = int(value)
        elif k == "mode":
            if value not in ("manual", "auto"):
                raise ValueError("mode must be manual|auto")
            bcfg.mode = value
        elif k == "interval":
            bcfg.schedule.interval_sec = int(value)
        elif k == "active":
            # формат HH:MM-HH:MM
            parts = value.split("-")
            if len(parts) != 2:
                raise ValueError("active format: HH:MM-HH:MM")
            bcfg.schedule.active_from = parts[0].strip()
            bcfg.schedule.active_to = parts[1].strip()
        elif k == "autorun":
            flag = value.strip().lower() in ("1", "on", "true", "yes")
            bcfg.schedule.enabled = flag
            # немедленно включить/отключить цикл
            if flag and not self._autorun_task:
                self._autorun_task = asyncio.create_task(self._autorun_loop())
            elif not flag and self._autorun_task:
                self._autorun_task.cancel()
                self._autorun_task = None
        else:
            raise ValueError(f"Неизвестный параметр: {key}")

        save_config(self.cfg)
        await self._send(f"✅ Параметр <b>{key}</b> обновлён.")

    '''async def run_once(self):
        async with self._run_lock:
            if self.bablo is not None and self.bablo._worker_task and not self.bablo._worker_task.done():
                await self._send("⚠️ Уже выполняется цикл. Сначала /stop.")
                return

            # Подготовка Bablo + кошельки
            self.bablo = self._build_bablo()
            wallets = await self._ensure_wallets()
            # подключаем dev в Bablo
            self.bablo.dev = wallets.dev

            # info dump
            await self._send(
                "▶️ Старт цикла\n"
                f"• mode: <code>{self.cfg.bablo.mode}</code>\n"
                f"• token_amount_ui: <code>{self.cfg.bablo.token_amount_ui}</code>\n"
                f"• wsol_amount_ui: <code>{self.cfg.bablo.wsol_amount_ui}</code>\n"
                f"• profit_threshold: <code>{self.cfg.bablo.profit_threshold_sol} SOL</code>\n"
                f"• timeout: <code>{self.cfg.bablo.cycle_timeout_sec}s</code>\n"
                f"• dev pubkey: <code>{wallets.dev_pubkey}</code>"
            )

            # запуск
            self.bablo.start()'''

    async def run_once(self):
        async with self._run_lock:
            if self.bablo is not None and self.bablo._worker_task and not self.bablo._worker_task.done():
                await self._send("⚠️ Уже выполняется цикл. Сначала /stop.")
                return

            self.bablo = self._build_bablo()

            dry = os.getenv("DRY_MODE", "1").lower() in ("1", "true", "on")
            if dry:
                self.bablo.dev = Keypair()
                dev_pub = self.bablo.dev.pubkey()
            else:
                wallets = await self._ensure_wallets()
                self.bablo.dev = wallets.dev
                dev_pub = wallets.dev_pubkey

            await self._send(
                "▶️ Старт цикла\n"
                f"• mode: <code>{self.cfg.bablo.mode}</code>\n"
                f"• token_amount_ui: <code>{self.cfg.bablo.token_amount_ui}</code>\n"
                f"• wsol_amount_ui: <code>{self.cfg.bablo.wsol_amount_ui}</code>\n"
                f"• profit_threshold: <code>{self.cfg.bablo.profit_threshold_sol} SOL</code>\n"
                f"• timeout: <code>{self.cfg.bablo.cycle_timeout_sec}s</code>\n"
                f"• dev pubkey: <code>{dev_pub}</code>"
            )
            self.bablo.start()

    async def stop(self):
        async with self._run_lock:
            if self.bablo is None:
                await self._send("ℹ️ Нет активного цикла.")
                return
            await self.bablo.stop()
            await self._send("⏹ Остановлено.")
            self.bablo = None

    def _within_active_window(self) -> bool:
        sched = self.cfg.bablo.schedule
        def _parse(hhmm: str) -> dtime:
            hh, mm = [int(x) for x in hhmm.split(":")]
            return dtime(hh, mm)
        now = datetime.now().time()
        a, b = _parse(sched.active_from), _parse(sched.active_to)
        if a <= b:
            return a <= now <= b
        # окно через полночь
        return now >= a or now <= b

    async def _autorun_loop(self):
        await self._send("♻️ Авто-режим включён.")
        try:
            while self.cfg.bablo.schedule.enabled:
                if self._within_active_window():
                    await self.run_once()
                    # ждём завершения текущего цикла или таймера
                    if self.bablo and self.bablo._worker_task:
                        try:
                            await self.bablo._worker_task
                        except asyncio.CancelledError:
                            pass
                        self.bablo = None
                # пауза между циклами
                await asyncio.sleep(self.cfg.bablo.schedule.interval_sec)
        except asyncio.CancelledError:
            pass
        finally:
            await self._send("🛑 Авто-режим выключен.")
