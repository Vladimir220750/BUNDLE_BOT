from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

class Settings(BaseModel):
    fund_private_key: str = Field(default=os.getenv("FUND_PRIVATE_KEY", ""))
    wallets_dir: Path = Field(default=Path(os.getenv("WALLETS_DIR", "./wallets")))
    run_mode: str = Field(default=os.getenv("RUN_MODE", "cli"))
    bot_token: str = Field(default=os.getenv("BOT_TOKEN", ""))
    log_level: str = Field(default=os.getenv("LOG_LEVEL", "INFO"))

settings = Settings()
settings.wallets_dir.mkdir(parents=True, exist_ok=True)
