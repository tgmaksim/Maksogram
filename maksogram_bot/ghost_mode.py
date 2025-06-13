import re
import time

from typing import Any
from core import (
    html,
    WWW_SITE,
    security,
    www_path,
    telegram_clients,
    bot_entities_from_tl,
)

from aiogram import F
from aiogram.fsm.context import FSMContext
from telethon.tl.patched import Message as Post
from aiogram.types import KeyboardButton as KButton
from aiogram.types import KeyboardButtonRequestUsers
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import ReplyKeyboardRemove as KRemove
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from telethon.tl.types.stories import PeerStories, Stories
from aiogram.types import Message, CallbackQuery, LinkPreviewOptions
from telethon.tl.functions.stories import GetPeerStoriesRequest, GetPinnedStoriesRequest
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, Channel, PeerChannel
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
                                      [IButton(text="⬇️ Скачать пост", callback_data=f"ghost_copy{prev}")],
                                      [IButton(text="◀️  Назад", callback_data="menu")]])
    return {"text": text or "👀 <b>Режим призрака</b>\nЗдесь вы можете совершить какое-то действие в «режиме призрака» (незаметно). "
                            "Ни один пользователь кроме вас об этом не узнает 🙈", "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data == "ghost_storiesPrev")
@security()
async def _ghost_stories_prev(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.answer("Посмотреть историю в режиме призрака доступно только пользователям Maksogram", True)


@dp.callback_query(F.data == "ghost_copyPrev")
@security()
async def _ghost_stories_prev(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.answer("Скачать пост с запретом копирования доступно только пользователям Maksogram", True)


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
            peer_stories: PeerStories = await telegram_client(GetPeerStoriesRequest(user_id))
            all_stories: Stories = await telegram_client(GetPinnedStoriesRequest(peer=user_id, offset_id=0, limit=10))
            links, all_links = "", ""
            for story in peer_stories.stories.stories:
                if isinstance(story.media, MessageMediaDocument) and story.media.video:
                    path = f"stories/{account_id}.{user_id}.{story.id}-{int(time.time())}.mp4"
                    links += f"<a href='{WWW_SITE}/{path}'>Видео №{story.id} ({int(story.media.document.attributes[0].duration)} " \
                             f"сек) от {story.media.document.date.strftime('%d-%m %H:%M')}</a>\n"
                elif isinstance(story.media, MessageMediaPhoto):
                    path = f"stories/{account_id}.{user_id}.{story.id}-{int(time.time())}.png"
                    links += f"<a href='{WWW_SITE}/{path}'>Фото №{story.id} от {story.media.photo.date.strftime('%d-%m %H:%M')}</a>\n"
                else: continue
                await telegram_client.download_media(story.media, www_path(path))
            for story in all_stories.stories:
                if isinstance(story.media, MessageMediaDocument) and story.media.video:
                    path = f"stories/{account_id}.{user_id}.{story.id}.profile-{int(time.time())}.mp4"
                    all_links += f"<a href='{WWW_SITE}/{path}'>Видео №{story.id} ({int(story.media.document.attributes[0].duration)} " \
                                 f"сек) от {story.media.document.date.strftime('%d-%m %H:%M')}</a>\n"
                elif isinstance(story.media, MessageMediaPhoto):
                    path = f"stories/{account_id}.{user_id}.{story.id}.profile-{int(time.time())}.png"
                    all_links += f"<a href='{WWW_SITE}/{path}'>Фото №{story.id} от {story.media.photo.date.strftime('%d-%m %H:%M')}</a>\n"
                else: continue
                await telegram_client.download_media(story.media, www_path(path))
            text = f"{links or '<b>Активные истории не найдены</b>'}\nПоследние 10 историй в профиле\n" \
                   f"<blockquote expandable>{all_links or '<b>Истории не найдены</b>'}</blockquote>"
            markup = IMarkup(inline_keyboard=[[IButton(text="◀️  Назад", callback_data="ghost_mode")]])
            await message.answer(f"👀 <b>Режим призрака</b>\nПосмотреть истории в «режиме призрака» можно по ссылкам ниже\n\n{text}",
                                 disable_web_page_preview=True, parse_mode=html, reply_markup=markup)
            await wait_message.delete()

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data == "ghost_copy")
@security('state')
async def _ghost_copy_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.ghost_copy)
    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте ссылку на пост, который нужно скачать", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.ghost_copy)
@security('state')
async def _ghost_copy(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    account_id = message.chat.id

    if message.text == "Отмена":
        await message.answer(**await ghost_mode_menu())
    elif link := (re.fullmatch(r'(?:(?:https|http)://)?t\.me/c/(?P<channel_id>\d+)/(?P<post_id>\d+)', message.text) or
                  re.fullmatch(r'(?:(?:https|http)://)?t\.me/(?P<channel_username>[a-zA-Z0-9_]+)/(?P<post_id>\d+)', message.text)):
        channel_id, post_id = link.groups()
        post_id = int(post_id)
        telegram_client = telegram_clients[account_id]
        try:
            peer_channel = PeerChannel(channel_id=int(channel_id)) if channel_id.isdigit() else channel_id
            channel: Channel = await telegram_client.get_entity(peer_channel)
        except ValueError:
            await message.answer(**await ghost_mode_menu(text="<b>Данный канал не найден</b>"))
        else:
            post: Post = await telegram_client.get_messages(channel, ids=post_id)
            if post:
                wait_message = await message.answer_sticker("CAACAgIAAxkBAAIyQWeUrH2jAUkcqHGYerWNT3ySuFwbAAJBAQACzRswCPHwYhjf9pZYNgQ", reply_markup=KRemove())
                posts = [post]
                if grouped_id := post.grouped_id:
                    async for post in telegram_client.iter_messages(channel, min_id=post_id-10, max_id=post_id):
                        if post.grouped_id != grouped_id:
                            break
                        posts.append(post)
                for post in posts:
                    entities = bot_entities_from_tl(post.entities or [])
                    if post.photo:
                        path = f"posts/{account_id}.{channel_id}.{post.id}-{int(time.time())}.png"
                    elif post.video or post.video_note:
                        path = f"posts/{account_id}.{channel_id}.{post.id}-{int(time.time())}.mp4"
                    elif post.voice:
                        path = f"posts/{account_id}.{channel_id}.{post.id}-{int(time.time())}.mp3"
                    else:
                        if not post.media:
                            await message.answer(post.message, entities=entities)
                        continue
                    await telegram_client.download_media(post, file=www_path(path))
                    link_preview_options = LinkPreviewOptions(url=f"{WWW_SITE}/{path}", show_above_text=True, prefer_large_media=True)
                    await message.answer(post.message or "media", entities=entities, link_preview_options=link_preview_options)
                await wait_message.delete()
            else:
                await message.answer(**await ghost_mode_menu(text="<b>Пост на канале не найден!</b>"))
    else:
        await message.answer("<b>Ссылка на пост не распознана!</b>\nЗайдите на канал, в котором запрещены пересылка и копирование "
                             "контента, и нажмите рядом с нужным постом, чтобы открылось меню. Нажмите на кнопку для копирования ссылки", parse_mode=html)
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


def ghost_mode_initial():
    pass  # Чтобы PyCharm не ругался
