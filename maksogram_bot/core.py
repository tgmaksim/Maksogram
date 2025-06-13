import aiohttp

from html import escape
from typing import Literal
from decimal import Decimal
from sys_keys import crypto_api_key
from telethon.utils import parse_username, parse_phone
from typing import Any, Union, Callable, Coroutine, Optional
from core import (
    n,
    db,
    html,
    OWNER,
    omsk_time,
    zip_int_data,
    resources_path,
    telegram_clients,
)

from core import MaksogramBot
from aiogram import Dispatcher
from telethon.tl.types import User
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from aiogram.types import (
    Message,
    WebAppInfo,
    InlineQuery,
    FSInputFile,
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
        login = State('login')

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
    answering_machine_edit_weekdays = State('answering_machine_edit_weekdays')
    answering_machine_new_trigger = State('answering_machine_new_trigger')
    changed_profile = State('changed_profile')
    security_email = State('security_email')
    confirm_security_email = State('confirm_security_email')
    security_new_agent = State('security_new_agent')
    add_chat = State('add_chat')
    remove_chat = State('remove_chat')
    ghost_stories = State('ghost_stories')
    ghost_copy = State('ghost_copy')
    speed_answer_trigger = State('speed_answer_trigger')
    speed_answer_text = State('speed_answer_text')
    speed_answer_edit = State('speed_answer_edit')
    main_currency = State('main_currency')
    my_currencies = State('my_currencies')


async def convert_ruble(amount_rub: int, currencies: dict[str, Union[str, int]]) -> dict[str, Union[dict[str, int], int]]:
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {"X-CMC_PRO_API_KEY": crypto_api_key}
    params = {"symbol": ",".join(map(lambda x: x['name'], currencies)), "convert": "RUB"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as response:
            data = await response.json()
            result = {"RUB": int(amount_rub)}
            for currency in currencies:
                price = data['data'][currency['name']]['quote']['RUB']['price']
                amount = round(amount_rub / price * currency['coefficient'], currency['accuracy'])
                if currency['min']: amount = max(amount, round(currency['min'], currency['accuracy']))
                result[currency['name']] = {"RUB": round(amount * price), currency['name']: str(Decimal(str(amount)))}
            return result


async def payment_menu() -> dict[str, Any]:
    subscriptions = await db.fetch_all("SELECT subscription_id, about FROM subscriptions ORDER BY subscription_id")
    i, buttons = 0, []
    while i < len(subscriptions):
        if i + 1 < len(subscriptions):
            buttons.append([IButton(text=subscriptions[j]['about'], callback_data=f"subscription{subscriptions[j]['subscription_id']}")
                            for j in [i, i+1]])
            i += 1
        else:
            buttons.append([IButton(text=subscriptions[i]['about'], callback_data=f"subscription{subscriptions[i]['subscription_id']}")])
        i += 1
    return {"caption": "Подписка Maksogram с полным набором всех доступных функций", "parse_mode": html,
            "reply_markup": IMarkup(inline_keyboard=buttons), "photo": FSInputFile(resources_path("logo.jpg"))}


async def subscription_menu(account_id: int, subscription_id: int) -> dict[str, Any]:
    subscription = await db.fetch_one(f"SELECT duration, discount, about FROM subscriptions WHERE subscription_id={subscription_id}")
    fee = await db.fetch_one(f"SELECT fee FROM payment WHERE account_id={account_id}", one_data=True)
    currencies = await db.fetch_all("SELECT name, coefficient, accuracy, min FROM currencies")
    without_discount = fee * (subscription['duration']/30)
    fee = await convert_ruble(without_discount * (1 - subscription['discount']/100), currencies)  # Вычисляем цену по скидке
    buttons = [IButton(text=currency['name'], web_app=WebAppInfo(url=f"{Data.web_app}/payment/{currency['name'].lower()}"))
               for currency in currencies]
    markup = IMarkup(inline_keyboard=[buttons,
                                      [IButton(text="Перевод по номеру", web_app=WebAppInfo(url=f"{Data.web_app}/payment/rub"))],
                                      [IButton(text="Я отправил(а)  ✅", callback_data=f"send_payment{subscription_id}")],
                                      [IButton(text="◀️  Назад", callback_data="payment")]])
    payment_methods = [f"{currency['name']}: {fee[currency['name']][currency['name']]} {currency['name'].lower()} " \
                       f"(≈ {fee[currency['name']]['RUB']} руб)" for currency in currencies]
    discount = "без скидки" if subscription['discount'] == 0 else f"-{subscription['discount']}%"
    without_discount = f" (вместо {int(without_discount)} руб)" if fee['RUB'] != without_discount else ""
    return {"caption": f"Maksogram на {subscription['about'].lower()} {discount}\nСбер: {fee['RUB']} руб{without_discount}\n"
                       f"{n.join(payment_methods)}",
            "parse_mode": html, "reply_markup": markup}


async def new_user(message: Message, menu_users: Callable[[int, Optional[str]], Coroutine[Any, Any, dict[str, Any]]]):
    account_id = message.chat.id
    if not await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True):
        await message.answer(**await menu_users(account_id, "<b>Maksogram выключен!</b>"))
    elif message.text == "Отмена":
        await message.answer(**await menu_users(account_id, None))
    else:  # Maksogram запущен
        entity, user = None, None
        username, phone = message.text and parse_username(message.text), message.text and parse_phone(message.text)
        if message.text == "Себя":
            entity = account_id
        elif message.content_type == "users_shared":
            entity = message.users_shared.user_ids[0]
        elif username[1] is False and username[0] is not None:  # Является ли строка username (не ссылка с приглашением)
            entity = username[0]
        elif phone and message.text.startswith('+'):
            entity = f"+{phone}"
        elif message.text and message.text.isdigit():  # ID пользователя
            entity = int(message.text)

        if entity:
            try:
                user = await telegram_clients[account_id].get_entity(entity)
            except ValueError:  # Пользователь с такими данными не найден
                pass

        if not user:  # Если не найден, не является User или не человек
            await message.answer(**await menu_users(account_id, "<b>Пользователь не найден!</b>"))
        elif not isinstance(user, User) or user.bot or user.support:  # Канал, группа, бот или поддержка
            await message.answer(**await menu_users(account_id, "<b>Не является пользователем!</b>"))
        else:
            return user


def referal_link(user_id: int) -> str:
    return "r" + zip_int_data(user_id)


async def username_acquaintance(id: int, first_name: str, default: Literal[None, 'first_name'] = None):
    user = await db.fetch_one(f"SELECT name FROM acquaintances WHERE id={id}", one_data=True)
    if user is not None or default != 'first_name':
        return user
    return first_name


async def developer_command(message: Message) -> bool:
    await new_message(message)
    if message.chat.id == OWNER:
        await message.answer("<b>Команда разработчика активирована!</b>", parse_mode=html)

    return message.chat.id != OWNER


async def new_message(message: Message, params: dict[str, str] = None) -> bool:
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
    message_id = str(message.message_id)
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    date = str(omsk_time(message.date))
    acquaintance = await username_acquaintance(message.chat.id, first_name)

    text = f"ID: {id}\n" \
           f"MSG: {message_id}\n" + \
           (f"<b>Знакомый: {acquaintance}</b>\n" if acquaintance else "") + \
           (f"USERNAME: @{username}\n" if username else "") + \
           f"Имя: {escape(first_name)}\n" + \
           (f"Фамилия: {escape(last_name)}\n" if last_name else "") + \
           (f"<code>{escape(content)}</code>\n" if not content.startswith("/") or len(content.split()) > 1 else
            f"{escape(content)}\n") + \
           f"Время: {date}\n" + \
           "\n".join([f"{key}: {params[key]}" for key in params or []])

    await bot.send_message(OWNER, text=text, parse_mode=html)

    if message.chat.id in Data.banned:
        await bot.send_message(OWNER, "Пользователь заблокирован!")
    return message.chat.id in Data.banned


async def new_callback_query(callback_query: CallbackQuery, params: dict[str, str] = None) -> bool:
    if callback_query.from_user.id == OWNER:
        return False

    id = str(callback_query.message.chat.id)
    username = callback_query.from_user.username
    first_name = callback_query.from_user.first_name
    last_name = callback_query.from_user.last_name
    callback_data = callback_query.data
    acquaintance = await username_acquaintance(callback_query.from_user.id, first_name)

    text = f"ID: {id}\n" + \
           (f"<b>Знакомый: {acquaintance}</b>\n" if acquaintance else "") + \
           (f"USERNAME: @{username}\n" if username else "") + \
           f"Имя: {escape(first_name)}\n" + \
           (f"Фамилия: {escape(last_name)}\n" if last_name else "") + \
           f"Кнопка: {callback_data}\n" + \
           "\n".join([f"{key}: {params[key]}" for key in params or []])

    await bot.send_message(OWNER, text=text, parse_mode=html)

    if callback_query.from_user.id in Data.banned:
        await bot.send_message(OWNER, "Пользователь заблокирован!")
    return callback_query.from_user.id in Data.banned


async def new_inline_query(inline_query: InlineQuery, params: dict[str, str] = None):
    if inline_query.from_user.id == OWNER:
        return

    id = str(inline_query.from_user.id)
    username = inline_query.from_user.username
    first_name = inline_query.from_user.first_name
    last_name = inline_query.from_user.last_name
    query = inline_query.query
    acquaintance = await username_acquaintance(inline_query.from_user.id, first_name)

    text = f"ID: {id}\n" + \
           (f"<b>Знакомый: {acquaintance}</b>\n" if acquaintance else "") + \
           (f"USERNAME: @{username}\n" if username else "") + \
           f"Имя: {escape(first_name)}\n" + \
           (f"Фамилия: {escape(last_name)}\n" if last_name else "") + \
           f"Поиск: {query}\n" + \
           "\n".join([f"{key}: {params[key]}" for key in params or []])

    await bot.send_message(OWNER, text=text, parse_mode=html)

    if inline_query.from_user.id in Data.banned:
        await bot.send_message(OWNER, "Пользователь заблокирован!")
    return inline_query.from_user.id in Data.banned
