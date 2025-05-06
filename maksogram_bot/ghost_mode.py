from typing import Any
from core import (
    html,
    WWW_SITE,
    security,
    www_path,
    telegram_clients,
)

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from telethon.tl.types.stories import PeerStories
from aiogram.types import KeyboardButton as KButton
from aiogram.types import KeyboardButtonRequestUsers
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import ReplyKeyboardRemove as KRemove
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from telethon.tl.functions.stories import GetPeerStoriesRequest
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from .core import (
    dp,
    bot,
    new_user,
    UserState,
    new_message,
    new_callback_query,
)


@dp.callback_query((F.data == "ghost_mode").__or__(F.data == "ghost_modePrev"))
@security()
async def _ghost_mode(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    prev = "Prev" if callback_query.data == "ghost_modePrev" else ""
    await callback_query.message.edit_text(**await ghost_mode_menu(prev=prev))


async def ghost_mode_menu(_: int = None, text: str = None, prev: str = "") -> dict[str, Any]:
    markup = IMarkup(inline_keyboard=[[IButton(text="📸 Посмотреть историю", callback_data=f"ghost_stories{prev}")],
                                      [IButton(text="◀️  Назад", callback_data="menu")]])
    return {"text": text or "👀 <b>Режим призрака</b>\nЗдесь вы можете совершить какое-то действие в «режиме призрака» (незаметно). "
                            "Ни один пользователь кроме вас об этом не узнает 🙈", "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data == "ghost_storiesPrev")
@security()
async def _ghost_stories_prev(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.answer("Посмотреть историю в режиме призрака доступно только пользователям Maksogram", True)


@dp.callback_query(F.data == "ghost_stories")
@security('state')
async def _ghost_stories(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.ghost_stories)
    request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False, user_is_premium=True)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request_users)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте пользователя для просмотра истории кнопкой, ID, username "
                                                      "или номер телефона", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.ghost_stories)
@security('state')
async def _ghost_stories_watch(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    account_id = message.chat.id

    user = await new_user(message, ghost_mode_menu)
    if user:
        user_id = user.id
        telegram_client = telegram_clients[account_id]
        if user_id == account_id:  # Себя нельзя
            await message.answer(**await ghost_mode_menu())
        else:
            wait_message = await message.answer_sticker("CAACAgIAAxkBAAIyQWeUrH2jAUkcqHGYerWNT3ySuFwbAAJBAQACzRswCPHwYhjf9pZYNgQ", reply_markup=KRemove())
            stories: PeerStories = await telegram_client(GetPeerStoriesRequest(user_id))
            paths = []
            for story in stories.stories.stories:
                if isinstance(story.media, MessageMediaDocument) and story.media.video:
                    paths.append(path := f"stories/{account_id}.{user_id}.{story.id}.mp4")
                elif isinstance(story.media, MessageMediaPhoto):
                    paths.append(path := f"stories/{account_id}.{user_id}.{story.id}.png")
                else:
                    continue
                await telegram_client.download_media(story.media, www_path(path))
            links = '\n'.join([f"<a href='{WWW_SITE}/{path}'>История №{i+1}</a>" for i, path in enumerate(paths)]) if paths \
                else "<b>Истории не найдены</b>"
            markup = IMarkup(inline_keyboard=[[IButton(text="◀️  Назад", callback_data="ghost_mode")]])
            await message.answer(f"👀 <b>Режим призрака</b>\nПосмотреть истории в «режиме призрака» можно по ссылкам ниже\n"
                                 f"{links}", disable_web_page_preview=True, parse_mode=html, reply_markup=markup)
            await wait_message.delete()

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


def ghost_mode_initial():
    pass  # Чтобы PyCharm не ругался
