import os

from aiogram import F

from aiogram.fsm.context import FSMContext
from mg.bot.types import dp, bot, CallbackData, UserState, sticker_loading
from aiogram.types import CallbackQuery, Message, KeyboardButtonRequestUsers
from mg.bot.functions import new_callback_query, new_message, request_user

from aiogram.types import KeyboardButton as KButton
from aiogram.types import ReplyKeyboardRemove as KRemove
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton

from typing import Any
from mg.core.types import MaksogramBot
from mg.core.functions import error_notify, get_subscription

from . functions import (
    update_limit,
    download_post,
    parse_post_link,
    COUNT_PINNED_STORIES,
    download_peer_stories,
    download_pinned_stories,
    check_count_usage_ghost_mode,
)


cb = CallbackData()


@dp.callback_query(F.data.startswith(cb.command('ghost_mode')))
@error_notify()
async def _ghost_mode(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    prev = cb.deserialize(callback_query.data).get(0) is True
    await callback_query.message.edit_text(**await ghost_mode_menu(prev=prev))


async def ghost_mode_menu(prev: bool = False) -> dict[str, Any]:
    markup = IMarkup(inline_keyboard=[[IButton(text="📸 Посмотреть историю", callback_data=cb('ghost_stories', prev))],
                                      [IButton(text="⬇️ Скачать пост", callback_data=cb('ghost_copy', prev))],
                                      [IButton(text="◀️  Назад", callback_data=cb('menu'))]])

    return dict(
        text="👀 <b>Режим призрака</b>\nЗдесь вы можете совершить какое-то действие в «режиме призрака» (незаметно). Ни один пользователь кроме "
             "вас об этом не узнает 🙈", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('ghost_stories')))
@error_notify('state')
async def _ghost_stories_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    prev = cb.deserialize(callback_query.data).get(0) is True
    if prev:
        await callback_query.answer("Запустите Maksogram кнопкой в меню", True)
        return

    if await get_subscription(callback_query.from_user.id) is None:
        await callback_query.answer("Смотреть историю в режиме призрака можно только с подпиской Maksogram Premium", True)
        return

    await state.set_state(UserState.ghost_stories)

    request = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False, user_is_premium=True, max_quantity=1)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте пользователя для просмотра истории кнопкой, ID, username "
                                                      "или номер телефона", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.ghost_stories)
@error_notify('state')
async def _ghost_stories(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']

    if message.text == "Отмена":
        await state.clear()
        await message.answer(**await ghost_mode_menu())
    else:
        response = await request_user(message, can_yourself=False)

        if not response.ok:
            request = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False, user_is_premium=True, max_quantity=1)
            markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request)],
                                       [KButton(text="Отмена")]], resize_keyboard=True)
            new_message_id = (await message.answer(response.warning, reply_markup=markup)).message_id
            await state.update_data(message_id=new_message_id)
        else:
            await state.clear()

            text = "👀 <b>Режим призрака</b>\nПосмотреть истории в «режиме призрака» можно по ссылкам ниже\n\n"
            wait_message = await message.answer_sticker(sticker_loading, reply_markup=KRemove())

            active_links = '\n'.join(await download_peer_stories(account_id, response.user.id))
            pinned_links = '\n'.join(await download_pinned_stories(account_id, response.user.id))

            if not pinned_links:  # Если нет историй в профиле, их нет вообще
                text += "<b>Истории не найдены...</b>"
            else:  # Истории в профиле есть
                if active_links:  # Активные истории есть
                    text += f"Активные истории пользователя\n{active_links}\n\n"
                text += (f"Последние {COUNT_PINNED_STORIES} историй\n"
                         f"<blockquote expandable>{pinned_links}</blockquote>")

            markup = IMarkup(inline_keyboard=[[IButton(text="◀️  Назад", callback_data=cb('ghost_mode'))]])
            await message.answer(text, reply_markup=markup, disable_web_page_preview=True)

            await update_limit(account_id, 'stories')
            await wait_message.delete()

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data.startswith(cb.command('ghost_copy')))
@error_notify('state')
async def _ghost_copy_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    prev = cb.deserialize(callback_query.data).get(0) is True
    if prev:
        await callback_query.answer("Запустите Maksogram кнопкой в меню", True)
        return

    if not await check_count_usage_ghost_mode(account_id, 'copy'):
        if await get_subscription(account_id) is None:
            await callback_query.answer("Достигнут лимит использования функции в день, подключите Maksogram Premium!", True)
        else:
            await callback_query.answer("Достигнут лимит количества использования функции в день!", True)
        return

    await state.set_state(UserState.ghost_copy)

    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте ссылку на пост, который нужно скачать", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.ghost_copy)
@error_notify('state')
async def _ghost_copy(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']

    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)

    if message.text == "Отмена":
        await state.clear()
        await message.answer(**await ghost_mode_menu())
    else:
        if channel := parse_post_link(message.text):
            entity, post_id = channel

            wait_message = await message.answer_sticker(sticker_loading, reply_markup=KRemove())

            response = await download_post(account_id, entity, post_id)
            if not response.ok:
                new_message_id = (await message.answer(response.warning, reply_markup=markup)).message_id
                await state.update_data(message_id=new_message_id)
            else:
                await state.clear()

                for post in response.posts:
                    if post.media:
                        await MaksogramBot.send_file(account_id, post.media, post.text, formatting_entities=post.entities,
                                                     video_note=post.video_note, voice_note=post.voice_note)
                        os.remove(post.media)
                    else:
                        await MaksogramBot.send_message(account_id, post.text, formatting_entities=post.entities, link_preview=False)

                await message.answer(**await ghost_mode_menu())

            await update_limit(account_id, 'copy')
            await wait_message.delete()

        else:
            new_message_id = (await message.answer("Ссылка на канал неверна", reply_markup=markup)).message_id
            await state.update_data(message_id=new_message_id)

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


def ghost_mode_initial():
    pass  # Чтобы PyCharm не ругался
