"""Utilities for bot storage.

This module serves two purposes:

1. Provide FSM states and admin checks used by the bot handlers.
2. Persist a list of contract addresses so they survive bot restarts.

The path to the file used for storing contracts is configurable via the
``CONTRACTS_STORAGE_PATH`` environment variable.
"""

from pathlib import Path
from typing import List
import os

from aiogram.fsm.state import StatesGroup, State

try:
    from .settings import SETTINGS
except Exception:  # pragma: no cover - SETTINGS may be optional during tests
    SETTINGS = None


# --------- Contracts storage utilities ---------

CONTRACTS_STORAGE_PATH = Path(os.getenv("CONTRACTS_STORAGE_PATH", "contracts.txt"))


def load_contracts() -> List[str]:
    """Load list of contract addresses from ``CONTRACTS_STORAGE_PATH``.

    Returns an empty list if the file does not exist.
    """

    if not CONTRACTS_STORAGE_PATH.exists():
        return []

    with CONTRACTS_STORAGE_PATH.open("r", encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip()]


def save_contracts(contracts: List[str]) -> None:
    """Persist list of contract addresses to ``CONTRACTS_STORAGE_PATH``."""

    CONTRACTS_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONTRACTS_STORAGE_PATH.open("w", encoding="utf-8") as fh:
        for ca in contracts:
            fh.write(ca.strip() + "\n")


class EditState(StatesGroup):
    """Состояния для ввода параметров и CA."""
    waiting_for_value = State()
    waiting_for_ca = State()


def admin_check(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором."""
    if not SETTINGS:
        return False
    return user_id in getattr(SETTINGS, "admin_ids", [])
