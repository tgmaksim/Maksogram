from typing import Any
from html import escape
from typing import Literal
from core import (
    db,
    html,
    OWNER,
    time_now,
    omsk_time,
    zip_int_data,
)

from core import MaksogramBot
from aiogram import Dispatcher
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    WebAppInfo,
    CallbackQuery,
)


bot = MaksogramBot.bot
dp = Dispatcher()


# Класс с глобальными переменными для удобного пользования
class Data:
    web_app = "https://tgmaksim.ru/maksogram"
    banned = []


# Класс нужен для определения состояния пользователя в данном боте,
# например: пользователь должен отправить отзыв в следующем сообщении
class UserState(StatesGroup):
    class Admin(StatesGroup):
        mailing = State('mailing')
        confirm_mailing = State('confirm_mailing')

    time_zone = State('time_zone')
    city = State('city')
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


async def payment_menu(account_id: int) -> dict[str, Any]:
    fee = await db.fetch_one(f"SELECT fee FROM payment WHERE account_id={account_id}", one_data=True)  # Цена подписки
    markup = IMarkup(inline_keyboard=[[IButton(text="TON", web_app=WebAppInfo(url=f"{Data.web_app}/payment/ton")),
                                       IButton(text="BTC", web_app=WebAppInfo(url=f"{Data.web_app}/payment/btc"))],
                                      [IButton(text="Перевод по номеру", web_app=WebAppInfo(url=f"{Data.web_app}/payment/fps"))],
                                      [IButton(text="Я отправил(а)  ✅", callback_data="send_payment")]])
    return {"text": f"Способы оплаты (любой):\nСбер: ({fee} руб)\nBTC: (0.00002 btc)\nTON: (0.4 ton)",
            "parse_mode": html, "reply_markup": markup}


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


async def new_message(message: Message) -> bool:
    if message.chat.id == OWNER:
        return False

    if message.content_type == "text":
        content = message.text
    elif message.content_type == "web_app_data":
        content = message.web_app_data.data
    elif message.content_type == "contact":
        content = f"contact {message.contact.phone_number}"
    elif message.content_type == "users_shared":
        content = f"user {message.users_shared.user_ids[0]}"
    else:
        content = f"'{str(message.content_type).lower().replace('contenttype.', '')}'"
    id = str(message.chat.id)
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    date = str(omsk_time(message.date))
    acquaintance = await username_acquaintance(message)
    acquaintance = f"<b>Знакомый: {acquaintance}</b>\n" if acquaintance else ""

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

    if message.chat.id in Data.banned:
        await bot.send_message(OWNER, "Пользователь заблокирован!")
    return message.chat.id in Data.banned


async def new_callback_query(callback_query: CallbackQuery) -> bool:
    if callback_query.from_user.id == OWNER:
        return False

    id = str(callback_query.message.chat.id)
    username = callback_query.from_user.username
    first_name = callback_query.from_user.first_name
    last_name = callback_query.from_user.last_name
    callback_data = callback_query.data
    date = str(time_now())
    acquaintance = await username_acquaintance(callback_query.message)
    acquaintance = f"<b>Знакомый: {acquaintance}</b>\n" if acquaintance else ""

    await bot.send_message(
        OWNER,
        text=f"ID: {id}\n"
             f"{acquaintance}" +
             (f"USERNAME: @{username}\n" if username else "") +
             f"Имя: {escape(first_name)}\n" +
             (f"Фамилия: {escape(last_name)}\n" if last_name else "") +
             f"Кнопка: {callback_data}\n"
             f"Время: {date}",
        parse_mode=html)

    if callback_query.from_user.id in Data.banned:
        await bot.send_message(OWNER, "Пользователь заблокирован!")
    return callback_query.from_user.id in Data.banned
