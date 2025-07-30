import re

from mg.config import BLOG_SITE, WWW_SITE

from aiogram import F

from aiogram.fsm.context import FSMContext
from mg.bot.types import dp, bot, CallbackData, UserState
from aiogram.types import CallbackQuery, Message, KeyboardButtonRequestUsers
from mg.bot.functions import new_callback_query, new_message, preview_options, request_user

from aiogram.types import KeyboardButton as KButton
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton

from typing import Any
from datetime import time
from mg.core.types import morning
from mg.core.functions import error_notify, serialize_aiogram_entities, get_time_zone, full_name, get_subscription

from . types import AutoAnswer, week
from . functions import (
    add_auto_answer,
    get_auto_answer,
    get_auto_answers,
    edit_auto_answer,
    delete_auto_answer,
    add_auto_answer_chat,
    intersection_triggers,
    set_status_auto_answer,
    add_auto_answer_trigger,
    delete_auto_answer_chat,
    check_count_auto_answers,
    set_auto_answer_settings,
    edit_auto_answer_weekdays,
    delete_auto_answer_trigger,
    edit_auto_answer_timetable,
    get_link_auto_answer_media,
    delete_auto_answer_timetable,
    disable_ordinary_auto_answers,
    check_count_auto_answer_chats,
    check_count_auto_answer_triggers,
    intersection_auto_answers_by_timetable,
    intersection_ordinary_auto_answers_by_triggers,
    intersection_timetable_auto_answers_by_triggers,
)


cb = CallbackData()
MAX_LENGTH_TEXT = 1024
MAX_LENGTH_TRIGGER = 32
MAX_FILE_SIZE = 20 * 2**20  # 20 МБ
TIMETABLE_RE = re.compile(r'(\d{1,2})[:.](\d{1,2})[-–—]((\d{1,2})[:.](\d{1,2})|допробуждения)')
WEEKDAYS_RE = re.compile(r'(пн|вт|ср|чт|пт|сб|вс)(,(пн|вт|ср|чт|пт|сб|вс))*')


@dp.callback_query(F.data.startswith(cb.command('answering_machine')))
@error_notify()
async def _answering_machine(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    prev = cb.deserialize(callback_query.data).get(0) is True
    await callback_query.message.edit_text(**await answering_machine_menu(callback_query.from_user.id, prev=prev))


async def answering_machine_menu(account_id: int, prev: bool = False) -> dict[str, Any]:
    answers = [] if prev else await get_auto_answers(account_id)
    buttons = [[IButton(text=answer.short_text, callback_data=cb('auto_answer', answer.id))] for answer in answers]

    markup = IMarkup(inline_keyboard=[*buttons,
                                      [IButton(text="➕ Создать новый ответ", callback_data=cb('new_auto_answer', prev))],
                                      [IButton(text="◀️  Назад", callback_data=cb('menu'))]])

    return dict(
        text="🤖 <b>Автоответчик</b>\nАвтоответчик будет отправлять заготовленный ответ вашим собеседникам, когда это будет необходимо. "
             f"Справиться со всеми настройками поможет <a href='{BLOG_SITE}/автоответчик-maksogram'>обзор</a>", reply_markup=markup, disable_web_page_preview=True)


@dp.callback_query(F.data.startswith(cb.command('new_auto_answer')))
@error_notify('state')
async def _new_auto_answer_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    prev = cb.deserialize(callback_query.data).get(0) is True
    if prev:
        await callback_query.answer("Запустите Maksogram кнопкой в меню", True)
        return

    if not await check_count_auto_answers(account_id):
        if await get_subscription(account_id) is None:
            await callback_query.answer("Достигнут лимит автоответов, подключите Maksogram Premium!", True)
        else:
            await callback_query.answer("Достигнут лимит количество автоответов!", True)
        return

    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте содержание (текст, фото или видео) автоответа", reply_markup=markup)).message_id

    await state.set_state(UserState.auto_answer)
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.auto_answer)  # Создание автоответа и его изменение
@error_notify('state')
async def _auto_answer(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    data = await state.get_data()
    message_id = data['message_id']
    answer_id = data.get('answer_id')

    warning = None
    text = message.text or message.caption
    entities = message.entities or message.caption_entities or []
    file = (message.photo and message.photo[-1]) or message.video

    if message.text == "Отмена":
        await state.clear()
        if answer_id:
            await message.answer(**await auto_answer_menu(account_id, answer_id))
        else:
            await message.answer(**await answering_machine_menu(account_id))
    elif message.content_type not in ('text', 'photo', 'video'):
        warning = "Содержание автоответа должно быть текстом, фото или видео"
    elif not text:
        warning = "Текст автоответа не может быть пустым"
    elif len(text) > MAX_LENGTH_TEXT:
        warning = "Текст сообщения слишком длинный"
    elif file and file.file_size > MAX_FILE_SIZE:
        warning = "Медиа слишком большое"
    else:
        await state.clear()

        json_entities = serialize_aiogram_entities(entities)
        media_id, ext = None, None

        if file:
            media_id = file.file_id
            ext = 'mp4' if message.video else 'png'

        if answer_id:  # Необходимо изменить текст автоответа
            if await edit_auto_answer(account_id, answer_id, text, json_entities, media_id, ext):  # Быстрый ответ изменен
                await message.answer(**await auto_answer_menu(account_id, answer_id))
            else:  # Быстрый ответ не найден
                await message.answer(**await answering_machine_menu(account_id))

        else:  # Необходимо создать новый автоответ
            answer_id = await add_auto_answer(account_id, text, json_entities, media_id, ext)
            await message.answer(**await auto_answer_menu(account_id, answer_id))

    if warning:
        markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
        new_message_id = (await message.answer(warning, reply_markup=markup)).message_id
        await state.update_data(message_id=new_message_id)

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data.startswith(cb.command('auto_answer')))
@error_notify()
async def _auto_answer(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = cb.deserialize(callback_query.data)[0]
    await callback_query.message.edit_text(**await auto_answer_menu(callback_query.from_user.id, answer_id))


async def auto_answer_menu(account_id: int, answer_id: int) -> dict[str, Any]:
    answer = await get_auto_answer(account_id, answer_id)
    if answer is None:
        return await answering_machine_menu(account_id)

    time_button = IButton(text="⏰ Расписание", callback_data=cb('auto_answer_time', answer_id))
    triggers_button = IButton(text="🔀 Триггеры", callback_data=cb('auto_answer_triggers', answer_id))
    buttons = [[time_button, triggers_button]]

    if answer.start_time:
        time_button = IButton(text=f"⏰ {answer.human_timetable} {answer.human_weekdays}",
                              callback_data=cb('auto_answer_time', answer_id))
    if answer.triggers:
        triggers_button = IButton(text=f"🔀 {answer.short_human_triggers}", callback_data=cb('auto_answer_triggers', answer_id))
    if answer.start_time or answer.triggers:
        buttons = [[time_button], [triggers_button]]

    status_button = IButton(text="🟢" if answer.status else "🔴", callback_data=cb('auto_answer_switch', answer_id, not answer.status))
    markup = IMarkup(inline_keyboard=[[IButton(text="🚫 Удал", callback_data=cb('del_auto_answer', answer_id)),
                                       status_button,
                                       IButton(text="✏️ Измен", callback_data=cb('edit_auto_answer', answer_id))],
                                      *buttons,
                                      [IButton(text="⚙️ Настройки автоответа", callback_data=cb('auto_answer_settings', answer_id))],
                                      [IButton(text="◀️  Назад", callback_data=cb('answering_machine'))]])

    preview = None
    if answer.media:
        preview = preview_options(get_link_auto_answer_media(account_id, answer_id, answer.media.access_hash, answer.media.ext),
                                  site=WWW_SITE, show_above_text=True)

    return dict(text=answer.text, entities=answer.entities, reply_markup=markup, link_preview_options=preview, parse_mode=None)


@dp.callback_query(F.data.startswith(cb.command('auto_answer_switch')))
@error_notify()
async def _auto_answer_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    answer_id, command = cb.deserialize(callback_query.data)

    answer = await get_auto_answer(account_id, answer_id)
    if answer is None:
        await callback_query.message.edit_text(**await answering_machine_menu(account_id))
        return

    if command == answer.status:
        await callback_query.message.edit_text(**await auto_answer_menu(account_id, answer_id))
        return

    if command:
        await enable_auto_answer(callback_query, account_id, answer)
    else:
        await disable_auto_answer(callback_query, account_id, answer)

    await callback_query.message.edit_text(**await auto_answer_menu(account_id, answer_id))


async def disable_auto_answer(callback_query: CallbackQuery, account_id: int, answer: AutoAnswer):
    await set_status_auto_answer(account_id, answer.id, False)
    await callback_query.answer("Автоответ выключен", True)


async def enable_auto_answer(callback_query: CallbackQuery, account_id: int, answer: AutoAnswer):
    # п 1 Примечания к функции get_enabled_auto_answer: Включенный обыкновенный автоответ без триггеров может быть только один
    if not answer.start_time and not answer.triggers:
        await disable_ordinary_auto_answers(account_id)  # Выключает другой включенный обыкновенный автоответ без триггеров

    # п 2 Примечания к функции get_enabled_auto_answer: Включенные обыкновенные автоответы не должны иметь одинаковых триггеров
    elif not answer.start_time and answer.triggers:
        if await intersection_ordinary_auto_answers_by_triggers(account_id, answer):  # Есть общие триггеры
            await callback_query.answer("Обыкновенные автоответы (без расписания) не должны иметь общих триггеров", True)
            return

    # п 4 Примечания к функции get_enabled_auto_answer: Включенные автоответы по расписанию с пересечением по времени не должны иметь одинаковых триггеров
    elif answer.start_time and answer.triggers:
        if await intersection_timetable_auto_answers_by_triggers(account_id, answer):  # Есть общие триггеры у пересекающихся по расписанию автоответов
            await callback_query.answer("Автоответы с пересекающимся расписанием не должны иметь общих триггеров", True)
            return

    # п 3 Примечания к функции get_enabled_auto_answer: Включенные автоответы по расписанию без триггеров не должны пересекаться по времени
    elif answer.start_time and not answer.triggers:
        if await intersection_auto_answers_by_timetable(account_id, answer):  # Расписание пересекается
            await callback_query.answer("Расписание автоответов без триггеров не должно пересекаться", True)
            return

    await set_status_auto_answer(account_id, answer.id, True)
    await callback_query.answer("Автоответ включен", True)


@dp.callback_query(F.data.startswith(cb.command('edit_auto_answer')))
@error_notify('state')
async def _edit_auto_answer(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    answer_id = cb.deserialize(callback_query.data)[0]

    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте содержание (текст, фото или видео) автоответа", reply_markup=markup)).message_id

    await state.set_state(UserState.auto_answer)
    await state.update_data(answer_id=answer_id, message_id=message_id)
    await callback_query.message.delete()


@dp.callback_query(F.data.startswith(cb.command('auto_answer_time')))
@error_notify()
async def _auto_answer_time(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = cb.deserialize(callback_query.data)[0]
    await callback_query.message.edit_text(**await auto_answer_time(callback_query.from_user.id, answer_id))


async def auto_answer_time(account_id: int, answer_id: int) -> dict[str, Any]:
    answer = await get_auto_answer(account_id, answer_id)
    if answer is None:
        return await answering_machine_menu(account_id)

    if not answer.start_time:  # Обыкновенный автоответ — расписание отсутствует
        markup = IMarkup(inline_keyboard=[[IButton(text="⏰ Выбрать время",
                                                         callback_data=cb('edit_auto_answer_timetable', answer_id))],
                                          [IButton(text="◀️  Назад", callback_data=cb('auto_answer', answer_id))]])

        return dict(
            text="Вы можете добавить расписание, чтобы автоответ работал только в нужное время\n"
                 "<blockquote>Для улучшения точности выберите часовой пояс в настройках /settings</blockquote>", reply_markup=markup)

    markup = IMarkup(inline_keyboard=[[IButton(text="⏰ Расписание", callback_data=cb('edit_auto_answer_timetable', answer_id)),
                                       IButton(text="🗓 Дни недели", callback_data=cb('edit_auto_answer_weekdays', answer_id))],
                                      [IButton(text="❌ Удалить расписание", callback_data=cb('del_auto_answer_timetable', answer_id))],
                                      [IButton(text="◀️  Назад", callback_data=cb('auto_answer', answer_id))]])

    return dict(
        text=f"Вы можете изменить или удалить расписание автоответа\n{answer.human_timetable}\nДни работы: {answer.human_weekdays}\n"
             "<blockquote>❗️ Для улучшения точности выберите часовой пояс в /settings</blockquote>", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('edit_auto_answer_timetable')))
@error_notify('state')
async def _edit_auto_answer_timetable_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    answer_id = cb.deserialize(callback_query.data)[0]

    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], input_field_placeholder="22:00 - 06:00", resize_keyboard=True)
    message_id = (await callback_query.message.answer(
        "Отправьте <b>время</b>, в течение которого будет работать автоответ\nНапример: 22:00 - 6:00\n"
        "<blockquote expandable>В качестве окончания можно выбрать <b>до пробуждения</b>. В таком случае автоответ будет работать "
        f"до того, как вы первый раз зайдете в сеть утром или до {morning[1]:02d}:00 (если утром в сети вы не появитесь)\n"
        "Например: 22:00 - до пробуждения</blockquote>", reply_markup=markup)).message_id

    await state.set_state(UserState.edit_auto_answer_timetable)
    await state.update_data(answer_id=answer_id, message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.edit_auto_answer_timetable)
@error_notify('state')
async def _edit_auto_answer_timetable(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    data = await state.get_data()
    message_id = data['message_id']
    answer_id = data['answer_id']

    warning = None
    text = message.text.replace(' ', '') if message.text else None

    if message.text == "Отмена":
        await state.clear()
        await message.answer(**await auto_answer_time(account_id, answer_id))
    elif not (answer := await get_auto_answer(account_id, answer_id)):
        await state.clear()
        await message.answer(**await answering_machine_menu(account_id))
    elif not message.text or not (match := re.fullmatch(TIMETABLE_RE, text)):
        warning = "Некорректное расписание автоответа\nНапример: 22:00 - 6:00"
    else:
        time_zone = await get_time_zone(account_id)
        hours_start_time, minutes_start_time, end_time, hours_end_time, minutes_end_time = match.groups()

        hours_start_time, minutes_start_time = int(hours_start_time), int(minutes_start_time)
        if end_time != 'допробуждения':
            hours_end_time, minutes_end_time = int(hours_end_time), int(minutes_end_time)

        try:  # Время начала и окончания должны быть корректны и не должны быть одинаковыми
            assert time(hours_start_time, minutes_start_time) != (end_time == 'допробуждения' or time(hours_end_time, minutes_end_time))
        except ValueError:
            warning = "Некорректное время! Пример: 22:00 - 6:00"
        except AssertionError:
            warning = "Начало и окончание расписания не должно совпадать"
        else:
            await state.clear()

            hours_start_time = (hours_start_time - time_zone) % 24
            hours_end_time = (hours_end_time - time_zone) % 24 if isinstance(hours_end_time, int) else None

            await edit_auto_answer_timetable(account_id, answer_id, time(hours_start_time, minutes_start_time),
                                             hours_end_time and time(hours_end_time, minutes_end_time))  # None, если end_time = до пробуждения

            if answer.status:
                # п 3 Примечания к функции get_enabled_auto_answer: Включенные автоответы по расписанию без триггеров не должны пересекаться по времени
                if not answer.triggers:
                    if await intersection_auto_answers_by_timetable(account_id, answer):  # Расписания пересекаются
                        await set_status_auto_answer(account_id, answer_id, False)

                # п 4 Примечания к функции get_enabled_auto_answer: Включенные автоответы по расписанию с пересечением по времени не должны иметь одинаковых триггеров
                else:  # answer.triggers
                    if await intersection_timetable_auto_answers_by_triggers(account_id, answer):  # Есть общие триггеры у пересекающихся по расписанию автоответов
                        await set_status_auto_answer(account_id, answer_id, False)

            await message.answer(**await auto_answer_time(account_id, answer_id))

    if warning:
        markup = KMarkup(keyboard=[[KButton(text="Отмена")]], input_field_placeholder="22:00 - 06:00", resize_keyboard=True)
        new_message_id = (await message.answer(warning, reply_markup=markup)).message_id
        await state.update_data(message_id=new_message_id)

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data.startswith(cb.command('edit_auto_answer_weekdays')))
@error_notify('state')
async def _edit_auto_answer_weekdays_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    answer_id = cb.deserialize(callback_query.data)[0]

    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], input_field_placeholder="пн, вт, ср, чт, пт", resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте <b>дни недели</b> работы автоответа через запятую\n"
                                                      "Например: пн, вт, ср, чт, пт", reply_markup=markup)).message_id

    await state.set_state(UserState.edit_auto_answer_weekdays)
    await state.update_data(answer_id=answer_id, message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.edit_auto_answer_weekdays)
@error_notify('state')
async def _edit_auto_answer_weekdays(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    data = await state.get_data()
    message_id = data['message_id']
    answer_id = data['answer_id']

    warning = None
    text = message.text.lower().replace(' ', '') if message.text else None

    if message.text == "Отмена":
        await state.clear()
        await message.answer(**await auto_answer_time(account_id, answer_id))
    elif not (answer := await get_auto_answer(account_id, answer_id)):
        await state.clear()
        await message.answer(**await answering_machine_menu(account_id))
    elif not message.text or not re.fullmatch(WEEKDAYS_RE, text):
        warning = "Отправьте <b>дни недели</b> работы автоответа через запятую\nНапример: пн, вт, ср, чт, пт"
    else:
        await state.clear()
        weekdays = list(set([week.index(weekday) for weekday in text.split(',')]))  # Список целых чисел дней недели в порядке возрастания

        await edit_auto_answer_weekdays(account_id, answer_id, weekdays)

        if answer.status:
            # п 3 Примечания к функции get_enabled_auto_answer: Включенные автоответы по расписанию без триггеров не должны пересекаться по времени
            if not answer.triggers:
                if await intersection_auto_answers_by_timetable(account_id, answer):  # Расписания пересекаются
                    await set_status_auto_answer(account_id, answer_id, False)

            # п 4 Примечания к функции get_enabled_auto_answer: Включенные автоответы по расписанию с пересечением по времени не должны иметь одинаковых триггеров
            else:  # answer.triggers
                if await intersection_timetable_auto_answers_by_triggers(account_id, answer):  # Есть общие триггеры у пересекающихся по расписанию автоответов
                    await set_status_auto_answer(account_id, answer_id, False)

        await message.answer(**await auto_answer_time(account_id, answer_id))

    if warning:
        markup = KMarkup(keyboard=[[KButton(text="Отмена")]], input_field_placeholder="пн, вт, ср, чт, пт", resize_keyboard=True)
        new_message_id = (await message.answer(warning, reply_markup=markup)).message_id
        await state.update_data(message_id=new_message_id)

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data.startswith(cb.command('del_auto_answer_timetable')))
@error_notify()
async def _delete_auto_answer_timetable(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    answer_id = cb.deserialize(callback_query.data)[0]

    await delete_auto_answer_timetable(account_id, answer_id)
    await callback_query.message.edit_text(**await auto_answer_menu(account_id, answer_id))


@dp.callback_query(F.data.startswith(cb.command('auto_answer_triggers')))
@error_notify()
async def _auto_answer_triggers(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = cb.deserialize(callback_query.data)[0]
    await callback_query.message.edit_text(**await auto_answer_triggers(callback_query.from_user.id, answer_id))


async def auto_answer_triggers(account_id: int, answer_id: int) -> dict[str, Any]:
    answer = await get_auto_answer(account_id, answer_id)
    if answer is None:
        return await answering_machine_menu(account_id)

    trigger_ids, triggers = list(answer.short_triggers.keys()), list(answer.short_triggers.values())

    i, buttons = 0, []
    while i < len(triggers):  # Если длина триггера достаточно короткая, то помещаем 2 в ряд, иначе 1
        if i + 1 < len(triggers) and len(triggers[i]) <= 15 and len(triggers[i+1]) <= 15:
            buttons.append([IButton(text=f"🚫 {triggers[i]}", callback_data=cb('del_auto_answer_trigger', answer_id, trigger_ids[i])),
                            IButton(text=f"🚫 {triggers[i+1]}", callback_data=cb('del_auto_answer_trigger', answer_id, trigger_ids[i+1]))])
            i += 1
        else:
            buttons.append([IButton(text=f"🚫 {triggers[i]}", callback_data=cb('del_auto_answer_trigger', answer_id, trigger_ids[i]))])
        i += 1

    markup = IMarkup(inline_keyboard=[*buttons,
                                      [IButton(text="➕ Добавить триггер", callback_data=cb('new_auto_answer_trigger', answer_id))],
                                      [IButton(text="◀️  Назад", callback_data=cb('auto_answer', answer_id))]])

    return dict(
        text="🔀 <b>Триггеры для автоответа</b>\nАвтоответ будет срабатывать, только если в сообщении есть хотя бы один триггер", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('new_auto_answer_trigger')))
@error_notify('state')
async def _new_auto_answer_trigger_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    answer_id = cb.deserialize(callback_query.data)[0]

    if not await check_count_auto_answer_triggers(account_id, answer_id):
        if await get_subscription(account_id) is None:
            await callback_query.answer("Достигнут лимит триггеров, подключите Maksogram Premium!", True)
        else:
            await callback_query.answer("Достигнут лимит количества триггеров!", True)
        return

    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте <b>текст триггера</b>", reply_markup=markup)).message_id

    await state.set_state(UserState.auto_answer_trigger)
    await state.update_data(answer_id=answer_id, message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.auto_answer_trigger)
@error_notify('state')
async def _auto_answer_trigger(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    data = await state.get_data()
    message_id = data['message_id']
    answer_id = data['answer_id']

    warning = None
    trigger = message.text.lower().strip() if message.text else None

    if message.text == "Отмена":
        await state.clear()
        await message.answer(**await auto_answer_triggers(account_id, answer_id))
    elif not (answer := await get_auto_answer(account_id, answer_id)):
        await state.clear()
        await message.answer(**await answering_machine_menu(account_id))
    elif not message.text:
        warning = "Отправьте <b>текст триггера</b>"
    elif len(trigger) > MAX_LENGTH_TRIGGER:
        warning = f"Дина триггера должна быть меньше {MAX_LENGTH_TRIGGER}"
    elif intersection_triggers(answer.triggers.values(), [trigger]):
        warning = "Такой триггер (или похожий) уже есть"
    else:
        await state.clear()
        await add_auto_answer_trigger(account_id, answer_id, trigger)

        if answer.status:
            # п 2 Примечания к функции get_enabled_auto_answer: Включенные обыкновенные автоответы не должны иметь одинаковых триггеров
            if not answer.start_time:
                if await intersection_ordinary_auto_answers_by_triggers(account_id, answer):  # Есть общие триггеры
                    await set_status_auto_answer(account_id, answer_id, False)

            # п 4 Примечания к функции get_enabled_auto_answer: Включенные автоответы по расписанию с пересечением по времени не должны иметь одинаковых триггеров
            else:  # answer.start_time
                if await intersection_timetable_auto_answers_by_triggers(account_id, answer):  # Есть общие триггеры у пересекающихся по расписанию автоответов
                    await set_status_auto_answer(account_id, answer_id, False)

        await message.answer(**await auto_answer_triggers(account_id, answer_id))

    if warning:
        markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
        new_message_id = (await message.answer(warning, reply_markup=markup)).message_id
        await state.update_data(message_id=new_message_id)

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data.startswith(cb.command('del_auto_answer_trigger')))
@error_notify()
async def _del_auto_answer_trigger(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    answer_id, trigger_id = cb.deserialize(callback_query.data)

    await delete_auto_answer_trigger(account_id, answer_id, trigger_id)
    await callback_query.message.edit_text(**await auto_answer_triggers(account_id, answer_id))


@dp.callback_query(F.data.startswith(cb.command('auto_answer_settings')))
@error_notify()
async def _auto_answer_settings(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = cb.deserialize(callback_query.data)[0]
    await callback_query.message.edit_text(**await auto_answer_settings(callback_query.from_user.id, answer_id))


async def auto_answer_settings(account_id: int, answer_id: int) -> dict[str, Any]:
    answer = await get_auto_answer(account_id, answer_id)
    if answer is None:
        return await answering_machine_menu(account_id)

    offline_button = IButton(text=f"{'🟢' if answer.offline else '🔴'} Только когда не в сети",
                             callback_data=cb('auto_answer_settings_switch', answer_id, 'offline', not answer.offline))

    if answer.blacklist_chats:
        blacklist_chats_button = IButton(text="👇 Отвечать всем кроме 👇",
                                         callback_data=cb('auto_answer_settings_switch', answer_id, 'blacklist_chats', False))
    else:
        blacklist_chats_button = IButton(text="👇 Отвечать только 👇",
                                         callback_data=cb('auto_answer_settings_switch', answer_id, 'blacklist_chats', True))

    if answer.contacts is True:
        contacts_buttons = [IButton(text=f"🟢 {'Контактов' if answer.blacklist_chats else 'Контактам'}",
                                    callback_data=cb('auto_answer_settings_switch', answer_id, 'contacts', None))]
    elif answer.contacts is False:
        contacts_buttons = [IButton(text=f"🟢 {'Не контактов' if answer.blacklist_chats else 'Не контактам'}",
                                    callback_data=cb('auto_answer_settings_switch', answer_id, 'contacts', None))]
    else:
        contacts_buttons = [IButton(text=f"🔴 {'Контактов' if answer.blacklist_chats else 'Контактам'}",
                                    callback_data=cb('auto_answer_settings_switch', answer_id, 'contacts', True)),
                            IButton(text=f"🔴 {'Не контактов' if answer.blacklist_chats else 'Не контактам'}",
                                    callback_data=cb('auto_answer_settings_switch', answer_id, 'contacts', False))]

    chats_button = IButton(text=f"💬 {answer.short_human_chats}", callback_data=cb('auto_answer_chats', answer_id)) if answer.chats \
        else IButton(text="💬 Выбрать доп чаты", callback_data=cb('auto_answer_chats', answer_id))

    markup = IMarkup(inline_keyboard=[[offline_button],
                                      [blacklist_chats_button],
                                      contacts_buttons,
                                      [chats_button],
                                      [IButton(text="◀️  Назад", callback_data=cb('auto_answer', answer_id))]])

    return dict(
        text="⚙️ <b>Настройки автоответа</b>\n<i>Только когда не в сети</i> — автоответ не будет работать, если Вы в сети\n\nНажимайте на кнопки ниже, "
             f"чтобы понять в каких чатах будет работать автоответ: 👇\n<blockquote>{answer.chats_about}</blockquote>", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('auto_answer_settings_switch')))
@error_notify()
async def _auto_answer_settings_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    answer_id, function, command = cb.deserialize(callback_query.data)

    answer = await get_auto_answer(account_id, answer_id)
    if answer is None:
        await callback_query.message.edit_text(**await answering_machine_menu(account_id))
        return

    await set_auto_answer_settings(account_id, answer_id, function, command)
    await callback_query.message.edit_text(**await auto_answer_settings(account_id, answer_id))


@dp.callback_query(F.data.startswith(cb.command('auto_answer_chats')))
@error_notify()
async def _auto_answer_chats(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = cb.deserialize(callback_query.data)[0]
    await callback_query.message.edit_text(**await auto_answer_chats(callback_query.from_user.id, answer_id))


async def auto_answer_chats(account_id: int, answer_id: int) -> dict[str, Any]:
    answer = await get_auto_answer(account_id, answer_id)
    if answer is None:
        return await answering_machine_menu(account_id)

    chat_ids, chats = list(answer.short_chats.keys()), list(answer.short_chats.values())

    i, buttons = 0, []
    while i < len(chats):  # Если длина имени достаточно короткая, то помещаем 2 в ряд, иначе 1
        if i + 1 < len(chats) and len(chats[i]) <= 15 and len(chats[i+1]) <= 15:
            buttons.append([IButton(text=f"🚫 {chats[i]}",
                                    callback_data=cb('del_auto_answer_chat', answer_id, chat_ids[i])),
                            IButton(text=f"🚫 {chats[i+1]}",
                                    callback_data=cb('del_auto_answer_chat', answer_id, chat_ids[i+1]))])
            i += 1
        else:
            buttons.append([IButton(text=f"🚫 {chats[i]}",
                                    callback_data=cb('del_auto_answer_chat', answer_id, chat_ids[i]))])
        i += 1

    markup = IMarkup(inline_keyboard=[*buttons,
                                      [IButton(text="➕ Добавить доп чат", callback_data=cb('new_auto_answer_chat', answer_id))],
                                      [IButton(text="◀️  Назад", callback_data=cb('auto_answer_settings', answer_id))]])

    return dict(text=f"⚙️ <b>Доп чаты автоответа</b>\nДобавляйте и удаляйте чаты, чтобы изменить настройки 👇\n"
                     f"<blockquote>{answer.chats_about}</blockquote>", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('new_auto_answer_chat')))
@error_notify('state')
async def _new_auto_answer_chat_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    answer_id = cb.deserialize(callback_query.data)[0]

    if not await check_count_auto_answer_chats(account_id, answer_id):
        if await get_subscription(account_id) is None:
            await callback_query.answer("Достигнут лимит доп чатов, подключите Maksogram Premium!", True)
        else:
            await callback_query.answer("Достигнут лимит количества доп чатов!", True)
        return

    request = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False, max_quantity=1)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте пользователя кнопкой, ID, username или номер телефона", reply_markup=markup)).message_id

    await state.set_state(UserState.auto_answer_chat)
    await state.update_data(answer_id=answer_id, message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.auto_answer_chat)
@error_notify('state')
async def _auto_answer_chat(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    data = await state.get_data()
    message_id = data['message_id']
    answer_id = data['answer_id']

    if message.text == "Отмена":
        await state.clear()
        await message.answer(**await auto_answer_chats(account_id, answer_id))
    else:
        response = await request_user(message, can_yourself=False)

        if not response.ok:
            request = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False, max_quantity=1)
            markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request)],
                                       [KButton(text="Отмена")]], resize_keyboard=True)
            new_message_id = (await message.answer(response.warning, reply_markup=markup)).message_id
            await state.update_data(message_id=new_message_id)
        else:
            await state.clear()
            name = full_name(response.user)

            await add_auto_answer_chat(account_id, answer_id, response.user.id, name)

            await message.answer(**await auto_answer_chats(account_id, answer_id))

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data.startswith(cb.command('del_auto_answer_chat')))
@error_notify()
async def _del_auto_answer_chat(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    answer_id, chat_id = cb.deserialize(callback_query.data)

    await delete_auto_answer_chat(account_id, answer_id, chat_id)
    await callback_query.message.edit_text(**await auto_answer_chats(account_id, answer_id))


@dp.callback_query(F.data.startswith(cb.command('del_auto_answer')))
@error_notify()
async def _del_auto_answer(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    answer_id = cb.deserialize(callback_query.data)[0]

    await delete_auto_answer(account_id, answer_id)
    await callback_query.message.edit_text(**await answering_machine_menu(account_id))


def answering_machine_initial():
    pass  # Чтобы PyCharm не ругался
