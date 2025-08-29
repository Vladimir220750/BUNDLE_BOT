#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

# Determine repository root (this file lives at repo root)
REPO_ROOT: Path = Path(__file__).resolve().parent
repo_root_str = str(REPO_ROOT)
if sys.path[0] != repo_root_str:
    sys.path.insert(0, repo_root_str)

import asyncio
import traceback
from typing import Optional

# Try to load .env: prefer app/bot/.env, fallback to repo root .env
try:
    from dotenv import load_dotenv  # type: ignore
    dotenv_path: Optional[Path] = REPO_ROOT / "app" / "bot" / ".env"
    if not dotenv_path.exists():
        dotenv_path = REPO_ROOT / ".env"
    load_dotenv(dotenv_path)
except Exception:
    # dotenv is optional; if it's not installed we just continue relying on env vars
    pass

# Import the async main() from the telegram bot package
try:
    import app.bot.main  # type: ignore
except Exception:
    print("Failed to import app.bot.main — diagnostic info follows:", file=sys.stderr)
    print("Repository root used for imports:", repo_root_str, file=sys.stderr)
    print("Current working directory:", Path.cwd(), file=sys.stderr)
    print("sys.path (first 5 entries):", sys.path[:5], file=sys.stderr)
    traceback.print_exc()
    raise

if __name__ == "__main__":
    # Run the async bot entrypoint
    asyncio.run(app.bot.main.main())
