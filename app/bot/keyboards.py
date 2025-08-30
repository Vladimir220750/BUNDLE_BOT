from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_kb() -> InlineKeyboardMarkup:
    """Основное меню бота."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Status", callback_data="action:status"),
            InlineKeyboardButton(text="⚙️ Show config", callback_data="action:show_config"),
        ],
        [
            InlineKeyboardButton(text="📝 Set CA", callback_data="action:set_ca"),
            InlineKeyboardButton(text="🔧 Set param", callback_data="action:choose_param"),
        ],
        [
            InlineKeyboardButton(text="▶️ Run", callback_data="action:run"),
            InlineKeyboardButton(text="⏹ Stop", callback_data="action:stop"),
        ],
        [InlineKeyboardButton(text="🔁 Toggle autorun", callback_data="action:toggle_autorun")],
    ])


def params_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с параметрами для редактирования."""
    choices = [
        ("token_amount_ui", "token_amount_ui"),
        ("wsol_amount_ui", "wsol_amount_ui"),
        ("profit", "profit"),
        ("timeout", "timeout"),
        ("interval", "interval"),
        ("mode", "mode"),
        ("active_hours", "active_hours"),
    ]
    rows = [[InlineKeyboardButton(text=label, callback_data=f"param:{key}")] for label, key in choices]
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="action:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
