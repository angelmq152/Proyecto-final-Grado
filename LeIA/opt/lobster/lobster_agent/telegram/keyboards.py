from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def approval_keyboard(approval_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Aprobar", callback_data=f"approve:{approval_id}"),
                InlineKeyboardButton(text="Rechazar", callback_data=f"reject:{approval_id}"),
            ],
            [InlineKeyboardButton(text="Pausar todo", callback_data="pause_all")],
        ]
    )
