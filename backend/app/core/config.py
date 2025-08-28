from pydantic import BaseModel, Field
import os
from pathlib import Path

class Settings(BaseModel):
    helius_rpc_url: str = Field(default=os.getenv("HELIUS_RPC_URL", "https://api.mainnet-beta.solana.com"))
    shift_rpc_url: str = Field(default=os.getenv("SHIFT_RPC_URL"))
    raydium_backend: str = Field(default=os.getenv("RAYDIUM_BACKEND"))
    wallets_dir: Path = Field(default=Path(os.getenv("WALLETS_DIR", "/data/wallets")))
    temp_wallets_dir: Path = Field(default=Path(os.getenv("TEMP_WALLETS_DIR", "/data/temp_wallets")))
    archive_wallets_dir: Path = Field(default=Path(os.getenv("ARCHIVE_WALLETS_DIR", "/data/archive_wallets")))
    tmp_dir: Path = Field(default=Path(os.getenv("TMP_DIR", "/data/tmp")))
    allowed_hosts: list[str] = Field(default=os.getenv("ALLOWED_HOSTS", "frontend:5000"))
    log_level: str = Field(default=os.getenv("LOG_LEVEL", "DEBUG"))

settings = Settings()
settings.wallets_dir.mkdir(parents=True, exist_ok=True)
settings.archive_wallets_dir.mkdir(parents=True, exist_ok=True)
settings.tmp_dir.mkdir(parents=True, exist_ok=True)
settings.temp_wallets_dir.mkdir(parents=True, exist_ok=True)
