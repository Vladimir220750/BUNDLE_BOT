import os
from dataclasses import dataclass
from typing import List
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    bot_token: str
    admin_ids: List[int]
    log_level: str
    default_ca: str | None

def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is required in environment")

    admin_ids_raw = os.getenv("ADMIN_IDS", "").strip()
    if not admin_ids_raw:
        raise RuntimeError("ADMIN_IDS (comma-separated) is required")

    admin_ids = []
    for part in admin_ids_raw.split(","):
        part = part.strip()
        if not part:
            continue
        admin_ids.append(int(part))

    return Settings(
        bot_token=token,
        admin_ids=admin_ids,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        default_ca=os.getenv("DEFAULT_CA") or None,
    )

SETTINGS = load_settings()
