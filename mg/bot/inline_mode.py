from mg.config import SITE

from mg.bot.types import dp
from aiogram.filters import Command
from mg.bot.functions import new_inline_query, new_message, preview_options, new_inline_result
from aiogram.types import InlineQuery, InlineQueryResultsButton, InlineQueryResultArticle, InputTextMessageContent, Message, ChosenInlineResult

from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton

from typing import Any
from mg.core.database import Database
from mg.core.functions import error_notify
from mg.client.functions import get_is_started


class Review:
    def __init__(self, review_id: int, photo_url: str, title: str, description: str, message_text: str, url: str):
        self.id = review_id
        self.photo_url = photo_url
        self.title = title
        self.description = description
        self.message_text = message_text
        self.url = url

    @classmethod
    def from_json(cls, json_data: dict[str, Any]) -> 'Review':
        return cls(
            review_id=json_data['review_id'],
            photo_url=json_data['photo_url'],
            title=json_data['title'],
            description=json_data['description'],
            message_text=json_data['message_text'],
            url=json_data['url']
        )

    @classmethod
    def list_from_json(cls, json_data: list[dict[str, Any]]) -> list['Review']:
        return [cls.from_json(data) for data in json_data]


async def get_reviews(search: str) -> list[Review]:
    sql = "SELECT review_id, photo_url, title, description, message_text, url FROM reviews WHERE lower(title) LIKE $1 ORDER BY review_id"
    data: list[dict] = await Database.fetch_all(sql, f"%{search.lower()}%")

    return Review.list_from_json(data)


@dp.inline_query()
@error_notify()
async def _review(inline_query: InlineQuery):
    if await new_inline_query(inline_query): return
    is_started = await get_is_started(inline_query.from_user.id)
    if is_started is not None:
        button = InlineQueryResultsButton(text="Открыть меню", start_parameter="menu")
    else:
        button = InlineQueryResultsButton(text="Запустить Maksogram", start_parameter="menu inline_mode")

    results = []

    for review in await get_reviews(search=inline_query.query):
        results.append(InlineQueryResultArticle(
            id=f"review{review.id}", thumbnail_url=review.photo_url, title=review.title,
            description=review.description, thumbnail_width=640, thumbnail_height=640,
            input_message_content=InputTextMessageContent(
                message_text=f"<b><a href='{SITE}/{review.url}'>{review.message_text}</a></b>",
                link_preview_options=preview_options(review.url)
            )))

    await inline_query.answer(results=results, button=button, cache_time=0, is_personal=True)


@dp.chosen_inline_result()
@error_notify()
async def _result_review(inline_result: ChosenInlineResult):
    if await new_inline_result(inline_result): return


@dp.message(Command('inline_mode'))
@error_notify()
async def _inline_mode(message: Message):
    if await new_message(message): return
    markup = IMarkup(inline_keyboard=[[IButton(text="Открыть inline-режим", switch_inline_query_current_chat='')]])
    await message.answer("Inline-режим Maksogram", reply_markup=markup)


def inline_mode_initial():
    pass  # Чтобы PyCharm не ругался
