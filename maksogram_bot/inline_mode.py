from dataclasses import dataclass
from core import (
    db,
    html,
    SITE,
    security,
    preview_options,
)

from .core import dp, new_inline_query
from aiogram.types import (
    InlineQuery,
    InputTextMessageContent,
    InlineQueryResultsButton,
    InlineQueryResultArticle,
)


@dataclass
class Preview:
    preview_id: int
    photo_url: str
    title: str
    description: str
    message_text: str
    url: str


@dp.inline_query()
@security()
async def _review(inline_query: InlineQuery):
    if await new_inline_query(inline_query): return
    is_started = await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={inline_query.from_user.id}", one_data=True)
    if is_started is None:  # Пользователь не зарегистрирован
        button = InlineQueryResultsButton(text="Зарегаться в Maksogram", start_parameter="inline_mode")
    elif is_started is False:  # Maksogram выключен для аккаунта
        button = InlineQueryResultsButton(text="Включить Maksogram", start_parameter="menu")
    else:
        button = InlineQueryResultsButton(text="Открыть меню функций", start_parameter="menu")

    results = []

    for preview in await get_previews(search=inline_query.query):
        results.append(InlineQueryResultArticle(
            id=f"preview_{preview.preview_id}", thumbnail_url=preview.photo_url, title=preview.title,
            description=preview.description, thumbnail_width=640, thumbnail_height=640,
            input_message_content=InputTextMessageContent(
                message_text=f"<b><a href='{SITE}/{preview.url}'>{preview.message_text}</a></b>",
                parse_mode=html, link_preview_options=preview_options(preview.url)
            )))

    await inline_query.answer(results=results, button=button, cache_time=0, is_personal=True)


async def get_previews(search: str) -> list[Preview]:
    previews = await db.fetch_all("SELECT preview_id, photo_url, title, description, message_text, url FROM previews "
                                  "WHERE lower(title) LIKE $1 ORDER BY preview_id", f"%{search.lower()}%")
    return [Preview(**preview) for preview in previews]


def inline_mode_initial():
    pass  # Чтобы PyCharm не ругался
