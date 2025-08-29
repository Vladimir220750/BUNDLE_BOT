from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover - fallback if package is absent
    load_dotenv = None

if load_dotenv:
    load_dotenv()


@dataclass
class Settings:
    log_level: str = "INFO"
    bot_token: str = ""
    admin_ids: List[int] = field(default_factory=list)
    dry_mode: bool = True
    wallets_dir: str = "wallets"
    fund_private_key: Optional[str] = None


def _parse_admin_ids(raw: str) -> List[int]:
    ids: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids


def load_settings() -> Settings:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    bot_token = os.getenv("BOT_TOKEN", "")
    admin_raw = os.getenv("ADMIN_IDS", "")
    dry_env = os.getenv("DRY_MODE")
    dry_mode = True if dry_env is None else dry_env.lower() in ("1", "true", "yes", "on")
    wallets_dir = os.getenv("WALLETS_DIR", "wallets")
    fund_private_key = os.getenv("FUND_PRIVATE_KEY") or None
    return Settings(
        log_level=log_level,
        bot_token=bot_token,
        admin_ids=_parse_admin_ids(admin_raw),
        dry_mode=dry_mode,
        wallets_dir=wallets_dir,
        fund_private_key=fund_private_key,
    )


settings = load_settings()
