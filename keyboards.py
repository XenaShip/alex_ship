from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def kb_start(items: list[tuple[str, str]]):
    """
    Стартовый экран
    """
    if len(items) == 1:
        _, slug = items[0]
        return InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="🚀 Начать опрос",
                    callback_data=f"pick:{slug}"
                )
            ]]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="📋 Выбрать опрос",
                callback_data="menu"
            )
        ]]
    )


def kb_surveys(items: list[tuple[str, str]]):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=name,
                    callback_data=f"pick:{slug}"
                )
            ]
            for name, slug in items
        ]
    )


def kb_yes_no(qid: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="Да", callback_data=f"yn:{qid}:yes"),
            InlineKeyboardButton(text="Нет", callback_data=f"yn:{qid}:no"),
        ]]
    )


def kb_one_of_many(qid: int, options: list[str]):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=opt,
                    callback_data=f"one:{qid}:{opt}"
                )
            ]
            for opt in options
        ]
    )


def kb_multi(qid: int, options: list[str], chosen: set[str]):
    rows = []

    for opt in options:
        icon = "✅" if opt in chosen else "▫️"
        rows.append([
            InlineKeyboardButton(
                text=f"{icon} {opt}",
                callback_data=f"multi:{qid}:{opt}"
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="Готово",
            callback_data=f"multi_done:{qid}"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_finish(slug: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="🔁 Пройти опрос заново",
                callback_data=f"restart:{slug}"
            )
        ]]
    )
