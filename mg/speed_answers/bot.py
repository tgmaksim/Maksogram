from mg.config import WWW_SITE

from typing import Any

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from mg.bot.types import dp, bot, CallbackData, UserState
from mg.bot.functions import new_callback_query, new_message, preview_options

from aiogram.types import KeyboardButton as KButton
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton

from mg.core.functions import error_notify, serialize_aiogram_entities, deserialize_aiogram_entities, get_subscription

from . functions import (
    add_speed_answer,
    get_speed_answer,
    get_speed_answers,
    edit_speed_answer,
    delete_speed_answer,
    check_unique_trigger,
    set_speed_answer_settings,
    check_count_speed_answers,
    get_link_speed_answer_media,
)


cb = CallbackData()

MAX_TEXT_LENGTH = 1024
MAX_TRIGGER_LENGTH = 32
MAX_FILE_SIZE = 20 * 2**20  # 20МБ


@dp.callback_query(F.data.startswith(cb.command('speed_answers')))
@error_notify()
async def _speed_answers(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    prev = cb.deserialize(callback_query.data).get(0) is True
    await callback_query.message.edit_text(**await speed_answers_menu(callback_query.from_user.id, prev=prev))


async def speed_answers_menu(account_id: int, prev: bool = False) -> dict[str, Any]:
    answers = await get_speed_answers(account_id)

    i, buttons = 0, []
    while i < len(answers):  # Если длина триггеров достаточно короткая, то помещаем 2 в ряд, иначе 1
        if i + 1 < len(answers) and len(answers[i].trigger) <= 15 and len(answers[i+1].trigger) <= 15:

            buttons.append([IButton(text=f"🪧 {answers[i].trigger}", callback_data=cb('speed_answer_menu', answers[i].id)),
                            IButton(text=f"🪧 {answers[i+1].trigger}", callback_data=cb('speed_answer_menu', answers[i+1].id))])
            i += 1
        else:
            buttons.append([IButton(text=f"🪧 {answers[i].trigger}", callback_data=cb('speed_answer_menu', answers[i].id))])
        i += 1

    buttons.append([IButton(text="➕ Добавить быстрый ответ", callback_data=cb('new_speed_answer', prev))])
    buttons.append([IButton(text="◀️  Назад", callback_data=cb('menu'))])

    return dict(
        text="🪧 <b>Быстрые ответы</b>\nСоздайте быстрый ответ, чтобы отправлять большое сообщение с помощью короткой команды\n"
             "После отправки сокращения в любой чат, оно превратится в нужное сообщение", reply_markup=IMarkup(inline_keyboard=buttons),
        link_preview_options=preview_options('быстрые-ответы.mp4', show_above_text=True))


@dp.callback_query(F.data.startswith(cb.command('new_speed_answer')))
@error_notify('state')
async def _new_speed_answer_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    prev = cb.deserialize(callback_query.data).get(0) is True
    if prev:
        await callback_query.answer("Запустите Maksogram кнопкой в меню", True)
        return

    if not await check_count_speed_answers(account_id):
        if await get_subscription(account_id) is None:
            await callback_query.answer("Достигнут лимит быстрых ответов, подключите Maksogram Premium", True)
        else:
            await callback_query.answer("Достигнут лимит количества быстрых ответов!", True)
        return

    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте сокращение (триггер) быстрого ответа", reply_markup=markup)).message_id

    await state.set_state(UserState.speed_answer_trigger)
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.speed_answer_trigger)
@error_notify('state')
async def _speed_answer_trigger(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']

    warning = None
    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)

    if message.text == "Отмена":
        await state.clear()
        await message.answer(**await speed_answers_menu(account_id))
    elif not message.text:
        warning = "Триггер быстрого ответа должен быть текстом"
    elif len(message.text) > MAX_TRIGGER_LENGTH:
        warning = f"Сокращение (триггер) быстрого ответа не должен быть больше {MAX_TRIGGER_LENGTH} символов"
    elif not await check_unique_trigger(account_id, message.text.lower()):  # Триггер неуникальный
        warning = "Сокращение (триггер) быстрого ответа должен быть уникальным"
    else:
        await state.set_state(UserState.speed_answer_text)
        await state.update_data(answer_id=None, trigger=message.text.lower())

        new_message_id = (await message.answer("Отправьте текст, фото или видео (содержание) быстрого ответа", reply_markup=markup)).message_id
        await state.update_data(message_id=new_message_id)

    if warning:
        new_message_id = (await message.answer(warning, reply_markup=markup)).message_id
        await state.update_data(message_id=new_message_id)

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.message(UserState.speed_answer_text)  # Создать новый быстрый ответ или изменить текст
@error_notify('state')
async def _speed_answer_text(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    data = await state.get_data()
    message_id = data['message_id']
    answer_id = data['answer_id']
    trigger = data['trigger']

    warning = None
    text = message.text or message.caption
    entities = message.entities or message.caption_entities or []
    file = message.photo[-1] if message.photo else message.video

    if text == "Отмена":
        await state.clear()
        await message.answer(**await speed_answers_menu(account_id))
    elif message.content_type not in ("text", "photo", "video"):
        warning = "Сообщение не является текстом, фото или видео"
    elif not text:
        warning = "Текст не может быть пустым"
    elif len(text) > MAX_TEXT_LENGTH:
        warning = "Сообщение слишком длинное"
    elif file and file.file_size > MAX_FILE_SIZE:
        warning = "Медиа слишком большое"
    else:
        await state.clear()

        json_entities = serialize_aiogram_entities(entities)
        media_id, ext = None, None

        if file:
            media_id = file.file_id
            ext = 'mp4' if message.video else 'png'

        if answer_id:  # Необходимо изменить текст быстрого ответа
            if await edit_speed_answer(account_id, answer_id, text, json_entities, media_id, ext):  # Быстрый ответ изменен
                await message.answer(**await speed_answer_menu(account_id, answer_id))
            else:  # Быстрый ответ не найден
                await message.answer(**await speed_answers_menu(account_id))

        else:  # Необходимо создать новый быстрый ответ
            answer_id = await add_speed_answer(account_id, trigger, text, json_entities, media_id, ext)

            if answer_id:  # Быстрый ответ создан
                await message.answer(**await speed_answer_menu(account_id, answer_id))
            else:  # Быстрый ответ с таким trigger уже есть у клиента
                await message.answer(**await speed_answers_menu(account_id))

    if warning:
        markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
        new_message_id = (await message.answer(warning, reply_markup=markup)).message_id
        await state.update_data(message_id=new_message_id)

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data.startswith(cb.command('speed_answer_menu')))
@error_notify()
async def _speed_answer_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = cb.deserialize(callback_query.data)[0]
    await callback_query.message.edit_text(**await speed_answer_menu(callback_query.from_user.id, answer_id))


async def speed_answer_menu(account_id: int, answer_id: int) -> dict[str, Any]:
    answer = await get_speed_answer(account_id, answer_id)
    if not answer:
        return await speed_answers_menu(account_id)

    markup = IMarkup(inline_keyboard=[[IButton(text="🚫 Удалить", callback_data=cb('del_speed_answer', answer_id)),
                                       IButton(text="✏️ Изменить", callback_data=cb('edit_speed_answer', answer_id))],
                                      [IButton(text="⚙️ Настройки ответа", callback_data=cb('speed_answer_settings', answer_id))],
                                      [IButton(text="◀️  Назад", callback_data=cb('speed_answers'))]])

    if not answer.media:
        return dict(text=answer.text, entities=deserialize_aiogram_entities(answer.entities), parse_mode=None, reply_markup=markup)
    else:
        link = get_link_speed_answer_media(account_id, answer_id, answer.media.access_hash, answer.media.ext)
        preview = preview_options(link, site=WWW_SITE, show_above_text=True)
        return dict(text=answer.text, entities=deserialize_aiogram_entities(answer.entities),
                    parse_mode=None, reply_markup=markup, link_preview_options=preview)


@dp.callback_query(F.data.startswith(cb.command('edit_speed_answer')))
@error_notify('state')
async def _edit_speed_answer(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    answer_id = cb.deserialize(callback_query.data)[0]

    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте текст, фото или видео (содержание) быстрого ответа", reply_markup=markup)).message_id

    await state.set_state(UserState.speed_answer_text)
    await state.update_data(answer_id=answer_id, trigger=None, message_id=message_id)
    await callback_query.message.delete()


@dp.callback_query(F.data.startswith(cb.command('speed_answer_settings')))
@error_notify()
async def _speed_answer_settings(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = cb.deserialize(callback_query.data)[0]
    await callback_query.message.edit_text(**await speed_answer_settings(callback_query.from_user.id, answer_id))


async def speed_answer_settings(account_id: int, answer_id: int) -> dict[str, Any]:
    answer = await get_speed_answer(account_id, answer_id)
    if answer is None:
        return await speed_answers_menu(account_id)

    send_button = IButton(text="🔺 Отправлять новое" if answer.send else "✏️ Изменять триггер",
                          callback_data=cb('speed_answer_settings_switch', answer_id, 'send', not answer.send))
    markup = IMarkup(inline_keyboard=[[send_button],
                                      [IButton(text="◀️  Назад", callback_data=cb('speed_answer_menu', answer_id))]])

    return dict(
        text="⚙️ <b>Настройки быстрого ответа</b>\n<i>Изменять триггер</i> - сообщение будет со статусом изменено, но будет отправлено быстро без лишних "
             "новых сообщений\n<i>Отправлять новое</i> - сообщение будет отправляться отдельно, что будет дольше и не эстетично", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('speed_answer_settings_switch')))
@error_notify()
async def _speed_answer_settings_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    answer_id, function, command = cb.deserialize(callback_query.data)

    await set_speed_answer_settings(account_id,  answer_id, function, command)
    await callback_query.message.edit_text(**await speed_answer_settings(account_id, answer_id))


@dp.callback_query(F.data.startswith(cb.command('del_speed_answer')))
@error_notify()
async def _del_speed_answer(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    answer_id = cb.deserialize(callback_query.data)[0]

    await delete_speed_answer(account_id, answer_id)
    await callback_query.message.edit_text(**await speed_answers_menu(account_id))


def speed_answers_initial():
    pass  # Чтобы PyCharm не ругался
