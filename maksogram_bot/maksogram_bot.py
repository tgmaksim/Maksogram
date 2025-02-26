import re
import time
import asyncio
import aiohttp

from html import escape
from datetime import timedelta
from typing import Literal, Any
from sys_keys import TOKEN, release
from modules.weather import check_city
from saving_messages import admin_program, program
from asyncpg.exceptions import UniqueViolationError
from create_chats import create_chats, CreateChatsError
from core import (
    db,
    html,
    SITE,
    OWNER,
    morning,
    channel,
    support,
    time_now,
    security,
    Variables,
    omsk_time,
    account_on,
    account_off,
    json_encode,
    MaksogramBot,
    zip_int_data,
    count_avatars,
    resources_path,
    unzip_int_data,
    preview_options,
    telegram_clients,
    UserIsNotAuthorized,
    new_telegram_client,
    get_enabled_auto_answer,
)

from telethon import errors
from telethon import TelegramClient
from aiogram import Bot, Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from aiogram.filters.command import Command, CommandStart
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import (
    Message,
    WebAppInfo,
    FSInputFile,
    CallbackQuery,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButtonRequestUsers,
)

bot = Bot(TOKEN)
dp = Dispatcher()


# Класс с глобальными переменными для удобного пользования
class Data:
    web_app = "https://tgmaksim.ru/maksogram"


# Класс нужен для определения состояния пользователя в данном боте,
# например: пользователь должен отправить отзыв в следующем сообщении
class UserState(StatesGroup):
    class Admin(StatesGroup):
        mailing = State('mailing')
        confirm_mailing = State('confirm_mailing')

    time_zone = State('time_zone')
    city = State('city')
    feedback = State('feedback')
    send_phone_number = State('send_phone_number')
    send_code = State('send_code')
    send_password = State('send_password')
    relogin = State('relogin')
    relogin_with_password = State('relogin_with_password')
    status_user = State('status_user')
    answering_machine = State('answering_machine')
    answering_machine_edit_text = State('answering_machine_edit_text')
    answering_machine_edit_timetable = State('answering_machine_edit_timetable')
    answering_machine_edit_time = State('answering_machine_edit_time')
    avatar = State('avatar')


# Метод для отправки сообщения от имени бота
@dp.message(F.reply_to_message.__and__(F.chat.id == OWNER).__and__(F.reply_to_message.text.startswith("ID")))
@security()
async def _sender(message: Message):
    user_id = int(message.reply_to_message.text.split('\n', 1)[0].replace("ID: ", ""))
    try:
        copy_message = await bot.copy_message(user_id, OWNER, message.message_id)
    except TelegramForbiddenError:
        await message.answer("Пользователь заблокировал бота...")
    except Exception as e:
        await message.answer(f"Сообщение не отправлено из-за ошибки {e.__class__.__name__}: {e}")
    else:
        await message.answer("Сообщение отправлено")
        await bot.forward_message(OWNER, user_id, copy_message.message_id)


@dp.message(Command('admin'))
@security()
async def _admin(message: Message):
    if await developer_command(message): return
    await message.answer("Команды разработчика:\n"
                         "/reload - перезапустить программу\n"
                         "/stop - остановить программу\n"
                         "/mailing - рассылка")


@dp.message(Command('reload'))
@security()
async def _reload(message: Message):
    if await developer_command(message): return
    if release:
        await message.answer("<b>Перезапуск бота</b>", parse_mode=html)
        print("Перезапуск бота")
        async with aiohttp.ClientSession() as session:
            async with session.post("https://panel.netangels.ru/api/gateway/token/",
                                    data={"api_key": Variables.ApiKey}) as response:
                token = (await response.json())['token']
                await session.post(f"https://api-ms.netangels.ru/api/v1/hosting/background-processes/{Variables.ProcessId}/restart",
                                   headers={"Authorization": f"Bearer {token}"})
    else:
        await message.answer("В тестовом режиме перезапуск бота программно не предусмотрен!")
        print("В тестовом режиме перезапуск бота программно не предусмотрен!")


@dp.message(Command('stop'))
@security()
async def _stop(message: Message):
    if await developer_command(message): return
    await message.answer("<b>Остановка бота и программы</b>", parse_mode=html)
    print("Остановка бота и программы")
    if release:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://panel.netangels.ru/api/gateway/token/",
                                    data={"api_key": Variables.ApiKey}) as response:
                token = (await response.json())['token']
                await session.post(f"https://api-ms.netangels.ru/api/v1/hosting/background-processes/{Variables.ProcessId}/stop",
                                   headers={"Authorization": f"Bearer {token}"})
    else:
        await dp.stop_polling()
        asyncio.get_event_loop().stop()


@dp.message(Command('mailing'))
@security('state')
async def _start_mailing(message: Message, state: FSMContext):
    if await developer_command(message): return
    await state.set_state(UserState.Admin.mailing)
    await message.answer("Отправь сообщение, которое я разошлю все активным пользователям бота")


@dp.message(UserState.Admin.mailing)
@security('state')
async def _mailing(message: Message, state: FSMContext):
    if await developer_command(message): return
    await state.update_data(message_id=message.message_id)
    markup = IMarkup(inline_keyboard=[[IButton(text="Переслать 💬", callback_data="mailing_forward"),
                                       IButton(text="Отправить 🔐", callback_data="mailing_send")],
                                      [IButton(text="❌ Отмена ❌", callback_data="stop_mailing")]])
    await message.answer("Выбери способ рассылки сообщения 👇", reply_markup=markup)


@dp.callback_query(F.data.in_(["mailing_forward", "mailing_send", "stop_mailing"]))
@security('state')
async def _confirm_mailing(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    match callback_query.data:
        case "mailing_forward":
            await callback_query.message.edit_text(f"{callback_query.message.text}\nПересылка")
            message_id = (await state.get_data())['message_id']
            await state.clear()
            fun = lambda user_id: bot.forward_message(user_id, callback_query.from_user.id, message_id)
        case "mailing_send":
            await callback_query.message.edit_text(f"{callback_query.message.text}\nОтправка")
            message_id = (await state.get_data())['message_id']
            await state.clear()
            fun = lambda user_id: bot.copy_message(user_id, callback_query.from_user.id, message_id)
        case _:
            await state.clear()
            return await callback_query.message.edit_text("Операция отменена!")
    # Получение количества активным зарегистрированных и активных пользователей
    result = [await db.fetch_one("SELECT COUNT(*) FROM accounts", one_data=True), 0, 0, 0]
    for account in await db.fetch_all("SELECT account_id, is_started FROM settings"):
        if account['is_started']:
            result[1] += 1  # Количество активных пользователей
            try:
                await fun(account['account_id'])
            except (TelegramBadRequest, TelegramForbiddenError):
                result[2] += 1  # Количество ошибок
            else:
                result[3] += 1  # Количество доставленных сообщений
            await asyncio.sleep(1)
    await callback_query.message.answer(f"Рассылка завершена!\nВсего пользователей: {result[0]}\n"
                                        f"Активные пользователи: {result[1]}\nДоставлено сообщений: {result[3]}\n"
                                        f"Произошло ошибок: {result[2]}")


@dp.message(Command('feedback'))
@security('state')
async def _start_feedback(message: Message, state: FSMContext):
    if await new_message(message): return
    await state.set_state(UserState.feedback)
    markup = IMarkup(inline_keyboard=[[IButton(text="❌", callback_data="stop_feedback")]])
    await message.answer("Отправьте текст вопроса или предложения. Любое следующее сообщение будет считаться отзывом",
                         reply_markup=markup)


@dp.message(UserState.feedback)
@security('state')
async def _feedback(message: Message, state: FSMContext):
    if await new_message(message, forward=False): return
    await state.clear()
    acquaintance = await username_acquaintance(message)
    if acquaintance:
        await bot.send_photo(OWNER, photo=FSInputFile(resources_path("feedback.png")),
                             caption=f"{acquaintance} написал(а) отзыв 👇")
    else:
        await bot.send_photo(OWNER,
                             photo=FSInputFile(resources_path("feedback.png")),
                             caption=f"ID: {message.chat.id}\n" +
                                     (f"USERNAME: @{message.from_user.username}\n" if message.from_user.username else "") +
                                     f"Имя: {message.from_user.first_name}\n" +
                                     (f"Фамилия: {message.from_user.last_name}\n" if message.from_user.last_name else "") +
                                     f"Время: {omsk_time(message.date)}")
    await message.forward(OWNER)
    await message.answer("Большое спасибо за отзыв!❤️❤️❤️")


@dp.callback_query(F.data == "stop_feedback")
@security('state')
async def _stop_feedback(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.clear()
    await callback_query.message.edit_text("Отправка отзыва отменена")


@dp.callback_query(F.data == "send_payment")
@security()
async def _send_payment(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    name = await db.fetch_one(f"SELECT name FROM accounts WHERE account_id={account_id}", one_data=True)  # Имя пользователя
    markup = IMarkup(inline_keyboard=[[
        IButton(text="Подтвердить! ✅", callback_data=f"confirm_sending_payment{account_id}_{callback_query.message.message_id}")]])
    await bot.send_message(OWNER, f"Пользователь {name} отправил оплату, проверь это! Если так, то подтверди, "
                                  "чтобы я продлил подписку на месяц", reply_markup=markup)
    await callback_query.answer("Запрос отправлен. Ожидайте!", True)


async def payment_menu(account_id: int) -> dict[str, Any]:
    fee = await db.fetch_one(f"SELECT fee FROM payment WHERE account_id={account_id}", one_data=True)  # Цена подписки
    markup = IMarkup(inline_keyboard=[[IButton(text="TON", web_app=WebAppInfo(url=f"{Data.web_app}/payment/ton")),
                                       IButton(text="BTC", web_app=WebAppInfo(url=f"{Data.web_app}/payment/btc"))],
                                      [IButton(text="Перевод по номеру", web_app=WebAppInfo(url=f"{Data.web_app}/payment/fps"))],
                                      [IButton(text="Я отправил(а)  ✅", callback_data="send_payment")]])
    return {"text": f"Способы оплаты (любой):\nСбер: ({fee} руб)\nBTC: (0.00002 btc)\nTON: (0.4 ton)",
            "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data.startswith("confirm_sending_payment"))
@security()
async def _confirm_sending_payment(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    if callback_query.from_user.id != OWNER:
        return await callback_query.answer("Ошибка!", True)
    account_id, message_id = map(int, callback_query.data.replace("confirm_sending_payment", "").split("_"))
    await db.execute(f"""UPDATE payment SET next_payment=((CASE WHEN 
                     next_payment > CURRENT_TIMESTAMP THEN 
                     next_payment ELSE CURRENT_TIMESTAMP END) + INTERVAL '30 days'), 
                     is_paid=true WHERE account_id={account_id}""")  # перемещение даты оплаты на 30 дней вперед
    await bot.edit_message_reply_markup(chat_id=account_id, message_id=message_id)
    await bot.send_message(account_id, f"Ваша оплата подтверждена! Следующий платеж через месяц", reply_to_message_id=message_id)
    await callback_query.message.edit_text(callback_query.message.text + '\n\nУспешно!')


@dp.message(Command('version'))
@security()
async def _version(message: Message):
    if await new_message(message): return
    await message.answer(f"Версия: {Variables.version_string}\n<a href='{SITE}/{Variables.version}'>Обновление</a> 👇",
                         parse_mode=html, link_preview_options=preview_options(Variables.version))


@dp.message(Command('friends'))
@security()
async def _friends(message: Message):
    if await new_message(message): return
    if not await db.fetch_one(f"SELECT true FROM accounts WHERE account_id={message.chat.id}", one_data=True):
        return await message.answer("Вы не подключили бота, у вас еще нет реферальной ссылки!")
    url = f"tg://resolve?domain={MaksogramBot.username}&start={referal_link(message.chat.id)}"
    await message.answer(
        "<b>Реферальная программа\n</b>"
        "Приглашайте своих знакомых и получайте в подарок месяц подписки за каждого друга. "
        "Пригласить друга можно, отправив сообщение 👇", parse_mode=html)
    markup = IMarkup(inline_keyboard=[[IButton(text="Попробовать бесплатно", url=url)]])
    await message.answer_photo(
        FSInputFile(resources_path("logo.jpg")),
        f"Привет! Я хочу тебе посоветовать отличного <a href='{url}'>бота</a>. "
        "Он сохранит все твои сообщения и подскажет, когда кто-то их удалит, изменит, прочитает или поставит реакцию. "
        "Также в нем есть множество других полезных функций", parse_mode=html, reply_markup=markup, disable_web_page_preview=True)


@dp.message(CommandStart())
@security('state')
async def _start(message: Message, state: FSMContext):
    if await new_message(message): return
    await state.clear()
    service_message = await message.answer("...", reply_markup=ReplyKeyboardRemove())
    if await db.fetch_one(f"SELECT true FROM accounts WHERE account_id={message.chat.id}", one_data=True):  # Зарегистрирован(а)
        markup = IMarkup(inline_keyboard=[[IButton(text="⚙️ Меню и настройки", callback_data="menu")]])
    else:
        markup = IMarkup(inline_keyboard=[[IButton(text="🚀 Запустить бота", callback_data="menu")]])
    await message.answer(f"Привет, {escape(await username_acquaintance(message, 'first_name'))} 👋\n"
                         f"<a href='{SITE}'>Обзор всех функций</a> 👇",
                         parse_mode=html, reply_markup=markup, link_preview_options=preview_options())
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
    await service_message.delete()


@dp.message(Command('help'))
@security()
async def _help(message: Message):
    if await new_message(message): return
    await help(message)


@dp.callback_query(F.data == "help")
@security()
async def _help_button(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_reply_markup()
    await help(callback_query.message)


async def help(message: Message):
    await message.answer("/menu - меню функций\n"
                         "/settings - настройки\n"
                         "/feedback - оставить отзыв или предложение\n"
                         "/friends - реферальная программа\n", parse_mode=html)


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


@dp.message(Command('menu_chat'))
@security()
async def _menu_chat(message: Message):
    if await new_message(message): return
    await message.answer(**modules_menu())


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
    if subscription['user'] == 'admin':
        subscription['next_payment'] = "конца жизни 😎"
        subscription['fee'] = "бесплатно"
    return {"text": f"👁 <b>Профиль</b>\nID: {account_id}\nИмя: {account['name']}\nРегистрация: {account['registration_date']}\n"
                    f"Подписка до {subscription['next_payment']}\nСтоимость: {subscription['fee']}",
            "parse_mode": html, "reply_markup": reply_markup}


@dp.callback_query(F.data == "city")
@security('state')
async def _city_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.city)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
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
            markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
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
    button = KeyboardButton(text="Выбрать часовой пояс", web_app=WebAppInfo(url=f"{Data.web_app}/time_zone"))
    back_button = KeyboardButton(text="Отмена")
    message_id = (await callback_query.message.answer("Нажмите на кнопку, чтобы выбрать часовой пояс",
                                                      reply_markup=ReplyKeyboardMarkup(keyboard=[[button], [back_button]],
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


@dp.callback_query(F.data == "modules")
@security()
async def _modules(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**modules_menu())


def modules_menu() -> dict[str, Any]:
    markup = IMarkup(inline_keyboard=[[IButton(text="🔢 Калькулятор", callback_data="calculator"),
                                       IButton(text="🌤 Погода", callback_data="weather")],
                                      [IButton(text="🔗 Генератор QR-кодов", callback_data="qrcode")],
                                      [IButton(text="🗣 Расшифровка ГС", callback_data="audio_transcription")],
                                      [IButton(text="◀️  Назад", callback_data="menu")]])
    return {"text": "💬 <b>Maksogram в чате</b>\nФункции, которые работают прямо из любого чата, не нужно вызывать меня",
            "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data == "calculator")
@security()
async def _calculator(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await calculator_menu(callback_query.message.chat.id))


async def calculator_menu(account_id: int) -> dict[str, Any]:
    if await db.fetch_one(f"SELECT calculator FROM modules WHERE account_id={account_id}", one_data=True):  # Вкл/выкл калькулятор
        status_button = IButton(text="🔴 Выключить калькулятор", callback_data="calculator_off")
    else:
        status_button = IButton(text="🟢 Включить калькулятор", callback_data="calculator_on")
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="Как работает калькулятор?", url=f"{SITE}#калькулятор")],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "🔢 <b>Калькулятор в чате</b>\nРешает примеры разных уровней сложности от обычного умножения до "
                    "длинных примеров. Для срабатывания укажите в конце \"=\"\n<blockquote>10+5*15=</blockquote>",
            "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data.in_(["calculator_on", "calculator_off"]))
@security()
async def _calculator_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET calculator=true WHERE account_id={callback_query.from_user.id}")
        case "off":
            await db.execute(f"UPDATE modules SET calculator=false WHERE account_id={callback_query.from_user.id}")
    await callback_query.message.edit_text(**await calculator_menu(callback_query.message.chat.id))


@dp.callback_query(F.data == "qrcode")
@security()
async def _qrcode(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await qrcode_menu(callback_query.message.chat.id))


async def qrcode_menu(account_id: int) -> dict[str, Any]:
    if await db.fetch_one(f"SELECT qrcode FROM modules WHERE account_id={account_id}", one_data=True):  # Вкл/выкл генератор QR
        status_button = IButton(text="🔴 Выключить генератор", callback_data="qrcode_off")
    else:
        status_button = IButton(text="🟢 Включить генератор", callback_data="qrcode_on")
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="Как работает генератор?", url=f"{SITE}#генератор-qr")],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "🔗 <b>Генератор QR-кодов</b>\nГенерирует QR-код с нужной ссылкой. "
                    f"Тригеры: создай, создать, qr, сгенерировать\n<blockquote>Создай t.me/{channel[1:]}</blockquote>",
            "reply_markup": markup, "parse_mode": html, "disable_web_page_preview": True}


@dp.callback_query(F.data.in_(["qrcode_on", "qrcode_off"]))
@security()
async def _qrcode_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET qrcode=true WHERE account_id={callback_query.from_user.id}")  # Включение QR
        case "off":
            await db.execute(f"UPDATE modules SET qrcode=false WHERE account_id={callback_query.from_user.id}")  # Выключение QR
    await callback_query.message.edit_text(**await qrcode_menu(callback_query.message.chat.id))


@dp.callback_query(F.data == "audio_transcription")
@security()
async def _audio_transcription(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await audio_transcription_menu(callback_query.message.chat.id))


async def audio_transcription_menu(account_id: int) -> dict[str, Any]:
    if await db.fetch_one(f"SELECT audio_transcription FROM modules WHERE account_id={account_id}", one_data=True):  # Вкл/выкл расшифровка гс
        status_button = IButton(text="🔴 Выключить расшифровку", callback_data="audio_transcription_off")
    else:
        status_button = IButton(text="🟢 Включить расшифровку", callback_data="audio_transcription_on")
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="Как пользоваться расшифровкой гс?", url=f"{SITE}#расшифровка-гс")],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "🗣 <b>Расшифровка ГС</b>\nНе хотите слушать голосовое? Расшифруйте его в текст. Тригеры: расшифруй, в текст",
            "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data.in_(["audio_transcription_on", "audio_transcription_off"]))
@security()
async def _audio_transcription_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET audio_transcription=true WHERE account_id={callback_query.from_user.id}")  # Включение расшифровки
        case "off":
            await db.execute(f"UPDATE modules SET audio_transcription=false WHERE account_id={callback_query.from_user.id}")  # Выключение расшифровки
    await callback_query.message.edit_text(**await audio_transcription_menu(callback_query.message.chat.id))


@dp.callback_query(F.data == "weather")
@security()
async def _weather(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await weather_menu(callback_query.from_user.id))


async def weather_menu(account_id: int) -> dict[str, Any]:
    if await db.fetch_one(f"SELECT weather FROM modules WHERE account_id={account_id}", one_data=True):  # Вкл/выкл погода
        status_button_weather = IButton(text="🔴 Выключить погоду", callback_data="weather_off")
    else:
        status_button_weather = IButton(text="🟢 Включить погоду", callback_data="weather_on")
    if await db.fetch_one(f"SELECT morning_weather FROM modules WHERE account_id={account_id}", one_data=True):  # Вкл/выкл погода по утрам
        status_button_morning_weather = IButton(text="🔴 Выключить утреннюю погоду", callback_data="morning_weather_off")
    else:
        status_button_morning_weather = IButton(text="🟢 Включить утреннюю погоду", callback_data="morning_weather_on")
    markup = IMarkup(inline_keyboard=[[status_button_weather],
                                      [status_button_morning_weather],
                                      [IButton(text="Как пользоваться погодой?", url=f"{SITE}#погода")],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "🌤 <b>Погода</b>\nЛегко получайте погоду за окном, не выходя из Telegram. Тригеры: какая погода\n"
                    f"Погода по утрам присылается, когда вы первый раз зашли в Telegram с {morning[0]}:00 до {morning[1]}:00",
            "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data.in_(["weather_on", "weather_off"]))
@security()
async def _weather_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET weather=true WHERE account_id={callback_query.from_user.id}")  # Включение погоды
        case "off":
            await db.execute(f"UPDATE modules SET weather=false WHERE account_id={callback_query.from_user.id}")  # Выключение погоды
    await callback_query.message.edit_text(**await weather_menu(callback_query.message.chat.id))


@dp.callback_query(F.data.in_(["morning_weather_on", "morning_weather_off"]))
@security()
async def _morning_weather_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    account_id = callback_query.from_user.id
    match command:
        case "on":
            telegram_clients[account_id].list_event_handlers()[4][1].chats.add(account_id)
            await db.execute(f"UPDATE modules SET morning_weather=true WHERE account_id={account_id}")  # Включение погоды по утрам
        case "off":
            telegram_clients[account_id].list_event_handlers()[4][1].chats.remove(account_id)
            await db.execute(f"UPDATE modules SET morning_weather=false WHERE account_id={account_id}")  # Выключение погоды по утрам
    await callback_query.message.edit_text(**await weather_menu(callback_query.message.chat.id))


@dp.callback_query(F.data == "avatars")
@security()
async def _avatars(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await avatars_menu(callback_query.message.chat.id))


async def avatars_menu(account_id: int) -> dict[str, Any]:
    buttons = []
    users = await db.fetch_all(f"SELECT user_id, name FROM avatars WHERE account_id={account_id}")  # Список новых аватарок
    for user in users:
        buttons.append([IButton(text=f"📸 {user['name']}", callback_data=f"avatar_menu{user['user_id']}")])
    buttons.append([IButton(text="➕ Добавить пользователя", callback_data="new_avatar")])
    buttons.append([IButton(text="◀️  Назад", callback_data="menu")])
    return {"text": "📸 <b>Новая аватарка</b>\nКогда кто-то из выбранных пользователей изменит или добавит аватарку, я сообщу вам",
            "parse_mode": html, "reply_markup": IMarkup(inline_keyboard=buttons)}


@dp.callback_query(F.data.startswith("new_avatar"))
@security('state')
async def _new_avatar_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    if await db.fetch_one(f"SELECT COUNT(*) FROM avatars WHERE account_id={callback_query.from_user.id}", one_data=True) >= 2:
        # Количество новых аватарок уже достигло максимума
        return await callback_query.answer("У вас максимальное количество \"новых аватарок\"")
    await state.set_state(UserState.avatar)
    request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Выбрать", request_users=request_users)],
                                           [KeyboardButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте пользователя для отслеживания", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.avatar)
@security('state')
async def _new_avatar(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    if message.content_type == "users_shared":
        user_id = message.users_shared.user_ids[0]
        account_id = message.chat.id
        if user_id == account_id:  # Себя нельзя
            await message.answer(**await avatars_menu(account_id))
        else:
            user = await telegram_clients[account_id].get_entity(user_id)
            name = user.first_name + (f" {user.last_name}" if user.last_name else "")
            count = await count_avatars(account_id, user_id)
            await db.execute(f"INSERT INTO avatars VALUES ({account_id}, {user_id}, $1, {count})", name)  # Добавление новой аватарки
            await message.answer(**await avatar_menu(message.chat.id, user_id))
    else:
        await message.answer(**await avatars_menu(message.chat.id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


async def avatar_menu(account_id: int, user_id: int) -> dict[str, Any]:
    name = await db.fetch_one(f"SELECT name FROM avatars WHERE account_id={account_id} AND user_id={user_id}", one_data=True)  # Имя новой аватарки
    if name is None:
        return await avatars_menu(account_id)
    markup = IMarkup(inline_keyboard=[
        [IButton(text="🔴 Выключить", callback_data=f"avatar_del{user_id}")],
        [IButton(text="◀️  Назад", callback_data="avatars")]])
    return {"text": f"📸 <b>Новая аватарка</b>\nКогда <b>{name}</b> изменит или добавит аватарку, я сообщу вам\n",
            "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data.startswith("avatar_del"))
@security()
async def _avatar_del(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    user_id = int(callback_query.data.replace("avatar_del", ""))
    await db.execute(f"DELETE FROM avatars WHERE account_id={callback_query.from_user.id} AND user_id={user_id}")  # Удаление новой аватарки
    await callback_query.message.edit_text(**await avatars_menu(callback_query.message.chat.id))


@dp.callback_query(F.data.startswith("avatar_menu"))
@security()
async def _avatar_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    user_id = int(callback_query.data.replace("avatar_menu", ""))
    await callback_query.message.edit_text(**await avatar_menu(callback_query.message.chat.id, user_id))


@dp.callback_query(F.data == "status_users")
@security()
async def _status_users(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await status_users_menu(callback_query.message.chat.id))


async def status_users_menu(account_id: int) -> dict[str, Any]:
    buttons = []
    users = await db.fetch_all(f"SELECT user_id, name FROM status_users WHERE account_id={account_id}")  # Список друзей в сети
    for user in users:
        buttons.append([IButton(text=f"🌐 {user['name']}", callback_data=f"status_user_menu{user['user_id']}")])
    buttons.append([IButton(text="➕ Добавить нового пользователя", callback_data="new_status_user")])
    buttons.append([IButton(text="◀️  Назад", callback_data="menu")])
    return {"text": "🌐 <b>Друг в сети</b>\nЯ уведомлю вас, если пользователь будет онлайн/офлайн. Не работает, если собеседник "
                    "скрыл время последнего захода...", "reply_markup": IMarkup(inline_keyboard=buttons), "parse_mode": html}


@dp.callback_query(F.data.startswith("status_user_menu"))
@security()
async def _status_user_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    user_id = int(callback_query.data.replace("status_user_menu", ""))
    await callback_query.message.edit_text(**await status_user_menu(callback_query.message.chat.id, user_id))


async def status_user_menu(account_id: int, user_id: int) -> dict[str, Any]:
    def status(parameter: bool):
        return "🟢" if parameter else "🔴"

    def command(parameter: bool):
        return "off" if parameter else "on"

    user = await db.fetch_one(f"SELECT name, online, offline, reading FROM status_users WHERE account_id={account_id} AND "
                              f"user_id={user_id}")  # Данные о друге в сети
    if user is None:
        return await status_users_menu(account_id)
    markup = IMarkup(inline_keyboard=[
        [IButton(text=f"{status(user['online'])} Появление в сети",
                 callback_data=f"status_user_online_{command(user['online'])}_{user_id}")],
        [IButton(text=f"{status(user['offline'])} Выход из сети",
                 callback_data=f"status_user_offline_{command(user['offline'])}_{user_id}")],
        [IButton(text=f"{status(user['reading'])} Чтение моего сообщения",
                 callback_data=f"status_user_reading_{command(user['reading'])}_{user_id}")],
        [IButton(text="🚫 Удалить пользователя", callback_data=f"status_user_del{user_id}")],
        [IButton(text="◀️  Назад", callback_data="status_users")]])
    return {"text": f"🌐 <b>Друг в сети</b>\nКогда <b>{user['name']}</b> выйдет/зайдет в сеть или прочитает сообщение, я сообщу",
            "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data.startswith("status_user_online_on").__or__(F.data.startswith("status_user_online_off")).__or__(
                   F.data.startswith("status_user_offline_on")).__or__(F.data.startswith("status_user_offline_off")).__or__(
                   F.data.startswith("status_user_reading_on")).__or__(F.data.startswith("status_user_reading_off")))
@security()
async def _status_user_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    function_status_user, command, user_id = callback_query.data.replace("status_user_", "").split("_")
    user = await db.fetch_one(f"SELECT true FROM status_users WHERE account_id={account_id} AND user_id={user_id}", one_data=True)
    if user is None:  # Пользователь удален из списка друзей в сети
        return await callback_query.message.edit_text(**await status_users_menu(account_id))
    await db.execute(f"UPDATE status_users SET {function_status_user}={'true' if command == 'on' else 'false'} WHERE "
                     f"account_id={account_id} AND user_id={user_id}")  # Вкл/выкл нужной функции друга в сети
    await callback_query.message.edit_text(**await status_user_menu(account_id, int(user_id)))


@dp.callback_query(F.data == "new_status_user")
@security('state')
async def _new_status_user_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    if await db.fetch_one(f"SELECT COUNT(*) FROM status_users WHERE account_id={callback_query.from_user.id}", one_data=True) >= 2:
        # Количество друзей в сети уже достигло максимума
        return await callback_query.answer("У вас максимальное количество!", True)
    await state.set_state(UserState.status_user)
    request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Выбрать", request_users=request_users)],
                                           [KeyboardButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте пользователя для отслеживания", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.status_user)
@security('state')
async def _new_status_user(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    if message.content_type == "users_shared":
        user_id = message.users_shared.user_ids[0]
        account_id = message.chat.id
        if user_id == account_id:  # Себя нельзя
            await message.answer(**await status_users_menu(account_id))
        else:
            user = await telegram_clients[message.chat.id].get_entity(user_id)
            name = user.first_name + (f" {user.last_name}" if user.last_name else "")
            name = (name[:30] + "...") if len(name) > 30 else name
            telegram_clients[account_id].list_event_handlers()[4][1].chats.add(user_id)
            await db.execute(f"INSERT INTO status_users VALUES ({account_id}, {user_id}, $1, false, false, false)", name)  # Добавление друга в сети
            await message.answer(**await status_user_menu(message.chat.id, user_id))
    else:
        await message.answer(**await status_users_menu(message.chat.id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data.startswith("status_user_del"))
@security()
async def _status_user_del(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    user_id = int(callback_query.data.replace("status_user_del", ""))
    account_id = callback_query.from_user.id
    telegram_clients[account_id].list_event_handlers()[4][1].chats.remove(user_id)
    await db.execute(f"DELETE FROM status_users WHERE account_id={account_id} AND user_id={user_id}")  # Удаление друга в сети
    await callback_query.message.edit_text(**await status_users_menu(callback_query.message.chat.id))


@dp.callback_query(F.data == "answering_machine")
@security()
async def _answering_machine(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await answering_machine_menu(callback_query.message.chat.id))


async def answering_machine_menu(account_id: int) -> dict[str, Any]:
    buttons = []
    answers = await db.fetch_all(f"SELECT answer_id, status, type, start_time, end_time, text FROM answering_machine "
                                 f"WHERE account_id={account_id}")  # Автоответы
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
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Напишите <b>текст</b>, который я отправлю в случае необходимости",
                                                      parse_mode=html, reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.answering_machine)
@security('state')
async def _new_answering_machine(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    if message.content_type != "text":
        await message.answer("<b>Ваше сообщение не является текстом</b>", parse_mode=html,
                             reply_markup=(await answering_machine_menu(message.chat.id))['reply_markup'])
    elif len(message.text) > 512:
        await message.answer("<b>Ваше сообщение слишком длинное</b>", parse_mode=html,
                             reply_markup=(await answering_machine_menu(message.chat.id))['reply_markup'])
    elif message.text != "Отмена":
        answer_id = int(time.time()) - 1737828000  # 1737828000 - 2025/01/26 00:00 (день активного обновления автоответчика)
        entities = json_encode([entity.model_dump() for entity in message.entities or []])
        # Новый автоответ
        await db.execute(f"INSERT INTO answering_machine VALUES ({message.chat.id}, {answer_id}, "
                         f"false, 'ordinary', NULL, NULL, $1, '{entities}')", message.text)
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
    answer = await db.fetch_one(f"SELECT status, type, start_time, end_time, text, entities FROM answering_machine "
                                f"WHERE account_id={account_id} AND answer_id={answer_id}")
    if answer is None:  # Автоответ не найден
        return await answering_machine_menu(account_id)
    time_button = IButton(text="⏰ Расписание", callback_data=f"answering_machine_time{answer_id}")
    is_timetable = answer['type'] == 'timetable'
    if is_timetable:
        time_zone = await db.fetch_one(f"SELECT time_zone FROM settings WHERE account_id={account_id}", one_data=True)
        hours_start_time = str((answer['start_time'].hour + time_zone) % 24).rjust(2, "0")
        minutes_start_time = str(answer['start_time'].minute).rjust(2, "0")
        hours_end_time = str((answer['end_time'].hour + time_zone) % 24).rjust(2, "0")
        minutes_end_time = str(answer['end_time'].minute).rjust(2, "0")
        timetable = f"{hours_start_time}:{minutes_start_time} — {hours_end_time}:{minutes_end_time}"
        time_button = IButton(text=f"⏰ {timetable}", callback_data=f"answering_machine_time{answer_id}")
    status_button = IButton(text="🔴 Выключить автоответ", callback_data=f"answering_machine_off_{answer_id}") if answer['status'] \
        else IButton(text="🟢 Включить автоответ", callback_data=f"answering_machine_on_{answer_id}")
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="✏️ Текст", callback_data=f"answering_machine_edit_text{answer_id}"),
                                       time_button],
                                      [IButton(text="🚫 Удалить автоответ", callback_data=f"answering_machine_del_answer{answer_id}")],
                                      [IButton(text="◀️  Назад", callback_data="answering_machine")]])
    return {"text": str(answer['text']), "entities": answer['entities'], "reply_markup": markup}


@dp.callback_query(F.data.startswith("answering_machine_del_answer"))
@security()
async def _answering_machine_del_answer(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_del_answer", ""))
    account_id = callback_query.from_user.id
    await db.execute(f"DELETE FROM answering_machine WHERE account_id={account_id} AND answer_id={answer_id}")  # Удаление автоответа
    await callback_query.message.edit_text(**await answering_machine_menu(callback_query.message.chat.id))


@dp.callback_query(F.data.startswith("answering_machine_on").__or__(F.data.startswith("answering_machine_off")))
@security()
async def _answering_machine_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command, answer_id = callback_query.data.replace("answering_machine_", "").split("_")
    account_id = callback_query.from_user.id
    answer = await db.fetch_one(f"SELECT type, start_time, end_time FROM answering_machine "
                                f"WHERE account_id={account_id} AND answer_id={answer_id}")
    if answer is None:  # Автоответ не найден
        await callback_query.answer("Автоответ был удалено ранее!", True)
        return await callback_query.message.edit_text(**await answering_machine_menu(account_id))
    status = "true" if command == "on" else "false"
    if answer['type'] == "ordinary" and command == "on":  # Обыкновенный автоответ
        # Выключение включенного обыкновенного автоответа (если есть)
        await db.execute(f"UPDATE answering_machine SET status=false WHERE account_id={account_id} AND type='ordinary'")
        await callback_query.answer("Включенный ранее автоответ был выключен")
    elif answer['type'] == "timetable" and command == "on":  # Автоответ по расписанию
        # Автоответы по расписанию не должны пересекаться во времени
        for ans in await db.fetch_all(f"SELECT start_time, end_time FROM answering_machine WHERE account_id={account_id} "
                                      f"AND type='timetable' AND status=true AND answer_id!={answer_id}"):
            if answer['start_time'] < answer['end_time'] < ans['start_time'] < ans['end_time'] or \
                    ans['start_time'] < ans['end_time'] < answer['start_time'] < answer['end_time'] or \
                    answer['end_time'] < ans['start_time'] < ans['end_time'] < answer['start_time'] or \
                    ans['end_time'] < answer['start_time'] < answer['end_time'] < answer['start_time']:
                pass  # Все случаи, когда автоответы по времени не пересекаются
            else:
                return await callback_query.answer("Расписание данного автоответа пересекается с расписанием уже включенного", True)
    await db.execute(f"UPDATE answering_machine SET status={status} WHERE account_id={account_id} AND answer_id={answer_id}")
    await db.execute(f"UPDATE functions SET answering_machine_sending='[]' WHERE account_id={account_id}")
    await callback_query.message.edit_text(**await auto_answer_menu(account_id, answer_id))


@dp.callback_query(F.data.startswith("answering_machine_edit_text"))
@security('state')
async def _answering_machine_edit_text_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_edit_text", ""))
    await state.set_state(UserState.answering_machine_edit_text)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Напишите <b>текст</b>, который я отправлю в случае необходимости",
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
    if not await db.fetch_one(f"SELECT true FROM answering_machine WHERE account_id={account_id} AND answer_id={answer_id}"):
        await message.answer(**await answering_machine_menu(account_id))  # Автоответ не найден
    elif message.content_type != "text":
        await message.answer("<b>Ваше сообщение не является текстом</b>", parse_mode=html,
                             reply_markup=(await auto_answer_menu(message.chat.id, answer_id))['reply_markup'])
    elif len(message.text) > 512:
        await message.answer("<b>Ваше сообщение слишком длинное</b>", parse_mode=html,
                             reply_markup=(await auto_answer_menu(message.chat.id, answer_id))['reply_markup'])
    elif message.text != "Отмена":
        entities = json_encode([entity.model_dump() for entity in message.entities or []])
        await db.execute(f"UPDATE answering_machine SET text=$1, entities='{entities}' "
                         f"WHERE account_id={account_id} AND answer_id={answer_id}", message.text)  # Изменение автоответа
        await message.answer(**await auto_answer_menu(account_id, answer_id))
    else:
        await message.answer(**await auto_answer_menu(account_id, answer_id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data.startswith("answering_machine_time"))
@security()
async def _answering_machine_time(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_time", ""))
    await callback_query.message.edit_text(**await time_auto_answer_menu(callback_query.from_user.id, answer_id))


async def time_auto_answer_menu(account_id: int, answer_id: int) -> dict[str, Any]:
    answer = await db.fetch_one(f"SELECT type, start_time, end_time FROM answering_machine "
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
                                                [IButton(text="❌ Удалить расписание", callback_data=f"answering_machine_del_time{answer_id}")],
                                                [IButton(text="◀️  Назад", callback_data=f"answering_machine_menu{answer_id}")]])
        time_zone = await db.fetch_one(f"SELECT time_zone FROM settings WHERE account_id={account_id}", one_data=True)
        hours_start_time = str((answer['start_time'].hour + time_zone) % 24).rjust(2, "0")
        minutes_start_time = str(answer['start_time'].minute).rjust(2, "0")
        hours_end_time = str((answer['end_time'].hour + time_zone) % 24).rjust(2, "0")
        minutes_end_time = str(answer['end_time'].minute).rjust(2, "0")
        return {"text": f"Вы можете изменить или удалить расписание автоответа\n"
                        f"{hours_start_time}:{minutes_start_time} — {hours_end_time}:{minutes_end_time}",
                "reply_markup": reply_markup, "parse_mode": html}


@dp.callback_query(F.data.startswith("answering_machine_edit_timetable"))
@security('state')
async def _answering_machine_edit_timetable_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_edit_timetable", ""))
    await state.set_state(UserState.answering_machine_edit_timetable)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
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
                                 f"end_time='{hours_end_time}:{minutes_end_time}' "
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
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
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


@dp.callback_query(F.data.startswith("answering_machine_del_time"))
@security()
async def _answering_machine_del_time(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_del_time", ""))
    account_id = callback_query.from_user.id
    await db.execute(f"UPDATE answering_machine SET status=false, type='ordinary', start_time=NULL, end_time=NULL "
                     f"WHERE account_id={account_id} AND answer_id={answer_id}")
    await callback_query.message.edit_text(**await auto_answer_menu(account_id, answer_id))


@dp.callback_query(F.data == "registration")
@security('state')
async def _registration(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.send_phone_number)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отправить номер телефона", request_contact=True)],
                                           [KeyboardButton(text="Отмена")]], resize_keyboard=True)
    await callback_query.message.answer("Начнем настройку Maksogram для твоего аккаунта. Отправь свой номер телефона",
                                        reply_markup=markup)
    await callback_query.message.delete()


@dp.callback_query(F.data == "off")
@security()
async def _off(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    phone_number = await db.fetch_one(f"SELECT phone_number FROM accounts WHERE account_id={account_id}", one_data=True)
    await account_off(account_id, f"+{phone_number}")
    await callback_query.message.edit_text(**await menu(callback_query.message.chat.id))


@dp.callback_query(F.data == "on")
@security('state')
async def _on(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    phone_number = await db.fetch_one(f"SELECT phone_number FROM accounts WHERE account_id={account_id}", one_data=True)
    is_started = await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True)
    is_paid = await db.fetch_one(f"SELECT is_paid FROM payment WHERE account_id={account_id}", one_data=True)
    if is_started is False:  # Зарегистрирован, но отключен
        if is_paid is False:  # Просрочен платеж
            payment_message = await payment_menu(account_id)
            await callback_query.message.edit_text("Ваша подписка истекла. Продлите ее, чтобы пользоваться Maksogram\n"
                                                   f"{payment_message['text']}", reply_markup=payment_message['reply_markup'])
            name = await db.fetch_one(f"SELECT name FROM accounts WHERE account_id={account_id}", one_data=True)
            return await bot.send_message(OWNER, f"Платеж просрочен. Программа не запущена ({name})")
        try:
            await account_on(account_id, (admin_program if callback_query.message.chat.id == OWNER else program).Program)
        except UserIsNotAuthorized:  # Удалена сессия
            await state.set_state(UserState.relogin)
            await callback_query.answer("Удалена Telegram-сессия!")
            markup = ReplyKeyboardMarkup(keyboard=[[
                KeyboardButton(text="Отправить код", web_app=WebAppInfo(url="https://tgmaksim.ru/maksogram/code"))],
                [KeyboardButton(text="Отмена")]], resize_keyboard=True)
            await callback_query.message.answer("Вы удалили сессию Telegram, Maksogram больше не имеет доступа "
                                                "к вашему аккаунту. Пришлите код для повторного входа (<b>только кнопкой!</b>)",
                                                parse_mode=html, reply_markup=markup)
            await callback_query.message.delete()
            await telegram_clients[account_id].send_code_request(phone_number)
            return await bot.send_message(OWNER, "Повторный вход...")
    await callback_query.message.edit_text(**await menu(callback_query.message.chat.id))


@dp.message(UserState.relogin)
@security('state')
async def _relogin(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer("Если вы считаете, что мы собираем какие-либо данные, то зайдите на наш сайт и "
                                    "посмотрите открытый исходный код бота, который постоянно обновляется в "
                                    "сторону улучшений и безопасности", reply_markup=ReplyKeyboardRemove())
    if message.content_type != "web_app_data":
        await state.clear()
        return await message.answer("Код можно отправлять только через кнопку! Telegram блокирует вход при отправке кода "
                                    "кому-либо. Попробуйте еще раз сначала (возможно придется подождать)",
                                    reply_markup=ReplyKeyboardRemove())
    code = unzip_int_data(message.web_app_data.data)
    account_id = message.chat.id
    phone_number = await db.fetch_one(f"SELECT phone_number FROM accounts WHERE account_id={account_id}", one_data=True)
    try:
        await telegram_clients[account_id].sign_in(phone=phone_number, code=code)
    except errors.SessionPasswordNeededError:
        await state.set_state(UserState.relogin_with_password)
        markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
        await message.answer("Оправьте пароль от вашего аккаунта, он нужен для работы Maksogram!", reply_markup=markup)
        await bot.send_message(OWNER, "Установлен облачный пароль")
    except (errors.PhoneCodeEmptyError,
            errors.PhoneCodeExpiredError,
            errors.PhoneCodeHashEmptyError,
            errors.PhoneCodeInvalidError):
        await message.answer("Неправильный код! Попробуйте еще раз (только кнопкой!) 👇")
        await bot.send_message(OWNER, "Неправильный код")
    except Exception as e:
        await message.answer("Произошла ошибка при попытке входа. Мы уже работает над ее решением!")
        await bot.send_message(OWNER, f"⚠️ Ошибка (sign_in) ⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
    else:
        await state.clear()
        await account_on(account_id, (admin_program if message.chat.id == OWNER else program).Program)
        await message.answer("Maksogram запущен!", reply_markup=ReplyKeyboardRemove())


@dp.message(UserState.relogin_with_password)
@security('state')
async def _relogin_with_password(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer("Если вы считаете, что мы собираем какие-либо данные, то зайдите на наш сайт и "
                                    "посмотрите открытый исходный код бота, который постоянно обновляется в "
                                    "сторону улучшений и безопасности", reply_markup=ReplyKeyboardRemove())
    if message.content_type != "text":
        return await message.answer("Отправьте пароль от вашего аккаунта")
    account_id = message.chat.id
    phone_number = await db.fetch_one(f"SELECT phone_number FROM accounts WHERE account_id={account_id}", one_data=True)
    try:
        await telegram_clients[account_id].sign_in(phone=phone_number, password=message.text)
    except errors.PasswordHashInvalidError:
        await message.answer("Пароль неверный, попробуйте снова!")
    except Exception as e:
        await message.answer("Произошла ошибка при попытке входа. Мы уже работает над ее решением!")
        await bot.send_message(OWNER, f"⚠️ Ошибка (sign_in) ⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
    else:
        await state.clear()
        await account_on(account_id, (admin_program if message.chat.id == OWNER else program).Program)
        await message.answer("Maksogram запущен!", reply_markup=ReplyKeyboardRemove())


@dp.message(UserState.send_phone_number)
@security('state')
async def _contact(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer("Если вы считаете, что мы собираем какие-либо данные, то зайдите на наш сайт и "
                                    "посмотрите открытый исходный код бота, который постоянно обновляется в "
                                    "сторону улучшений и безопасности", reply_markup=ReplyKeyboardRemove())
    if message.content_type != "contact":
        return await message.reply("Вы не отправили контакт!")
    if message.chat.id != message.contact.user_id:
        return await message.reply("Это не ваш номер! Пожалуйста, воспользуйтесь кнопкой")
    await state.set_state(UserState.send_code)
    phone_number = '+' + message.contact.phone_number
    telegram_client = new_telegram_client(phone_number)
    await state.update_data(telegram_client=telegram_client, phone_number=phone_number)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отправить код", web_app=WebAppInfo(url=f"https://tgmaksim.ru/maksogram/code"))],
                                           [KeyboardButton(text="Отмена")]], resize_keyboard=True)
    await message.answer("Осталось отправить код для входа (<b>только кнопкой!</b>). Напоминаю, что мы не собираем "
                         f"никаких данных, а по любым вопросам можете обращаться в @{support}", reply_markup=markup, parse_mode=html)
    await telegram_client.connect()
    for i in range(10):
        if telegram_client.is_connected():
            await telegram_client.send_code_request(phone_number)
            break
        await asyncio.sleep(1)  # Ожидание соединения


@dp.message(UserState.send_code)
@security('state')
async def _login(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer("Если вы считаете, что мы собираем какие-либо данные, то зайдите на наш сайт и "
                                    "посмотрите открытый исходный код бота, который постоянно обновляется в "
                                    "сторону улучшений и безопасности", reply_markup=ReplyKeyboardRemove())
    if message.content_type != "web_app_data":
        await state.clear()
        return await message.answer("Код можно отправлять только через кнопку! Telegram блокирует вход при отправке "
                                    "кому-либо. Попробуйте еще раз сначала (возможно придется подождать)",
                                    reply_markup=ReplyKeyboardRemove())
    code = unzip_int_data(message.web_app_data.data)
    data = await state.get_data()
    telegram_client: TelegramClient = data['telegram_client']
    phone_number: str = data['phone_number']
    try:
        await telegram_client.sign_in(phone=phone_number, code=code)
    except errors.SessionPasswordNeededError:
        await state.set_state(UserState.send_password)
        markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
        await message.answer("У вас установлен облачный пароль (двухфакторная аутентификация). Отправьте его мне", reply_markup=markup)
        await bot.send_message(OWNER, "Установлен облачный пароль")
    except (errors.PhoneCodeEmptyError,
            errors.PhoneCodeExpiredError,
            errors.PhoneCodeHashEmptyError,
            errors.PhoneCodeInvalidError):
        await message.answer("Неправильный код! Попробуйте еще раз (только кнопкой!) 👇")
        await bot.send_message(OWNER, "Неправильный код")
    except Exception as e:
        await message.answer("Произошла ошибка при попытке входа. Мы уже работает над ее решением!")
        await bot.send_message(OWNER, f"⚠️ Ошибка (sign_in) ⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
    else:
        await state.clear()
        loading = await message.answer_sticker("CAACAgIAAxkBAAIyQWeUrH2jAUkcqHGYerWNT3ySuFwbAAJBAQACzRswCPHwYhjf9pZYNgQ", reply_markup=ReplyKeyboardRemove())
        try:
            await start_program(message.chat.id, message.from_user.username, int(phone_number), telegram_client)
        except CreateChatsError as e:
            await loading.delete()
            await message.answer(e.args[0])
            await bot.send_message(OWNER, e.args[1])
        except Exception as e:
            await loading.delete()
            await message.answer("Произошла ошибка при создании необходимых чатов. Мы уже работает над ее решением")
            await bot.send_message(OWNER, f"⚠️ Ошибка (start_program) ⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
        else:
            referal: int = await db.fetch_one(f"SELECT account_id FROM referals WHERE referal_id={message.chat.id}", one_data=True)
            if referal:
                await db.execute(f"""UPDATE payment SET next_payment=((CASE WHEN 
                                 next_payment > CURRENT_TIMESTAMP THEN 
                                 next_payment ELSE CURRENT_TIMESTAMP END) + INTERVAL '30 days'), 
                                 is_paid=true WHERE account_id={referal}""")  # перемещение даты оплаты на 30 дней вперед
                await db.execute(f"DELETE FROM referals WHERE referal_id={message.chat.id}")
                await bot.send_message(referal, "По вашей реферальной ссылке зарегистрировался пользователь. "
                                                "Вы получили месяц подписки в подарок!")
            await loading.delete()
            await message.answer("Maksogram запущен 🚀\nВ канале \"Мои сообщения\" будут храниться все ваши сообщения, в "
                                 "комментариях к постам будет информация о изменении и удалении\n"
                                 "Пробная подписка заканчивается через неделю")
            await message.answer(**await menu(message.chat.id))
            await bot.send_message(OWNER, "Создание чатов завершено успешно!")


@dp.message(UserState.send_password)
@security('state')
async def _login_with_password(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer("Если вы считаете, что мы собираем какие-либо данные, то зайдите на наш сайт и "
                                    "посмотрите открытый исходный код бота, который постоянно обновляется в "
                                    "сторону улучшений и безопасности", reply_markup=ReplyKeyboardRemove())
    if message.content_type != "text":
        return await message.answer("Отправьте пароль от вашего аккаунта")
    data = await state.get_data()
    telegram_client: TelegramClient = data['telegram_client']
    phone_number: str = data['phone_number']
    try:
        await telegram_client.sign_in(phone=phone_number, password=message.text)
    except errors.PasswordHashInvalidError:
        await message.answer("Пароль неверный, попробуйте снова!")
    except Exception as e:
        await state.clear()
        await message.answer("Произошла ошибка, обратитесь в поддержку...")
        await bot.send_message(OWNER, f"⚠️Ошибка⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
    else:
        await state.clear()
        loading = await message.answer_sticker("CAACAgIAAxkBAAIyQWeUrH2jAUkcqHGYerWNT3ySuFwbAAJBAQACzRswCPHwYhjf9pZYNgQ", reply_markup=ReplyKeyboardRemove())
        try:
            await start_program(message.chat.id, message.from_user.username, int(phone_number), telegram_client)
        except CreateChatsError as e:
            await loading.delete()
            await message.answer(e.args[0])
            await bot.send_message(OWNER, e.args[1])
        except Exception as e:
            await loading.delete()
            await message.answer("Произошла ошибка при создании необходимых чатов. Мы уже работает над ее решением")
            await bot.send_message(OWNER, f"⚠️ Ошибка (start_program) ⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
        else:
            referal: int = await db.fetch_one(f"SELECT account_id FROM referals WHERE referal_id={message.chat.id}", one_data=True)
            if referal:
                await db.execute(f"""UPDATE payment SET next_payment=((CASE WHEN 
                                 next_payment > CURRENT_TIMESTAMP THEN 
                                 next_payment ELSE CURRENT_TIMESTAMP END) + INTERVAL '30 days'), 
                                 is_paid=true WHERE account_id={referal}""")  # перемещение даты оплаты на 30 дней вперед
                await db.execute(f"DELETE FROM referals WHERE referal_id={message.chat.id}")
                await bot.send_message(referal, "По вашей реферальной ссылке зарегистрировался пользователь. "
                                                "Вы получили месяц подписки в подарок!")
            await loading.delete()
            await message.answer("Maksogram запущен 🚀\nВ канале \"Мои сообщения\" будут храниться все ваши сообщения, в "
                                 "комментариях к постам будет информация о изменении и удалении\n"
                                 "Пробная подписка заканчивается через неделю")
            await message.answer(**await menu(message.chat.id))
            await bot.send_message(OWNER, "Создание чатов завершено успешно!")


@dp.callback_query()
@security()
async def _other_callback_query(callback_query: CallbackQuery):
    await new_callback_query(callback_query)


@dp.message()
@security()
async def _other_message(message: Message):
    if await new_message(message): return


async def start_program(account_id: int, username: str, phone_number: int, telegram_client: TelegramClient):
    request = await create_chats(telegram_client)  # Создаем все нужные чаты, папки
    if request['result'] != "ok":
        raise CreateChatsError(request['message'], f"Произошла ошибка {request['error'].__class__.__name__}: {request['error']}")
    name = ('@' + username) if username else account_id
    next_payment = time_now() + timedelta(days=7)
    await db.execute(f"INSERT INTO accounts VALUES ({account_id}, '{name}', {phone_number}, "
                     f"{request['my_messages']}, {request['message_changes']}, now(), now())")
    await db.execute(f"INSERT INTO settings VALUES ({account_id}, '[]', '[]', true, 6, 'Омск')")
    await db.execute(f"INSERT INTO payment VALUES ({account_id}, 'user', {Variables.fee}, '{next_payment}', true)")
    await db.execute(f"INSERT INTO functions VALUES ({account_id}, '[]')")
    await db.execute(f"INSERT INTO modules VALUES ({account_id}, false, false, false, false, false)")
    await db.execute(f"INSERT INTO statistics VALUES ({account_id}, now(), now(), now())")
    telegram_clients[account_id] = telegram_client
    asyncio.get_running_loop().create_task(program.Program(telegram_client, account_id, [], time_now()).run_until_disconnected())


def referal_link(user_id: int) -> str:
    return "r" + zip_int_data(user_id)


async def username_acquaintance(message: Message, default: Literal[None, 'first_name'] = None):
    id = message.chat.id
    user = await db.fetch_one(f"SELECT name FROM acquaintances WHERE id={id}", one_data=True)
    if user is not None or default != 'first_name':
        return user
    return message.from_user.first_name


async def developer_command(message: Message) -> bool:
    await new_message(message)
    if message.chat.id == OWNER:
        await message.answer("<b>Команда разработчика активирована!</b>", parse_mode=html)
    else:
        await message.answer("<b>Команда разработчика НЕ была активирована</b>", parse_mode=html)

    return message.chat.id != OWNER


async def new_message(message: Message, /, forward: bool = True) -> bool:
    if message.content_type == "text":
        content = message.text
    elif message.content_type == "web_app_data":
        content = message.web_app_data.data
    elif message.content_type == "contact":
        content = f"contact {message.contact.phone_number}"
    elif message.content_type == "users_shared":
        content = f"user {message.users_shared.user_ids[0]}"
    else:
        content = f"'{message.content_type}'"
    id = str(message.chat.id)
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    date = str(omsk_time(message.date))
    acquaintance = await username_acquaintance(message)
    acquaintance = f"<b>Знакомый: {acquaintance}</b>\n" if acquaintance else ""

    if message.chat.id == OWNER:
        return False

    if forward and (message.entities and message.entities[0].type != 'bot_command'):  # Сообщение с форматированием
        await bot.send_message(
            OWNER,
            text=f"ID: {id}\n"
                 f"{acquaintance}" +
                 (f"USERNAME: @{username}\n" if username else "") +
                 f"Имя: {escape(first_name)}\n" +
                 (f"Фамилия: {escape(last_name)}\n" if last_name else "") +
                 f"Время: {date}",
            parse_mode=html)
        await message.forward(OWNER)
    elif forward:
        await bot.send_message(
            OWNER,
            text=f"ID: {id}\n"
                 f"{acquaintance}" +
                 (f"USERNAME: @{username}\n" if username else "") +
                 f"Имя: {escape(first_name)}\n" +
                 (f"Фамилия: {escape(last_name)}\n" if last_name else "") +
                 (f"<code>{escape(content)}</code>\n"
                  if not content.startswith("/") or len(content.split()) > 1 else f"{escape(content)}\n") +
                 f"Время: {date}",
            parse_mode=html)

    return False


async def new_callback_query(callback_query: CallbackQuery) -> bool:
    id = str(callback_query.message.chat.id)
    username = callback_query.from_user.username
    first_name = callback_query.from_user.first_name
    last_name = callback_query.from_user.last_name
    callback_data = callback_query.data
    date = str(time_now())
    acquaintance = await username_acquaintance(callback_query.message)
    acquaintance = f"<b>Знакомый: {acquaintance}</b>\n" if acquaintance else ""

    if callback_query.from_user.id == OWNER:
        return False

    await bot.send_message(
        OWNER,
        text=f"ID: {id}\n"
             f"{acquaintance}" +
             (f"USERNAME: @{username}\n" if username else "") +
             f"Имя: {escape(first_name)}\n" +
             (f"Фамилия: {escape(last_name)}\n" if last_name else "") +
             f"CALLBACK_DATA: {callback_data}\n"
             f"Время: {date}",
        parse_mode=html)

    return False


async def check_payment_datetime():
    for account_id in await db.fetch_all("SELECT account_id FROM accounts", one_data=True):
        account_id: int
        payment = await db.fetch_one(f"SELECT \"user\", next_payment FROM payment WHERE account_id={account_id}")
        if payment['user'] != 'user': continue
        if time_now() <= payment['next_payment'] <= (time_now() + timedelta(days=1)):  # За день до конца
            await bot.send_message(account_id, "Текущая подписка заканчивается! Произведите следующий "
                                               "платеж до конца завтрашнего дня")
            await bot.send_message(account_id, **await payment_menu(account_id))


async def start_bot():
    await check_payment_datetime()

    await bot.send_message(OWNER, f"<b>Бот запущен!🚀</b>", parse_mode=html)
    print("Запуск бота")
    await dp.start_polling(bot)
