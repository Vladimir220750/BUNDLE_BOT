from aiogram.fsm.state import StatesGroup, State

try:
    from .settings import SETTINGS
except Exception:  # pragma: no cover - SETTINGS may be optional during tests
    SETTINGS = None


class EditState(StatesGroup):
    """Состояния для ввода параметров и CA."""
    waiting_for_value = State()
    waiting_for_ca = State()


def admin_check(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором."""
    if not SETTINGS:
        return False
    return user_id in getattr(SETTINGS, "admin_ids", [])
