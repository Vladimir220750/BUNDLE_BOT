#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import sys
import traceback
from pathlib import Path
from typing import Optional

# Determine repository root in a robust way:
# - If this file is inside ".../repo/app/main.py" then repo root is parent of "app"
# - Otherwise repo root is the directory containing this file
HERE: Path = Path(__file__).resolve().parent
if HERE.name == "app":
    REPO_ROOT: Path = HERE.parent
else:
    REPO_ROOT = HERE

# Ensure repo root is first in sys.path so `import app...` works regardless of cwd
repo_root_str = str(REPO_ROOT)
if sys.path[0] != repo_root_str:
    sys.path.insert(0, repo_root_str)

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
    # app.bot.main is expected to provide: async def main()
    from app.bot.main import main as bot_main  # type: ignore
except Exception as exc:
    print("Failed to import app.bot.main — diagnostic info follows:", file=sys.stderr)
    print("Repository root used for imports:", repo_root_str, file=sys.stderr)
    print("Current working directory:", Path.cwd(), file=sys.stderr)
    print("sys.path (first 5 entries):", sys.path[:5], file=sys.stderr)
    traceback.print_exc()
    raise

if __name__ == "__main__":
    # Run the async bot entrypoint
    asyncio.run(bot_main())
