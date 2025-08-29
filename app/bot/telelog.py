import logging
import asyncio
from typing import Callable

class TelegramLogHandler(logging.Handler):
    """
    Логгер-Handler, который шлёт сообщения в Telegram через переданный send_fn(chat_id, text).
    Имеет минимальную защиту от спама (очередь и sleep).
    """
    def __init__(self, send_fn: Callable[[int, str], "asyncio.Future"], chat_id: int, level=logging.INFO):
        super().__init__(level=level)
        self.send_fn = send_fn
        self.chat_id = chat_id
        self._lock = asyncio.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            return
        # fire-and-forget в фоне
        asyncio.create_task(self._safe_send(msg))

    async def _safe_send(self, msg: str):
        # простая защита от бурста
        async with self._lock:
            try:
                await self.send_fn(self.chat_id, f"<code>{self._clip(msg)}</code>")
            except Exception:
                pass
            await asyncio.sleep(0.15)

    @staticmethod
    def _clip(s: str, limit: int = 3500) -> str:
        return s if len(s) <= limit else s[:limit] + " …"
