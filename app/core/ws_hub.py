from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Awaitable, Callable, Optional

import websockets
from .constants import HELIUS_WSS

log = logging.getLogger(__name__)

LamportsHandler = Callable[[int], Awaitable[None]]

class WsHub:
    """
    Подписка на изменения аккаунта через Helius WebSocket:
      - monitor_account_lamports(pubkey, on_change): следит за lamports и вызывает on_change при каждом изменении
      - stop(): мягкая остановка, разрывает WS и отменяет фоновые задачи
    Надёжность:
      - авто-реконнект с экспоненциальным backoff
      - heartbeat ping/pong
      - игнор дублей (скользящее предыдущее значение)
    """
    def __init__(self):
        self._url = HELIUS_WSS
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

    def start(self, pubkey: str, on_change: LamportsHandler, *, commitment: str = "processed", emit_initial: bool = True):
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(
            self._runner(pubkey, on_change, commitment=commitment, emit_initial=emit_initial),
            name=f"ws-hub-{pubkey[:6]}",
        )

    async def stop(self):
        self._stop.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def monitor_account_lamports(self, pubkey: str, *, on_change: LamportsHandler,
                                       commitment: str = "processed", emit_initial: bool = True):
        await self._runner(pubkey, on_change, commitment=commitment, emit_initial=emit_initial)


    async def _runner(self, pubkey: str, on_change: LamportsHandler, *, commitment: str, emit_initial: bool):
        backoff_min, backoff_max = 0.5, 10.0
        prev_lamports: Optional[int] = None

        while not self._stop.is_set():
            try:
                async with websockets.connect(self._url, ping_interval=None, close_timeout=2.0) as ws:
                    log.info("[WS] connected → %s", self._url)
                    await self._subscribe_account(ws, pubkey, commitment=commitment)
                    log.info("[WS] subscribed account=%s (commitment=%s)", pubkey, commitment)

                    if emit_initial:
                        pass

                    reader = asyncio.create_task(self._read_loop(ws, pubkey, on_change, lambda v: self._should_emit(v, prev_lamports)))
                    pinger = asyncio.create_task(self._ping_loop(ws))

                    done, pending = await asyncio.wait(
                        {reader, pinger},
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    for t in pending:
                        t.cancel()
                        try:
                            await t
                        except asyncio.CancelledError:
                            pass

                    if reader.done() and not reader.cancelled():
                        exc = reader.exception()
                        if exc:
                            raise exc

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._stop.is_set():
                    break
                delay = min(backoff_max, backoff_min * (1.7 ** random.randint(1, 4)))
                log.warning("[WS] error: %s | reconnect in %.1fs", e, delay)
                await asyncio.sleep(delay)

    async def _subscribe_account(self, ws, pubkey: str, *, commitment: str):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "accountSubscribe",
            "params": [
                pubkey,
                {"encoding": "jsonParsed", "commitment": commitment}
            ],
        }
        await ws.send(json.dumps(payload))

    async def _read_loop(self, ws, pubkey: str, on_change: LamportsHandler, should_emit) -> None:
        prev: Optional[int] = None
        async for raw in ws:
            if self._stop.is_set():
                break
            try:
                msg = json.loads(raw)
            except Exception:
                continue

            params = msg.get("params")
            if not params:
                continue
            value = params.get("result", {}).get("value", {})
            lamports = value.get("lamports")
            if lamports is None:
                continue

            if should_emit(lamports):
                prev = lamports
                try:
                    await on_change(lamports)
                except Exception as e:
                    log.error("[WS] handler error for %s: %s", pubkey, e)

    async def _ping_loop(self, ws, *, interval: float = 20.0):
        """
        Heartbeat-пинги с таймаутом, чтобы ловить тихие обрывы.
        """
        while not self._stop.is_set():
            try:
                await ws.ping()
            except Exception:
                break
            await asyncio.sleep(interval)

    @staticmethod
    def _should_emit(current: int, prev: Optional[int]) -> bool:
        # если предыдущего нет — эмитим; иначе — только при изменении.
        return prev is None or current != prev
