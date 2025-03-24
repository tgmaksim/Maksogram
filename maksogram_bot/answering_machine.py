import os
import re
import time
import random

from typing import Any
from core import (
    db,
    html,
    www_path,
    security,
    WWW_SITE,
    json_encode,
    preview_options,
    get_enabled_auto_answer,
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


def get_weekdays_string_by_list(weekdays: list[int]) -> str:
    dictionary = {0: "пн", 1: "вт", 2: "ср", 3: "чт", 4: "пт", 5: "сб", 6: "вс"}
    return " ".join([dictionary[weekday] for weekday in weekdays])


def get_weekdays_list_by_string(weekdays: str) -> list[int]:
    dictionary = {"пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "вс": 6}
    return list({dictionary[weekday] for weekday in weekdays.replace(" ", "").split(",")})


@dp.callback_query(F.data == "answering_machine")
@security()
async def _answering_machine(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await answering_machine_menu(callback_query.message.chat.id))


async def answering_machine_menu(account_id: int) -> dict[str, Any]:
    buttons = []
    answers = await db.fetch_all(f"SELECT answer_id, type, text FROM answering_machine "
                                 f"WHERE account_id={account_id} ORDER BY answer_id")  # Автоответы
    enabled_answer = await get_enabled_auto_answer(account_id)
    for answer in answers:
        text = (str(answer['text'])[:28] + "...") if len(str(answer['text'])) > 28 else str(answer['text'])
        indicator = ""
        if answer['answer_id'] == enabled_answer:  # Автоответ активен
            if answer['type'] == 'timetable':  # Автоответ по расписанию
                indicator = "⏰ "
            elif answer['type'] == 'ordinary':  # Обычный автоответ
                indicator = "🟢 "
        buttons.append([IButton(text=f"{indicator}{text}", callback_data=f"answering_machine_menu{answer['answer_id']}")])
    buttons.append([IButton(text="➕ Создать новый ответ", callback_data="new_answering_machine")])
    buttons.append([IButton(text="◀️  Назад", callback_data="menu")])
    markup = IMarkup(inline_keyboard=buttons)
    return {
        "text": "🤖 <b>Автоответчик</b>\n<blockquote expandable><b>Подробнее об автоответчике</b>\n"
                "Автоответчик бывает <b>обыкновенным</b> и <b>по расписанию</b>\n\nОбыкновенный автоответ работает при включении\n"
                "Автоответ по расписанию имеет временные рамки, в течение которых будет работать\n\nОдновременно могут "
                "работать сразу <b>несколько</b> автоответов по расписанию, но их время работы не должно пересекаться\n\n"
                "Если включен обыкновенный автоответ и один (несколько) временной, то работать будет "
                "<b>только обыкновенный</b></blockquote>",
        "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data == "new_answering_machine")
@security('state')
async def _new_answering_machine_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    if await db.fetch_one(f"SELECT COUNT(*) FROM answering_machine WHERE account_id={callback_query.from_user.id}", one_data=True) >= 5:
        # Количество автоответов уже достигло максимума
        return await callback_query.answer("У вас максимальное количество автоответов", True)
    await state.set_state(UserState.answering_machine)
    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте <b>текст, фото или видео</b>, которые я отправлю в случае необходимости",
                                                      parse_mode=html, reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.answering_machine)
@security('state')
async def _new_answering_machine(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    text = message.text or message.caption
    file = message.photo[-1] if message.photo else (message.video if message.video else None)
    if not text:
        await message.answer("<b>Текст не может быть пустым</b>", parse_mode=html,
                             reply_markup=(await answering_machine_menu(message.chat.id))['reply_markup'])
    elif message.content_type not in ("text", "photo", "video"):
        await message.answer("<b>Ваше сообщение не является текстом, фото или видео</b>", parse_mode=html,
                             reply_markup=(await answering_machine_menu(message.chat.id))['reply_markup'])
    elif len(text) > 512:
        await message.answer("<b>Ваше сообщение слишком длинное</b>", parse_mode=html,
                             reply_markup=(await answering_machine_menu(message.chat.id))['reply_markup'])
    elif file and file.file_size / 2**20 > 10:
        await message.answer("<b>Ваше медиа слишком большое</b>", parse_mode=html,
                             reply_markup=(await answering_machine_menu(message.chat.id))['reply_markup'])
    elif text != "Отмена":
        answer_id = int(time.time()) - 1737828000  # 1737828000 - 2025/01/26 00:00 (день активного обновления автоответчика)
        entities = json_encode([entity.model_dump() for entity in message.entities or message.caption_entities or []])
        media = None
        if message.photo or message.video:
            access_hash = random.randint(10**10, 10**12-1)
            ext = 'png' if message.photo else 'mp4'
            media = access_hash * 10 + (1 if ext == 'png' else 2)
            path = www_path(f"answering_machine/{message.chat.id}.{answer_id}.{access_hash}.{ext}")
            await bot.download(file.file_id, path)
        # Новый автоответ
        await db.execute(f"INSERT INTO answering_machine VALUES ({message.chat.id}, {answer_id}, "
                         f"false, 'ordinary', NULL, NULL, NULL, $1, '{entities}', false, $2)", text, media)
        await message.answer(**await auto_answer_menu(message.chat.id, answer_id))
    else:
        await message.answer(**await answering_machine_menu(message.chat.id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data.startswith("answering_machine_menu"))
@security()
async def _answering_machine_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_menu", ""))
    await callback_query.message.edit_text(**await auto_answer_menu(callback_query.message.chat.id, answer_id))


async def auto_answer_menu(account_id: int, answer_id: int):
    # Включенный автоответ и нужный автоответ
    answer = await db.fetch_one(f"SELECT status, type, start_time, end_time, weekdays, text, entities, contacts, media "
                                f"FROM answering_machine WHERE account_id={account_id} AND answer_id={answer_id}")
    if answer is None:  # Автоответ не найден
        return await answering_machine_menu(account_id)
    media = answer['media']
    time_button = IButton(text="⏰ Расписание", callback_data=f"answering_machine_time{answer_id}")
    weekdays_button = IButton(text="🗓 Выбрать дни", callback_data=f"answering_machine_weekdays{answer_id}")
    is_timetable = answer['type'] == 'timetable'
    if is_timetable:
        time_zone = await db.fetch_one(f"SELECT time_zone FROM settings WHERE account_id={account_id}", one_data=True)
        hours_start_time = str((answer['start_time'].hour + time_zone) % 24).rjust(2, "0")
        minutes_start_time = str(answer['start_time'].minute).rjust(2, "0")
        hours_end_time = str((answer['end_time'].hour + time_zone) % 24).rjust(2, "0")
        minutes_end_time = str(answer['end_time'].minute).rjust(2, "0")
        timetable = f"{hours_start_time}:{minutes_start_time} — {hours_end_time}:{minutes_end_time}"
        time_button = IButton(text=f"⏰ {timetable}", callback_data=f"answering_machine_time{answer_id}")

        weekdays = get_weekdays_string_by_list(answer['weekdays'])
        weekdays_button = IButton(text=f"🗓 {weekdays}", callback_data=f"answering_machine_weekdays{answer_id}")
    status_button = IButton(text="🔴 Выключить", callback_data=f"answering_machine_off_{answer_id}") if answer['status'] \
        else IButton(text="🟢 Включить", callback_data=f"answering_machine_on_{answer_id}")
    contacts = IButton(text="🤝 Только контактам", callback_data=f"answering_machine_contacts_off_{answer_id}") \
        if answer['contacts'] else IButton(text="🤝 Отвечаю всем", callback_data=f"answering_machine_contacts_on_{answer_id}")
    markup = IMarkup(inline_keyboard=[[status_button,
                                       IButton(text="🚫 Удалить", callback_data=f"answering_machine_del_answer{answer_id}")],
                                      [IButton(text="✏️ Изменить", callback_data=f"answering_machine_edit_text{answer_id}"),
                                       time_button],
                                      [weekdays_button],
                                      [contacts],
                                      [IButton(text="◀️  Назад", callback_data="answering_machine")]])
    if media:
        access_hash = media // 10
        ext = 'png' if media % 10 == 1 else 'mp4'
        preview = preview_options(f"answering_machine/{account_id}.{answer_id}.{access_hash}.{ext}",
                                  site=WWW_SITE, show_above_text=True)
    else:
        preview = None
    return {"text": str(answer['text']), "entities": answer['entities'], "reply_markup": markup, "link_preview_options": preview}


@dp.callback_query(F.data.startswith("answering_machine_del_answer"))
@security()
async def _answering_machine_del_answer(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_del_answer", ""))
    account_id = callback_query.from_user.id
    answer = await db.fetch_one(f"SELECT media FROM answering_machine WHERE account_id={account_id} AND answer_id={answer_id}")
    if answer:
        if media := answer['media']:
            access_hash = media // 10
            ext = 'png' if media % 10 == 1 else 'mp4'
            os.remove(www_path(f"answering_machine/{account_id}.{answer_id}.{access_hash}.{ext}"))
        await db.execute(f"DELETE FROM answering_machine WHERE account_id={account_id} AND answer_id={answer_id}")  # Удаление автоответа
    await callback_query.message.edit_text(**await answering_machine_menu(callback_query.message.chat.id))


@dp.callback_query(F.data.startswith("answering_machine_on").__or__(F.data.startswith("answering_machine_off")))
@security()
async def _answering_machine_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command, answer_id = callback_query.data.replace("answering_machine_", "").split("_")
    account_id = callback_query.from_user.id
    answer = await db.fetch_one(f"SELECT status, type, start_time, end_time, weekdays FROM answering_machine "
                                f"WHERE account_id={account_id} AND answer_id={answer_id}")
    if answer is None:  # Автоответ не найден
        await callback_query.answer("Автоответ был удалено ранее!", True)
        return await callback_query.message.edit_text(**await answering_machine_menu(account_id))
    if (command == "on") == answer['status']:  # Статус совпадает с нужным
        return await callback_query.message.edit_text(**await auto_answer_menu(account_id, answer_id))
    status = "true" if command == "on" else "false"
    main_auto_answer = await get_enabled_auto_answer(account_id)
    if answer['type'] == "ordinary" and command == "on":  # Обыкновенный автоответ
        # Выключение включенного обыкновенного автоответа (если есть)
        await db.execute(f"UPDATE answering_machine SET status=false WHERE account_id={account_id} AND type='ordinary'")
    elif answer['type'] == "timetable" and command == "on":  # Автоответ по расписанию
        # Автоответы по расписанию не должны пересекаться во времени
        for ans in await db.fetch_all(f"SELECT start_time, end_time, weekdays FROM answering_machine WHERE account_id={account_id} "
                                      f"AND type='timetable' AND status=true AND answer_id!={answer_id}"):
            if answer['start_time'] < answer['end_time'] < ans['start_time'] < ans['end_time'] or \
                    ans['start_time'] < ans['end_time'] < answer['start_time'] < answer['end_time'] or \
                    answer['end_time'] < ans['start_time'] < ans['end_time'] < answer['start_time'] or \
                    ans['end_time'] < answer['start_time'] < answer['end_time'] < ans['start_time']:
                pass  # Все случаи, когда автоответы по времени не пересекаются
            elif len(set(ans['weekdays'] + answer['weekdays'])) == len(ans['weekdays'] + answer['weekdays']):
                pass  # Автоответы пересекаются по времени, но работают в разные дни
            else:
                return await callback_query.answer("Расписание данного автоответа пересекается с расписанием уже включенного", True)
    await db.execute(f"UPDATE answering_machine SET status={status} WHERE account_id={account_id} AND answer_id={answer_id}")
    if await db.fetch_all(f"SELECT true FROM answering_machine WHERE status=true AND account_id={account_id}", one_data=True):
        await db.execute(f"UPDATE statistics SET answering_machine=NULL WHERE account_id={account_id}")
    else:
        await db.execute(f"UPDATE statistics SET answering_machine=now() WHERE account_id={account_id}")
    if main_auto_answer != await get_enabled_auto_answer(account_id):  # Если работающий автоответ сменился, обнуляем sending
        await db.execute(f"UPDATE functions SET answering_machine_sending='[]' WHERE account_id={account_id}")
    await callback_query.message.edit_text(**await auto_answer_menu(account_id, answer_id))


@dp.callback_query(F.data.startswith("answering_machine_edit_text"))
@security('state')
async def _answering_machine_edit_text_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_edit_text", ""))
    await state.set_state(UserState.answering_machine_edit_text)
    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправь <b>текст, фото или видео</b>, которые я отправлю в случае необходимости",
                                                      parse_mode=html, reply_markup=markup)).message_id
    await state.update_data(message_id=message_id, answer_id=answer_id)
    await callback_query.message.delete()


@dp.message(UserState.answering_machine_edit_text)
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
    if not await db.fetch_one(f"SELECT true FROM answering_machine WHERE account_id={account_id} AND answer_id={answer_id}"):
        await message.answer(**await answering_machine_menu(account_id))  # Автоответ не найден
    elif not text:
        await message.answer("<b>Текст не должен быть пустым</b>", parse_mode=html,
                             reply_markup=(await auto_answer_menu(message.chat.id, answer_id))['reply_markup'])
    elif message.content_type not in ("text", "photo", "video"):
        await message.answer("<b>Ваше сообщение не является текстом, фото или видео</b>", parse_mode=html,
                             reply_markup=(await auto_answer_menu(message.chat.id, answer_id))['reply_markup'])
    elif len(text) > 512:
        await message.answer("<b>Ваше сообщение слишком длинное</b>", parse_mode=html,
                             reply_markup=(await auto_answer_menu(message.chat.id, answer_id))['reply_markup'])
    elif file and file.file_size / 2**20 > 10:
        await message.answer("<b>Ваше медиа слишком большое</b>", parse_mode=html,
                             reply_markup=(await answering_machine_menu(message.chat.id))['reply_markup'])
    elif text != "Отмена":
        entities = json_encode([entity.model_dump() for entity in message.entities or message.caption_entities or []])
        media = None
        last_media = await db.fetch_one(f"SELECT media FROM answering_machine "
                                        f"WHERE account_id={account_id} AND answer_id={answer_id}", one_data=True)
        if last_media:
            access_hash = last_media // 10
            ext = 'png' if last_media % 10 == 1 else 'mp4'
            os.remove(www_path(f"answering_machine/{account_id}.{answer_id}.{access_hash}.{ext}"))
        if message.photo or message.video:
            access_hash = random.randint(10**10, 10**12-1)
            ext = 'png' if message.photo else 'mp4'
            media = access_hash * 10 + (1 if ext == 'png' else 2)
            path = www_path(f"answering_machine/{account_id}.{answer_id}.{access_hash}.{ext}")
            await bot.download(file.file_id, path)
        await db.execute(f"UPDATE answering_machine SET text=$1, entities='{entities}', media=$2 "
                         f"WHERE account_id={account_id} AND answer_id={answer_id}", text, media)  # Изменение автоответа
        await message.answer(**await auto_answer_menu(account_id, answer_id))
    else:
        await message.answer(**await auto_answer_menu(account_id, answer_id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data.startswith("answering_machine_time").__or__(F.data.startswith("answering_machine_weekdays")))
@security()
async def _answering_machine_time(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_time", "").replace("answering_machine_weekdays", ""))
    await callback_query.message.edit_text(**await time_auto_answer_menu(callback_query.from_user.id, answer_id))


async def time_auto_answer_menu(account_id: int, answer_id: int) -> dict[str, Any]:
    answer = await db.fetch_one(f"SELECT type, start_time, end_time, weekdays FROM answering_machine "
                                f"WHERE account_id={account_id} AND answer_id={answer_id}")
    if answer['type'] == "ordinary":  # Обыкновенный автоответ — расписание отсутствует
        reply_markup = IMarkup(inline_keyboard=
                               [[IButton(text="⏰ Выбрать время", callback_data=f"answering_machine_edit_timetable{answer_id}")],
                                [IButton(text="◀️  Назад", callback_data=f"answering_machine_menu{answer_id}")]])
        return {"text": f"Вы можете добавить расписание, чтобы я отвечал только в нужное время",
                "reply_markup": reply_markup, "parse_mode": html}
    elif answer['type'] == "timetable":  # Автоответ с расписанием
        reply_markup = IMarkup(inline_keyboard=[[IButton(text="➡️ Начало", callback_data=f"answering_machine_edit_start_time_{answer_id}"),
                                                IButton(text="Окончание ⬅️", callback_data=f"answering_machine_edit_end_time_{answer_id}")],
                                                [IButton(text="🗓 Дни недели", callback_data=f"answering_machine_edit_weekdays{answer_id}")],
                                                [IButton(text="❌ Удалить расписание", callback_data=f"answering_machine_del_time{answer_id}")],
                                                [IButton(text="◀️  Назад", callback_data=f"answering_machine_menu{answer_id}")]])
        time_zone = await db.fetch_one(f"SELECT time_zone FROM settings WHERE account_id={account_id}", one_data=True)
        hours_start_time = str((answer['start_time'].hour + time_zone) % 24).rjust(2, "0")
        minutes_start_time = str(answer['start_time'].minute).rjust(2, "0")
        hours_end_time = str((answer['end_time'].hour + time_zone) % 24).rjust(2, "0")
        minutes_end_time = str(answer['end_time'].minute).rjust(2, "0")
        weekdays = get_weekdays_string_by_list(answer['weekdays'])
        return {"text": f"Вы можете изменить или удалить расписание автоответа\n"
                        f"{hours_start_time}:{minutes_start_time} — {hours_end_time}:{minutes_end_time}\nДни работы: {weekdays}",
                "reply_markup": reply_markup, "parse_mode": html}


@dp.callback_query(F.data.startswith("answering_machine_edit_timetable"))
@security('state')
async def _answering_machine_edit_timetable_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_edit_timetable", ""))
    await state.set_state(UserState.answering_machine_edit_timetable)
    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Напишите <b>время</b>, в течение которого будет работать автоответ\n"
                                                      "Например: 22:00 - 6:00", parse_mode=html, reply_markup=markup)).message_id
    await state.update_data(message_id=message_id, answer_id=answer_id)
    await callback_query.message.delete()


@dp.message(UserState.answering_machine_edit_timetable)
@security('state')
async def _answering_machine_edit_timetable(message: Message, state: FSMContext):
    if await new_message(message): return
    data = await state.get_data()
    answer_id = data['answer_id']
    message_id = data['message_id']
    await state.clear()
    account_id = message.chat.id
    if not await db.fetch_one(f"SELECT true FROM answering_machine WHERE account_id={account_id} AND answer_id={answer_id}"):
        await message.answer(**await answering_machine_menu(account_id))  # Автоответ не найден
    elif message.content_type != "text":
        await message.answer("<b>Ваше сообщение не является текстом</b>", parse_mode=html,
                             reply_markup=(await time_auto_answer_menu(message.chat.id, answer_id))['reply_markup'])
    elif message.text != "Отмена":
        text = message.text.replace(" ", "")
        if not re.fullmatch(r'\d{1,2}:\d{1,2}-\d{1,2}:\d{1,2}', text):  # Некорректный формат
            await message.answer("<b>Некорректный формат расписания</b>", parse_mode=html,
                                 reply_markup=(await time_auto_answer_menu(message.chat.id, answer_id))['reply_markup'])
        else:
            time_zone = await db.fetch_one(f"SELECT time_zone FROM settings WHERE account_id={account_id}", one_data=True)
            start_time, end_time = text.split("-")
            hours_start_time, minutes_start_time = map(int, start_time.split(":"))
            hours_start_time = (hours_start_time - time_zone) % 24
            hours_end_time, minutes_end_time = map(int, end_time.split(":"))
            hours_end_time = (hours_end_time - time_zone) % 24
            if (hours_start_time, minutes_start_time) == (hours_end_time, minutes_end_time):  # Одинаковые start_time и end_time
                await message.answer("<b>Некорректный формат расписания</b>", parse_mode=html,
                                     reply_markup=(await time_auto_answer_menu(message.chat.id, answer_id))['reply_markup'])
            else:
                await db.execute(f"UPDATE answering_machine SET status=false, type='timetable', "
                                 f"start_time='{hours_start_time}:{minutes_start_time}', "
                                 f"end_time='{hours_end_time}:{minutes_end_time}', weekdays='{list(range(7))}' "
                                 f"WHERE account_id={account_id} AND answer_id={answer_id}")
                await message.answer(**await time_auto_answer_menu(account_id, answer_id))
    else:
        await message.answer(**await time_auto_answer_menu(message.chat.id, answer_id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data.startswith("answering_machine_edit_start_time").__or__(F.data.startswith("answering_machine_edit_end_time")))
@security('state')
async def _answering_machine_edit_time_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    type_time = "_".join(callback_query.data.split("_")[3:5])  # start_time или end_time
    answer_id = int(callback_query.data.split("_")[-1])
    await state.set_state(UserState.answering_machine_edit_time)
    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    if type_time == "start_time":
        text = "Напишите <b>начало</b> работы автоответа\nНапример: 22:00"
    else:
        text = "Напишите <b>окончание</b> работы автоответа\nНапример: 06:00"
    message_id = (await callback_query.message.answer(text, parse_mode=html, reply_markup=markup)).message_id
    await state.update_data(message_id=message_id, answer_id=answer_id, type_time=type_time)
    await callback_query.message.delete()


@dp.message(UserState.answering_machine_edit_time)
@security('state')
async def _answering_machine_edit_time(message: Message, state: FSMContext):
    if await new_message(message): return
    data = await state.get_data()
    answer_id = data['answer_id']
    message_id = data['message_id']
    type_time = data['type_time']
    await state.clear()
    account_id = message.chat.id
    if not await db.fetch_one(f"SELECT true FROM answering_machine WHERE account_id={account_id} AND answer_id={answer_id}"):
        await message.answer(**await answering_machine_menu(account_id))  # Автоответ не найден
    elif message.content_type != "text":
        await message.answer("<b>Ваше сообщение не является текстом</b>", parse_mode=html,
                             reply_markup=(await time_auto_answer_menu(message.chat.id, answer_id))['reply_markup'])
    elif message.text != "Отмена":
        text = message.text.replace(" ", "")
        if not re.fullmatch(r'\d{1,2}:\d{1,2}', text):  # Некорректный формат
            await message.answer("<b>Некорректный формат времени</b>", parse_mode=html,
                                 reply_markup=(await time_auto_answer_menu(message.chat.id, answer_id))['reply_markup'])
        else:
            other_type_time = "start_time" if type_time == "end_time" else "end_time"
            other_time = await db.fetch_one(f"SELECT {other_type_time} FROM answering_machine "
                                            f"WHERE account_id={account_id} AND answer_id={answer_id}", one_data=True)
            time_zone = await db.fetch_one(f"SELECT time_zone FROM settings WHERE account_id={account_id}", one_data=True)
            hours, minutes = map(int, text.split(":"))
            hours = (hours - time_zone) % 24
            if (hours, minutes) == tuple(map(int, other_time.strftime("%H:%M").split(":"))):
                await message.answer("<b>Начало и окончание расписания совпадают</b>", parse_mode=html,
                                     reply_markup=(await time_auto_answer_menu(message.chat.id, answer_id))['reply_markup'])
            else:
                await db.execute(f"UPDATE answering_machine SET status=false, {type_time}='{hours}:{minutes}' "
                                 f"WHERE account_id={account_id} AND answer_id={answer_id}")
                await message.answer(**await time_auto_answer_menu(account_id, answer_id))
    else:
        await message.answer(**await time_auto_answer_menu(message.chat.id, answer_id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data.startswith("answering_machine_edit_weekdays"))
@security('state')
async def _answering_machine_edit_weekdays(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_edit_weekdays", ""))
    await state.set_state(UserState.answering_machine_edit_weekdays)
    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    text = "Напишите <b>дни недели</b> работы автоответа через запятую\nНапример: пн, вт, ср, чт, пт"
    message_id = (await callback_query.message.answer(text, parse_mode=html, reply_markup=markup)).message_id
    await state.update_data(message_id=message_id, answer_id=answer_id)
    await callback_query.message.delete()


@dp.message(UserState.answering_machine_edit_weekdays)
@security('state')
async def _answering_machine_edit_time(message: Message, state: FSMContext):
    if await new_message(message): return
    data = await state.get_data()
    answer_id = data['answer_id']
    message_id = data['message_id']
    await state.clear()
    account_id = message.chat.id
    if not await db.fetch_one(f"SELECT true FROM answering_machine WHERE account_id={account_id} AND answer_id={answer_id}"):
        await message.answer(**await answering_machine_menu(account_id))  # Автоответ не найден
    elif message.content_type != "text":
        await message.answer("<b>Ваше сообщение не является текстом</b>", parse_mode=html,
                             reply_markup=(await time_auto_answer_menu(message.chat.id, answer_id))['reply_markup'])
    elif message.text != "Отмена":
        try:
            weekdays = get_weekdays_list_by_string(message.text.lower())
        except KeyError:
            await message.answer("<b>Некорректный формат дней</b>", parse_mode=html,
                                 reply_markup=(await time_auto_answer_menu(message.chat.id, answer_id))['reply_markup'])
        else:
            await db.execute(f"UPDATE answering_machine SET status=false, weekdays='{weekdays}' "
                             f"WHERE account_id={account_id} AND answer_id={answer_id}")
            await message.answer(**await time_auto_answer_menu(account_id, answer_id))
    else:
        await message.answer(**await time_auto_answer_menu(message.chat.id, answer_id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data.startswith("answering_machine_del_time"))
@security()
async def _answering_machine_del_time(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_del_time", ""))
    account_id = callback_query.from_user.id
    await db.execute(f"UPDATE answering_machine SET status=false, type='ordinary', start_time=NULL, end_time=NULL, weekdays=NULL "
                     f"WHERE account_id={account_id} AND answer_id={answer_id}")
    await callback_query.message.edit_text(**await auto_answer_menu(account_id, answer_id))


@dp.callback_query(F.data.startswith("answering_machine_contacts"))
@security()
async def _answering_machine_contacts_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command, answer_id = callback_query.data.replace("answering_machine_contacts_", "").split("_")
    account_id = callback_query.from_user.id
    answer = await db.fetch_one(f"SELECT contacts FROM answering_machine WHERE account_id={account_id} AND answer_id={answer_id}")
    if answer is None:
        await callback_query.answer("Автоответ был удален ранее!", True)
        return await callback_query.message.edit_text(**await answering_machine_menu(account_id))
    if (command == "on") == answer['contacts']:
        return await callback_query.message.edit_text(**await auto_answer_menu(account_id, answer_id))
    contacts = "true" if command == "on" else "false"
    await db.execute(f"UPDATE answering_machine SET contacts={contacts} WHERE account_id={account_id} AND answer_id={answer_id}")
    await callback_query.message.edit_text(**await auto_answer_menu(account_id, answer_id))


def answering_machine_initial():
    pass  # Чтобы PyCharm не ругался
