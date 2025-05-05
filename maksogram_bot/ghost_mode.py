from typing import Any
from telethon.utils import parse_username, parse_phone
from core import (
    db,
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
    UserState,
    new_message,
    new_callback_query,
)


@dp.callback_query(F.data == "ghost_mode")
@security()
async def _ghost_mode(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**ghost_mode_menu())


def ghost_mode_menu(text: str = None) -> dict[str, Any]:
    markup = IMarkup(inline_keyboard=[[IButton(text="📸 Посмотреть историю", callback_data="ghost_stories")],
                                      [IButton(text="◀️  Назад", callback_data="menu")]])
    return {"text": text or "👀 <b>Режим призрака</b>\nЗдесь вы можете совершить какое-то действие в «режиме призрака» (незаметно). "
                            "Ни один пользователь кроме вас об этом не узнает 🙈", "parse_mode": html, "reply_markup": markup}


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
    if not await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True):
        await message.answer(**ghost_mode_menu("<b>Maksogram выключен!</b>"))
    elif message.text == "Отмена":
        await message.answer(**ghost_mode_menu())
    else:  # Maksogram запущен
        entity, user = None, None
        telegram_client = telegram_clients[account_id]
        username, phone = message.text and parse_username(message.text), message.text and parse_phone(message.text)
        if message.content_type == "users_shared":
            entity = message.users_shared.user_ids[0]
        elif username[1] is False and username[0] is not None:  # Является ли строка username (не ссылка с приглашением)
            entity = username[0]
        elif phone and message.text.startswith('+'):
            entity = f"+{phone}"
        elif message.text and message.text.isdigit():  # ID пользователя
            entity = int(message.text)
        if entity:
            try:
                user = await telegram_client.get_entity(entity)
            except ValueError:  # Пользователь с такими данными не найден
                pass

        if user:
            user_id = user.id
            if user_id == account_id:  # Себя нельзя
                await message.answer(**ghost_mode_menu())
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
        else:
            await message.answer(**ghost_mode_menu("<b>Пользователь не найден!</b>"))

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


def ghost_mode_initial():
    pass  # Чтобы PyCharm не ругался
