from typing import Any
from html import escape
from modules.weather import check_city
from asyncpg.exceptions import UniqueViolationError
from core import (
    db,
    html,
    SITE,
    OWNER,
    security,
    unzip_int_data,
    preview_options,
)

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, CommandStart
from aiogram.types import KeyboardButton as KButton
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import ReplyKeyboardRemove as KRemove
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from .core import (
    dp,
    bot,
    Data,
    UserState,
    new_message,
    new_callback_query,
    username_acquaintance,
)
from aiogram.types import (
    Message,
    WebAppInfo,
    CallbackQuery,
)


@dp.message(CommandStart())
@security('state')
async def _start(message: Message, state: FSMContext):
    if await new_message(message): return
    await state.clear()
    service_message = await message.answer("...", reply_markup=KRemove())
    if await db.fetch_one(f"SELECT true FROM accounts WHERE account_id={message.chat.id}", one_data=True):  # Зарегистрирован(а)
        markup = IMarkup(inline_keyboard=[[IButton(text="⚙️ Меню и настройки", callback_data="menu")]])
    else:
        markup = IMarkup(inline_keyboard=[[IButton(text="🚀 Запустить бота", callback_data="menu")]])
    acquaintance = await username_acquaintance(message.chat.id, message.from_user.first_name, 'first_name')
    start_message = await message.answer(f"Привет, {escape(acquaintance)} 👋\n"
                                         f"<a href='{SITE}'>Обзор всех функций</a> 👇",
                                         parse_mode=html, reply_markup=markup, link_preview_options=preview_options())
    params = message.text.replace("/start ", "").split()
    if message.text.startswith('/start r'):
        friend_id = unzip_int_data(message.text.replace('/start r', ''))
        if message.chat.id == friend_id:
            await message.answer("Вы не можете зарегистрироваться по своей реферальной ссылке!")
        elif not await db.fetch_one(f"SELECT true FROM accounts WHERE account_id={friend_id}", one_data=True):
            await message.answer("Реферальная ссылка не найдена!")
        elif await db.fetch_one(f"SELECT true FROM accounts WHERE account_id={message.chat.id}", one_data=True):
            await message.answer("Вы уже зарегистрированы и не можете использовать чьи-то реферальные ссылки")
        else:
            try:
                await db.execute(f"INSERT INTO referals VALUES ({friend_id}, {message.chat.id})")
            except UniqueViolationError:
                await db.execute(f"UPDATE referals SET account_id={friend_id} WHERE referal_id={message.chat.id}")
            await bot.send_message(friend_id, "По вашей реферальной ссылке зарегистрировался новый пользователь. Если он "
                                              "подключит бота, то вы получите месяц подписки в подарок")
            await bot.send_message(OWNER, f"Регистрация по реферальной ссылке #r{friend_id}")
    elif "menu" in params:
        await start_message.edit_text(**await menu(message.chat.id))
    await service_message.delete()


@dp.message(Command('menu'))
@security()
async def _menu(message: Message):
    if await new_message(message): return
    await message.answer(**await menu(message.chat.id))


@dp.callback_query(F.data == "menu")
@security()
async def _menu_button(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await menu(callback_query.message.chat.id))


async def menu(account_id: int) -> dict[str, Any]:
    status = await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True)  # Вкл/выкл Maksogram
    if status is None:
        markup = IMarkup(inline_keyboard=[[IButton(text="🟢 Включить Maksogram", callback_data="registration")],
                                          [IButton(text="ℹ️ Узнать все возможности", url=SITE)]])
    elif status is False:
        markup = IMarkup(inline_keyboard=[[IButton(text="🟢 Включить Maksogram", callback_data="on")],
                                          [IButton(text="⚙️ Настройки", callback_data="settings")],
                                          [IButton(text="ℹ️ Памятка по функциям", url=SITE)]])
    else:
        markup = IMarkup(inline_keyboard=[[IButton(text="🔴 Выключить Maksogram", callback_data="off")],
                                          [IButton(text="📸 Новая аватарка", callback_data="avatars"),
                                           IButton(text="🤖 Автоответчик", callback_data="answering_machine")],
                                          [IButton(text="🌐 Друг в сети", callback_data="status_users"),
                                           IButton(text="💬 Maksogram в чате", callback_data="modules")],
                                          [IButton(text="⚙️ Настройки", callback_data="settings")],
                                          [IButton(text="ℹ️ Памятка по функциям", url=SITE)]])
    return {"text": "⚙️ Maksogram — меню ⚙️", "reply_markup": markup}


@dp.message(Command('settings'))
@security()
async def _settings(message: Message):
    if await new_message(message): return
    await message.answer(**await settings(message.chat.id))


@dp.callback_query(F.data == "settings")
@security()
async def _settings_button(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await settings(callback_query.from_user.id))


async def settings(account_id: int) -> dict[str, Any]:
    account_settings = await db.fetch_one(f"SELECT time_zone, city, gender FROM settings WHERE account_id={account_id}")
    time_zone = f"+{account_settings['time_zone']}" if account_settings['time_zone'] >= 0 else str(account_settings['time_zone'])
    city = account_settings['city']
    gender = {None: "не указан", True: "мужчина", False: "женщина"}[account_settings['gender']]  # Заранее извиняюсь :)
    reply_markup = IMarkup(inline_keyboard=[[IButton(text="👁 Профиль", callback_data="profile"),
                                             IButton(text="🕰 Часовой пояс", callback_data="time_zone")],
                                            [IButton(text="🌏 Город", callback_data="city"),
                                             IButton(text="🚹 🚺 Пол", callback_data="gender")],
                                            [IButton(text="◀️  Назад", callback_data="menu")]])
    return {"text": f"⚙️ Общие настройки Maksogram\nЧасовой пояс: {time_zone}:00\nГород: {city}\nПол: {gender}",
            "reply_markup": reply_markup}


@dp.callback_query(F.data == "gender")
@security()
async def _gender(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await gender_menu(callback_query.from_user.id))


async def gender_menu(account_id: int) -> dict[str, Any]:
    account_settings = await db.fetch_one(f"SELECT gender FROM settings WHERE account_id={account_id}")
    gender = {None: "не указан", True: "мужчина", False: "женщина"}[account_settings['gender']]  # Заранее извиняюсь :)
    reply_markup = IMarkup(inline_keyboard=[[IButton(text="🚹 Мужчина", callback_data="gender_edit__man")],
                                            [IButton(text="🚺 Женщина", callback_data="gender_edit_woman")],
                                            [IButton(text="◀️  Назад", callback_data="settings")]])
    return {"text": f"Вы можете выбрать пол. Он нужен для красивых поздравлений\nПол: {gender}", "reply_markup": reply_markup}


@dp.callback_query(F.data.startswith("gender_edit"))
@security()
async def _gender_edit(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    gender = "true" if callback_query.data.split("_")[-1] == "man" else "false"
    account_id = callback_query.from_user.id
    await db.execute(f"UPDATE settings SET gender={gender} WHERE account_id={account_id}")
    await callback_query.message.edit_text(**await settings(account_id))


@dp.callback_query(F.data == "profile")
@security()
async def _profile_button(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await profile_menu(callback_query.from_user.id))


async def profile_menu(account_id: int) -> dict[str, Any]:
    reply_markup = IMarkup(inline_keyboard=[[IButton(text="◀️  Назад", callback_data="settings")]])
    account = await db.fetch_one(f"SELECT name, registration_date FROM accounts WHERE account_id={account_id}")
    subscription = await db.fetch_one(f"SELECT \"user\", fee, next_payment FROM payment WHERE account_id={account_id}")
    account['registration_date'] = account['registration_date'].strftime("%Y-%m-%d %H:%M")
    subscription['next_payment'] = subscription['next_payment'].strftime("%Y-%m-%d 20:00")  # Время перезапуска
    my_referal = await db.fetch_one(f"SELECT account_id FROM referals WHERE referal_id={account_id}", one_data=True)
    if my_referal:
        my_referal = f'<a href="tg://user?id={my_referal}">{my_referal}</a>'
    else:
        my_referal = '<span class="tg-spoiler">сам пришел 🤓</span>'
    if subscription['user'] == 'admin':
        subscription['next_payment'] = "конца жизни 😎"
        subscription['fee'] = "бесплатно"
    return {"text": f"👁 <b>Профиль</b>\nID: {account_id}\nИмя: {account['name']}\n"
                    f"Регистрация: {account['registration_date']}\nМеня пригласил: {my_referal}\n"
                    f"Подписка до {subscription['next_payment']}\nСтоимость: {subscription['fee']}",
            "parse_mode": html, "reply_markup": reply_markup}


@dp.callback_query(F.data == "city")
@security('state')
async def _city_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.city)
    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте название вашего города", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.city)
@security('state')
async def _city(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    account_id = message.chat.id
    if message.text != "Отмена":
        if not await check_city(message.text.lower()):
            markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
            await state.update_data(message_id=(await message.answer("Город не найден...", reply_markup=markup)).message_id)
        else:
            await state.clear()
            await db.execute(f"UPDATE settings SET city=$1 WHERE account_id={account_id}", message.text)
            await message.answer(**await settings(account_id))
    else:
        await state.clear()
        await message.answer(**await settings(account_id))
    await bot.delete_messages(account_id, [message_id, message.message_id])


@dp.callback_query(F.data == "time_zone")
@security('state')
async def _time_zone_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.time_zone)
    button = KButton(text="Выбрать часовой пояс", web_app=WebAppInfo(url=f"{Data.web_app}/time_zone"))
    back_button = KButton(text="Отмена")
    message_id = (await callback_query.message.answer(
        "Нажмите на кнопку, чтобы выбрать часовой пояс", reply_markup=KMarkup(keyboard=[[button], [back_button]],
                                                                              resize_keyboard=True))).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.time_zone)
@security('state')
async def _time_zone(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    account_id = message.chat.id
    if message.content_type == "web_app_data":
        time_zone = int(message.web_app_data.data)
        await db.execute(f"UPDATE settings SET time_zone={time_zone} WHERE account_id={account_id}")
    await message.answer(**await settings(account_id))
    await bot.delete_messages(message.chat.id, [message_id, message.message_id])


def menu_initial():
    pass  # Чтобы PyCharm не ругался
