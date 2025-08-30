# app/core/ws_hub.py
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Awaitable, Callable, Optional

import websockets
from .constants import HELIUS_WSS

log = logging.getLogger(__name__)

LamportsHandler = Callable[[int], Awaitable[None]]  # async def on_change(lamports:int)->None

class WsHub:
    def __init__(self, url: str | None = None):
        self._url = url or HELIUS_WSS
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

    def start(self, pubkey: str, on_change: LamportsHandler, *, commitment: str = "processed"):
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(
            self._runner(pubkey, on_change, commitment=commitment, stop_event=self._stop),
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

    async def monitor_account_lamports(
        self,
        pubkey: str,
        *,
        on_change: LamportsHandler,
        commitment: str = "processed",
        stop_event: Optional[asyncio.Event] = None,
    ):
        await self._runner(pubkey, on_change, commitment=commitment, stop_event=stop_event)

    async def _runner(
        self,
        pubkey: str,
        on_change: LamportsHandler,
        *,
        commitment: str,
        stop_event: Optional[asyncio.Event],
    ):
        backoff_min, backoff_max = 0.5, 10.0
        stop_event = stop_event or asyncio.Event()

        while not stop_event.is_set():
            try:
                async with websockets.connect(self._url, ping_interval=None, close_timeout=2.0) as ws:
                    log.info("[WS] connected → %s", self._url)
                    await self._subscribe_account(ws, pubkey, commitment)
                    log.info("[WS] subscribed account=%s (%s)", pubkey, commitment)

                    reader = asyncio.create_task(self._read_loop(ws, pubkey, on_change, stop_event))
                    pinger = asyncio.create_task(self._ping_loop(ws, stop_event))

                    done, pending = await asyncio.wait({reader, pinger}, return_when=asyncio.FIRST_COMPLETED)
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
                if stop_event.is_set():
                    break
                step = random.uniform(1.5, 2.2)
                delay = min(backoff_max, backoff_min * step)
                log.warning("[WS] error: %s | reconnect in %.1fs", e, delay)
                await asyncio.sleep(delay)

    @staticmethod
    async def _subscribe_account(ws, pubkey: str, commitment: str):
        await ws.send(json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "accountSubscribe",
            "params": [pubkey, {"encoding": "jsonParsed", "commitment": commitment}],
        }))

    @staticmethod
    async def _read_loop(ws, pubkey: str, on_change: LamportsHandler, stop_event: asyncio.Event):
        while not stop_event.is_set():
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
            try:
                msg = json.loads(raw)
                params = msg.get("params")
                if not params:
                    continue
                value = params.get("result", {}).get("value", {})
                lamports = value.get("lamports")
                if lamports is None:
                    continue
                await on_change(lamports)
            except Exception as e:
                log.error("[WS] handler error for %s: %s", pubkey, e)

    @staticmethod
    async def _ping_loop(ws, stop_event: asyncio.Event, *, interval: float = 20.0):
        tick = 0.5
        elapsed = 0.0
        while not stop_event.is_set():
            if elapsed >= interval:
                try:
                    await ws.ping()
                except Exception:
                    break
                elapsed = 0.0
            await asyncio.sleep(tick)
            elapsed += tick
