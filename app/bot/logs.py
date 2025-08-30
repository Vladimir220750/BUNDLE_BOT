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


class TelegramErrorHandler(logging.Handler):
    """Хэндлер, отправляющий сообщения уровня ERROR и выше в Telegram.

    Сообщения группируются, чтобы уменьшить спам: все записи,
    пришедшие за короткий промежуток времени, объединяются в одно
    Telegram-сообщение.
    """

    def __init__(
        self,
        send_fn: Callable[[int, str], "asyncio.Future"],
        chat_id: int,
        level: int = logging.ERROR,
        group_delay: float = 0.5,
    ) -> None:
        super().__init__(level=level)
        self.send_fn = send_fn
        self.chat_id = chat_id
        self.group_delay = group_delay
        self._lock = asyncio.Lock()
        self._buf: list[str] = []
        self._task: asyncio.Task | None = None

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - async fire-and-forget
        if record.levelno < self.level:
            return
        try:
            msg = self.format(record)
        except Exception:
            return
        self._buf.append(msg)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._flush())

    async def _flush(self) -> None:
        await asyncio.sleep(self.group_delay)
        async with self._lock:
            if not self._buf:
                return
            text = "\n".join(self._clip(m) for m in self._buf)
            self._buf.clear()
            try:
                await self.send_fn(self.chat_id, f"<code>{text}</code>")
            except Exception:
                pass

    @staticmethod
    def _clip(s: str, limit: int = 3500) -> str:
        return s if len(s) <= limit else s[:limit] + " …"
