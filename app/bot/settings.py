"""Telegram bot specific settings."""

from __future__ import annotations

import os
from typing import List, Optional

from pydantic import Field

from app.core.config import Settings as CoreSettings


def _parse_admin_ids(raw: str | None) -> List[int]:
    """Parse comma/space separated list of integers."""
    if not raw:
        return []
    items: List[int] = []
    for part in raw.replace(",", " ").split():
        part = part.strip()
        if part:
            try:
                items.append(int(part))
            except ValueError:
                continue
    return items


class Settings(CoreSettings):
    """Extend core settings with Telegram specific fields."""

    bot_token: str = Field(
        default=os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN", "")
    )
    boot_chat_id: Optional[int] = Field(
        default=(int(os.getenv("TELEGRAM_BOOT_CHAT_ID"))
                 if os.getenv("TELEGRAM_BOOT_CHAT_ID")
                 else None)
    )
    admin_ids: List[int] = Field(
        default_factory=lambda: _parse_admin_ids(os.getenv("TELEGRAM_ADMIN_IDS"))
    )


def load_settings() -> Settings:
    return Settings()


SETTINGS = load_settings()

