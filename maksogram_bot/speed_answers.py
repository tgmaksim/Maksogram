import os
import time
import random

from typing import Any
from asyncpg.exceptions import UniqueViolationError
from core import (
    db,
    html,
    OWNER,
    WWW_SITE,
    security,
    www_path,
    json_encode,
    preview_options,
)

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.types import KeyboardButton as KButton
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from .core import (
    dp,
    bot,
    UserState,
    new_message,
    new_callback_query,
)


@dp.callback_query((F.data == "speed_answers").__or__(F.data == "speed_answersPrev"))
@security()
async def _speed_answers(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    prev = "Prev" if callback_query.data == "speed_answersPrev" else ""
    await callback_query.message.edit_text(**await speed_answers_menu(callback_query.from_user.id, prev=prev))


async def speed_answers_menu(account_id: int, text: str = None, prev: str = "") -> dict[str, Any]:
    buttons = []
    answers = await db.fetch_all(f"SELECT answer_id, trigger FROM speed_answers WHERE account_id={account_id} ORDER BY answer_id")
    i = 0
    while i < len(answers):  # Если длина триггеров достаточно короткая, то помещаем 2 в ряд, иначе 1
        if i + 1 < len(answers) and all(map(lambda x: len(x['trigger']) <= 15, answers[i:i+1])):
            buttons.append([IButton(text=f"🪧 {answers[i]['trigger']}", callback_data=f"speed_answer_menu{answers[i]['answer_id']}"),
                            IButton(text=f"🪧 {answers[i+1]['trigger']}", callback_data=f"speed_answer_menu{answers[i+1]['answer_id']}")])
            i += 1
        else:
            buttons.append([IButton(text=f"🪧 {answers[i]['trigger']}", callback_data=f"speed_answer_menu{answers[i]['answer_id']}")])
        i += 1
    buttons.append([IButton(text="➕ Добавить быстрый ответ", callback_data=f"new_speed_answer{prev}")])
    buttons.append([IButton(text="◀️  Назад", callback_data="menu")])
    return {"text": text or "🪧 <b>Быстрые ответы</b>\nСоздайте быстрый ответ, чтобы отправлять большое сообщение с помощью команды\n"
                            "Отправь сокращение в любой чат и оно превратится в нужное сообщение",
            "reply_markup": IMarkup(inline_keyboard=buttons), "parse_mode": html}


@dp.callback_query(F.data == "new_speed_answerPrev")
@security()
async def _new_speed_answer_prev(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.answer("Быстрые ответы работают только с включенным Maksogram!", True)


@dp.callback_query(F.data == "new_speed_answer")
@security('state')
async def _new_speed_answer_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    if await db.fetch_one(f"SELECT COUNT(*) FROM speed_answers WHERE account_id={account_id}", one_data=True) >= 5:
        if account_id != OWNER:
            return await callback_query.answer("У вас максимальное количество быстрых ответов!", True)
    await state.set_state(UserState.speed_answer_trigger)
    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте сокращение (триггер) быстрого ответа", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.speed_answer_trigger)
@security('state')
async def _new_speed_answer_trigger(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    account_id = message.chat.id

    if message.text and message.text != "Отмена":
        if len(message.text) > 32:
            new_message_id = (await message.answer("Сокращение (триггер) быстрого ответа не должен быть больше 32 символов")).message_id
        else:
            await state.set_state(UserState.speed_answer_text)
            await state.update_data(trigger=message.text.lower())
            markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
            new_message_id = (await message.answer("Отправьте текст, фото или видео — то, что отправится вместо сокращения",
                                                   parse_mode=html, reply_markup=markup)).message_id
        await state.update_data(message_id=new_message_id)
    else:
        await state.clear()
        await message.answer(**await speed_answers_menu(account_id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.message(UserState.speed_answer_text)
@security('state')
async def _new_speed_answer(message: Message, state: FSMContext):
    if await new_message(message): return
    data = await state.get_data()
    message_id = data['message_id']
    trigger = data['trigger']
    await state.clear()
    account_id = message.chat.id

    text = message.text or message.caption
    file = message.photo[-1] if message.photo else (message.video if message.video else None)
    if not text:
        await message.answer(**await speed_answers_menu(account_id, "<b>Текст не может быть пустым</b>"))
    elif message.content_type not in ("text", "photo", "video"):
        await message.answer(**await speed_answers_menu(account_id, "<b>Ваше сообщение не является текстом, фото или видео</b>"))
    elif len(text) > 1024:
        await message.answer(**await speed_answers_menu(account_id, "<b>Ваше сообщение слишком длинное</b>"))
    elif file and file.file_size / 2**20 > 10:
        await message.answer(**await speed_answers_menu(account_id, "<b>Ваше медиа слишком большое</b>"))
    elif text != "Отмена":
        answer_id = int(time.time()) - 1748196000  # 1748196000 - 2025/05/26 00:00 (день создания быстрых ответов)
        entities = json_encode([entity.model_dump() for entity in message.entities or message.caption_entities or []])
        media = None
        if message.photo or message.video:
            access_hash = random.randint(10**10, 10**12-1)
            ext = 'png' if message.photo else 'mp4'
            media = access_hash * 10 + (1 if ext == 'png' else 2)
            path = www_path(f"speed_answers/{account_id}.{answer_id}.{access_hash}.{ext}")
            await bot.download(file.file_id, path)
        # Новый быстрый ответ
        try:
            await db.execute(f"INSERT INTO speed_answers VALUES ({account_id}, {answer_id}, $1, $2, '{entities}', $3)",
                             trigger, text, media)
        except UniqueViolationError:  # Такой текст trigger уже есть
            await message.answer(**await speed_answers_menu(account_id, "<b>Такое сокращение (триггер) уже есть</b>"))
        else:
            await message.answer(**await speed_answer_menu(account_id, answer_id))
    else:
        await message.answer(**await speed_answers_menu(account_id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data.startswith("speed_answer_menu"))
@security()
async def _speed_answer_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("speed_answer_menu", ""))
    await callback_query.message.edit_text(**await speed_answer_menu(callback_query.from_user.id, answer_id))


async def speed_answer_menu(account_id: int, answer_id: int, text: str = None) -> dict[str, Any]:
    answer = await db.fetch_one(f"SELECT text, entities, media FROM speed_answers WHERE account_id={account_id} AND answer_id={answer_id}")
    markup = IMarkup(inline_keyboard=[[IButton(text="🚫 Удалить", callback_data=f"speed_answer_del{answer_id}"),
                                       IButton(text="✏️ Изменить", callback_data=f"speed_answer_edit{answer_id}")],
                                      [IButton(text="◀️  Назад", callback_data="speed_answers")]])
    if text:
        return {"text": text, "parse_mode": html, "reply_markup": markup}
    if answer['media']:
        access_hash = answer['media'] // 10
        ext = 'png' if answer['media'] % 10 == 1 else 'mp4'
        preview = preview_options(f"speed_answers/{account_id}.{answer_id}.{access_hash}.{ext}", site=WWW_SITE, show_above_text=True)
    else:
        preview = None
    return {"text": answer['text'], "entities": answer['entities'], "reply_markup": markup, "link_preview_options": preview}


@dp.callback_query(F.data.startswith("speed_answer_edit"))
@security('state')
async def _speed_answer_edit_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    answer_id = int(callback_query.data.replace("speed_answer_edit", ""))
    if not await db.fetch_one(f"SELECT true FROM speed_answers WHERE account_id={account_id} AND answer_id={answer_id}"):
        return await callback_query.message.edit_text(**await speed_answers_menu(account_id))  # Быстрый ответ не найден
    await state.set_state(UserState.speed_answer_edit)
    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте <b>текст, фото или видео</b> — то, что отправится вместо сокращения",
                                                      parse_mode=html, reply_markup=markup)).message_id
    await state.update_data(message_id=message_id, answer_id=answer_id)
    await callback_query.message.delete()


@dp.message(UserState.speed_answer_edit)
@security('state')
async def _answering_machine_edit_text(message: Message, state: FSMContext):
    if await new_message(message): return
    data = await state.get_data()
    message_id = data['message_id']
    answer_id = data['answer_id']
    await state.clear()
    account_id = message.chat.id

    text = message.text or message.caption
    file = message.photo[-1] if message.photo else (message.video if message.video else None)
    if not await db.fetch_one(f"SELECT true FROM speed_answers WHERE account_id={account_id} AND answer_id={answer_id}"):
        await message.answer(**await speed_answers_menu(account_id))  # Быстрый ответ не найден
    elif not text:
        await message.answer(**await speed_answer_menu(account_id, answer_id, "<b>Текст не должен быть пустым</b>"))
    elif message.content_type not in ("text", "photo", "video"):
        await message.answer(**await speed_answer_menu(account_id, answer_id, "<b>Ваше сообщение не является текстом, фото или видео</b>"))
    elif len(text) > 1024:
        await message.answer(**await speed_answer_menu(account_id, answer_id, "<b>Ваше сообщение слишком длинное</b>"))
    elif file and file.file_size / 2**20 > 10:
        await message.answer(**await speed_answer_menu(account_id, answer_id, "<b>Ваше медиа слишком большое</b>"))
    elif text != "Отмена":
        entities = json_encode([entity.model_dump() for entity in message.entities or message.caption_entities or []])
        media = None
        last_media = await db.fetch_one(f"SELECT media FROM speed_answers "
                                        f"WHERE account_id={account_id} AND answer_id={answer_id}", one_data=True)
        if last_media:
            access_hash = last_media // 10
            ext = 'png' if last_media % 10 == 1 else 'mp4'
            os.remove(www_path(f"speed_answers/{account_id}.{answer_id}.{access_hash}.{ext}"))
        if message.photo or message.video:
            access_hash = random.randint(10**10, 10**12-1)
            ext = 'png' if message.photo else 'mp4'
            media = access_hash * 10 + (1 if ext == 'png' else 2)
            path = www_path(f"speed_answers/{account_id}.{answer_id}.{access_hash}.{ext}")
            await bot.download(file.file_id, path)
        await db.execute(f"UPDATE speed_answers SET text=$1, entities='{entities}', media=$2 "
                         f"WHERE account_id={account_id} AND answer_id={answer_id}", text, media)  # Изменение автоответа
        await message.answer(**await speed_answer_menu(account_id, answer_id))
    else:
        await message.answer(**await speed_answer_menu(account_id, answer_id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data.startswith("speed_answer_del"))
@security()
async def _speed_answer_del(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    answer_id = int(callback_query.data.replace("speed_answer_del", ""))
    answer = await db.fetch_one(f"SELECT media FROM speed_answers WHERE account_id={account_id} AND answer_id={answer_id}")
    if answer:
        if media := answer['media']:
            access_hash = media // 10
            ext = 'png' if media % 10 == 1 else 'mp4'
            os.remove(www_path(f"speed_answers/{account_id}.{answer_id}.{access_hash}.{ext}"))
        await db.execute(f"DELETE FROM speed_answers WHERE account_id={account_id} AND answer_id={answer_id}")  # Удаление быстрого ответа
    await callback_query.message.edit_text(**await speed_answers_menu(account_id))


def speed_answers_initial():
    return  # Чтобы PyCharm не ругался
