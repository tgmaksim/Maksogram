import aiohttp

from mg.config import testing, OWNER, SITE, CRYPTO_API_KEY

from html import escape
from decimal import Decimal
from mg.core.database import Database
from typing import Optional, Union, Literal
from mg.core.functions import admin_time, time_now, zip_int_data

from mg.client.types import maksogram_clients
from mg.client.functions import get_is_started
from telethon.tl.types import User, Chat, Channel
from telethon.utils import parse_username, parse_phone
from aiogram.types import Message, CallbackQuery, LinkPreviewOptions, InlineQuery
from . types import Sleep, bot, Blocked, Subscription, CallbackData, PaymentCurrency, AmountPaymentCurrency, RequestUserResult, RequestChatResult


cb = CallbackData()
callbacks: dict[int, tuple[int, str]] = {}  # Последнее нажатие кнопки пользователем в сообщении


async def new_message(message: Message, *, params: Optional[dict[str, str]] = None, accept_album: bool = False) -> bool:
    """
    Обрабатывает новое сообщение от пользователя боту и возвращает необходимость прервать диалог

    :param message: сообщение от пользователя
    :param params: дополнительные параметры для уведомления админа
    :param accept_album: если False (по умолчанию), то сообщение-альбом не будет обработан (только сообщение админу), True, если альбом нужен
    :return: True, если необходимо прервать диалог с пользователей (не нужно отвечать), иначе False
    """

    if message.chat.id == OWNER:
        return False  # Сообщения от админа не обрабатываются и никогда не игнорируются

    if message.text:
        content = escape(message.text)
        if not message.text.startswith('/') or len(message.text.split()) > 1:
            content = f"<code>{content}</code>"  # Если не является командой (/start, /help) или имеет параметры (/start menu)

        if message.text.startswith('/start'):
            if await check_new_user(message.chat.id):  # Пользователь запустил бота в первый раз
                await message.forward(OWNER)
    elif message.web_app_data:
        content = escape(message.web_app_data.data)
    elif message.contact:
        content = f"contact {message.contact.phone_number}"
    elif message.users_shared:
        if len(message.users_shared.user_ids) == 1:
            content = f"user {message.users_shared.user_ids[0]}"
        else:
            content = f"users {tuple(message.users_shared.user_ids)}"
    elif message.chat_shared:
        content = f"chat {message.chat_shared.chat_id}"
    else:
        album = "album " if message.media_group_id else ""
        content = f"{album}'{message.content_type}'".lower().removeprefix('contenttype.')

    text = (f"User: {message.chat.id}",
            f"Msg: {message.message_id}",
            f"Username: {message.from_user.username}" if message.from_user.username else None,
            f"Имя: {escape(message.from_user.first_name)}",
            f"Фамилия: {escape(message.from_user.last_name)}" if message.from_user.last_name else None,
            content,
            f"Время: {admin_time(message.date)}",
            *(f"{key}: {value}" for key, value in (params or {}).items()))
    await bot.send_message(OWNER, '\n'.join(filter(None, text)))

    if message.entities and not message.entities[0].type == "bot_command":
        await message.forward(OWNER)  # В тексте есть форматирование (кроме команды)

    if testing:
        await message.answer("Ведутся технические работы...")
        await bot.send_message(OWNER, "Ведется тестирование...")
        return True

    if message.chat.id in Blocked.users:
        await bot.send_message(OWNER, "Пользователь заблокирован")

    if Sleep.reload or Sleep.loading:
        await message.answer("Подождите минуту, бот перезагружается!" if Sleep.reload else "Подождите несколько секунд, бот загружается!")
        await bot.send_message(OWNER, "Бот перезагружается..." if Sleep.reload else "Бот загружается...")
        return True

    if not accept_album and message.media_group_id:
        await message.answer("Альбом с несколькими медиа не поддерживается!")
        return True  # Если альбом необходимо проигнорировать

    return message.chat.id in Blocked.users


async def check_new_user(user_id: int) -> bool:
    """Проверяет, запустил ли пользователь бота в первый раз или нет"""

    sql = f"SELECT true FROM users WHERE user_id={user_id}"
    data: bool = await Database.fetch_row_for_one(sql)

    if not data:
        sql = "INSERT INTO users (user_id, launch_time) VALUES ($1, now())"
        await Database.execute(sql, user_id)

    return not data


async def new_callback_query(callback_query: CallbackQuery, *, params: Optional[dict[str, str]] = None) -> bool:
    """
    Обрабатывает нажатие на кнопку от пользователя и возвращает необходимость прервать диалог

    :param callback_query: данные о нажатии кнопки
    :param params: дополнительные параметры для уведомления админа
    :return: True, если необходимо прервать диалог с пользователей (не нужно отвечать), иначе False
    """

    if callback_query.from_user.id == OWNER:
        return False  # Нажатия кнопок от админа не обрабатываются и никогда не игнорируются

    text = (f"User: {callback_query.from_user.id}",
            f"Msg: {callback_query.message.message_id}",
            f"Username: {callback_query.from_user.username}" if callback_query.from_user.username else None,
            f"Имя: {callback_query.from_user.first_name}",
            f"Фамилия: {callback_query.from_user.last_name}" if callback_query.from_user.last_name else None,
            callback_query.data,
            *(f"{key}: {value}" for key, value in (params or {}).items()))
    await bot.send_message(OWNER, '\n'.join(filter(None, text)))

    if callback := callbacks.get(callback_query.from_user.id):
        if callback[0] == callback_query.message.message_id and callback[1] == callback_query.data:  # Прошлое нажатие той же кнопки
            return True
    callbacks[callback_query.from_user.id] = (callback_query.message.message_id, callback_query.data)  # Обновляем данные

    if Sleep.reload or Sleep.loading:
        await callback_query.answer("Подождите минуту, бот перезагружается!" if Sleep.reload else "Подождите несколько секунд, бот загружается!", True)
        await bot.send_message(OWNER, "Бот перезагружается..." if Sleep.reload else "Бот загружается...")
        return True

    if testing:
        await callback_query.answer("Ведутся технические работы...", True)
        await bot.send_message(OWNER, "Ведется тестирование...")
        return True

    if callback_query.from_user.id in Blocked.users:
        await bot.send_message(OWNER, "Пользователь заблокирован")

    return callback_query.from_user.id in Blocked.users


async def developer_command(message: Message) -> bool:
    """
    Обрабатывает команду разработчика и возвращает необходимость прервать диалог

    :param message: сообщение от пользователя
    :return: True, если необходимо прервать диалог с пользователем (не нужно отвечать), иначе False
    """

    await new_message(message)

    if message.chat.id == OWNER:
        await message.answer("<b>Команда разработчика активирована</b>")

    return message.chat.id != OWNER


async def new_inline_query(inline_query: InlineQuery, *, params: Optional[dict[str, str]] = None) -> bool:
    """
    Обрабатывает inline-запрос от пользователя и возвращает необходимость прервать диалог

    :param inline_query: данные о запросе
    :param params: дополнительные параметры для уведомления админа
    :return: True, если необходимо прервать диалог с пользователей (не нужно отвечать), иначе False
    """

    if inline_query.from_user.id == OWNER:
        return False  # Inline-запросы от админа не обрабатываются и никогда не игнорируются

    text = (f"User: {inline_query.from_user.id}",
            f"Query: {inline_query.id}",
            f"Username: {inline_query.from_user.username}" if inline_query.from_user.username else None,
            f"Имя: {inline_query.from_user.first_name}",
            f"Фамилия: {inline_query.from_user.last_name}" if inline_query.from_user.last_name else None,
            inline_query.query,
            *(f"{key}: {value}" for key, value in (params or {}).items()))
    await bot.send_message(OWNER, '\n'.join(filter(None, text)))

    if Sleep.reload or Sleep.loading:
        await bot.send_message(OWNER, "Бот перезагружается..." if Sleep.reload else "Бот загружается...")
        return True

    if testing:
        await bot.send_message(OWNER, "Ведется тестирование...")
        return True

    if inline_query.from_user.id in Blocked.users:
        await bot.send_message(OWNER, "Пользователь заблокирован")

    return inline_query.from_user.id in Blocked.users


def preview_options(path: str = '', *, site: str = SITE, show_above_text: bool = False):
    """Создает LinkPreviewOptions для ссылки с большой картинкой"""

    return LinkPreviewOptions(
        url=f"{site}/{path}",
        prefer_large_media=True,
        show_above_text=show_above_text
    )


async def get_blocked_users() -> list[int]:
    """Возвращает список заблокированных админом пользователей"""

    sql = "SELECT user_id FROM blocked_users"
    data: list[int] = await Database.fetch_all_for_one(sql)

    return data


async def generate_sensitive_link(account_id: int, event: str = "menu_link", preview: str = "") -> str:
    """
    Генерирует ссылку с привязкой к клиенту и событию. После перехода по такой ссылке, админ получает уведомление

    :param account_id: клиент
    :param event: событие
    :param preview: идентификатор функции, на которую будет ссылаться ссылка
    :return: чувствительная ссылка
    """

    if account_id == OWNER:
        return f"{SITE}?обзор={preview}"

    token = int(time_now().timestamp() * 1000)
    text = f"User: {account_id}\nСобытие: {event}"

    sql = f"INSERT INTO sensitive_links (account_id, token, text) VALUES ($1, $2, $3)"
    await Database.execute(sql, account_id, token, text)

    return f"{SITE}?обзор={preview}&t={token}"


def referral_link(account_id: int) -> str:
    """Создает реферальную ссылку для клиента"""

    return 'r' + zip_int_data(account_id)


async def get_referral(account_id: int) -> Optional[int]:
    """Возвращает клиента, который пригласил нового пользователя"""

    sql = f"SELECT account_id FROM referrals WHERE friend_id={account_id}"
    data: Optional[int] = await Database.fetch_row_for_one(sql)

    return data


async def request_user(message: Message, can_yourself: bool = True) -> RequestUserResult:
    """
    Запрашивает entity у Telegram из идентификатора пользователя, username'а, номера телефона или users_shared сообщения

    :param message: сообщение с данными
    :param can_yourself: можно ли выбрать себя
    :return: результат обработки сообщения с данные о статусе, User и предупреждении
    """

    account_id = message.chat.id

    if not await get_is_started(account_id):
        return RequestUserResult(
            ok=False,
            user=None,
            warning="Maksogram выключен"
        )

    entity, user, username, phone = None, None, None, None
    if message.text and message.text.startswith('@'):
        username = parse_username(message.text)
    if message.text and message.text.startswith('+'):  # Без + будет считаться ID
        phone = parse_phone(message.text)

    if message.text == "Себя":
        entity = account_id
    elif message.users_shared:
        entity = message.users_shared.user_ids[0]
    elif username and username[0] is not None and username[1] is False:  # username имеет формат @username, а не ссылка-приглашение
        entity = username[0]
    elif phone:
        entity = f"+{phone}"
    elif message.text and message.text.isdigit():  # ID пользователя
        entity = int(message.text)

    if entity:
        try:
            user = await maksogram_clients[account_id].client.get_entity(entity)
        except ValueError as e:
            maksogram_clients[account_id].logger.warning(f"entity '{entity}' не найден (ошибка {e.__class__.__name__}: {e})")

    if not user:  # Пользователь не найден или данные неверные
        return RequestUserResult(
            ok=False,
            user=None,
            warning="Пользователь не найден"
        )
    elif not isinstance(user, User) or user.bot or user.support:
        return RequestUserResult(
            ok=False,
            user=None,
            warning="Не является пользователем!"
        )
    elif not can_yourself and user.id == account_id:
        return RequestUserResult(
            ok=False,
            user=user,
            warning="Собственный аккаунт выбрать нельзя!"
        )
    else:
        return RequestUserResult(
            ok=True,
            user=user,
            warning=None
        )


async def request_chat(message: Message) -> RequestChatResult:
    """
    Запрашивает entity у Telegram из идентификатора чата, username'а или chat_shared сообщения

    :param message: сообщение с данными
    :return: результат обработки сообщения с данные о статусе, Chat или Channel и предупреждении
    """

    account_id = message.chat.id

    if not await get_is_started(account_id):
        return RequestChatResult(
            ok=False,
            chat=None,
            warning="Maksogram выключен"
        )

    entity, chat, username = None, None, None
    if message.text and message.text.startswith('@'):
        username = parse_username(message.text)

    if message.chat_shared:
        entity = message.chat_shared.chat_id
    elif username and username[0] is not None and username[1] is False:  # username имеет формат @username, а не ссылка-приглашение
        entity = username[0]
    elif message.text and message.text.isdigit():  # ID чата
        entity = int(message.text)

    if entity:
        try:
            chat = await maksogram_clients[account_id].client.get_entity(entity)
        except ValueError as e:
            maksogram_clients[account_id].logger.warning(f"entity '{entity}' не найден (ошибка {e.__class__.__name__}: {e})")

    if not chat:  # Чат не найден или данные неверные
        return RequestChatResult(
            ok=False,
            chat=None,
            warning="Групповой чат или канал не найден!"
        )
    elif not isinstance(chat, (Channel, Chat)):
        return RequestChatResult(
            ok=False,
            chat=None,
            warning="Не является групповым чатом или каналом!"
        )
    else:
        return RequestChatResult(
            ok=True,
            chat=chat,
            warning=None
        )


async def get_subscriptions() -> list[Subscription]:
    """Возвращает доступные варианты подписки"""

    sql = "SELECT subscription_id, duration, discount, about FROM subscriptions ORDER BY subscription_id"
    data: list[dict] =  await Database.fetch_all(sql)

    return Subscription.list_from_json(data)


async def get_subscription(subscription_id: int) -> Subscription:
    """Возвращает вариант подписки с subscription_id"""

    sql = f"SELECT subscription_id, duration, discount, about FROM subscriptions WHERE subscription_id={subscription_id}"
    data: dict = await Database.fetch_row(sql)

    return Subscription.from_json(data)


async def get_currencies() -> list[PaymentCurrency]:
    """Возвращает список доступных для оплаты валют"""

    sql = "SELECT name, coefficient, accuracy, min FROM currencies"
    data: list[dict] = await Database.fetch_all(sql)

    return PaymentCurrency.list_from_json(data)


async def convert_ruble(amount_rub: float, currencies: list[PaymentCurrency]) -> dict[str, Union[int, AmountPaymentCurrency]]:
    """
    Конвертирует цену в рублях в криптовалюты

    :param amount_rub: цена в рублях
    :param currencies: список валют для оплаты
    :return: словарь: {"RUB": int, название криптовалюты: данные о цене в рублях и валюте}
    """

    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {"X-CMC_PRO_API_KEY": CRYPTO_API_KEY}
    params = {"symbol": ",".join(map(lambda c: c.name, currencies)), "convert": "RUB"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as response:
            data = await response.json()
            result: dict = {"RUB": int(amount_rub)}

            for currency in currencies:
                price = data['data'][currency.name]['quote']['RUB']['price']  # Курс криптовалюты к рублю
                amount = round(amount_rub / price * currency.coefficient, currency.accuracy)  # Вычисляем сумму с учетом коэффициента скидки валюты

                if currency.min:  # Если есть минимальный порог у криптовалюты
                    amount = max(amount, round(currency.min, currency.accuracy))

                result[currency.name] = AmountPaymentCurrency(round(amount * price), str(Decimal(str(amount))))  # Вычисляем цену в рублях и валюте

            return result


async def set_time_subscription_notification(account_id: int, type_notification: Literal["first", "second"]):
    """Обновляет время отправки уведомления о подписки"""

    sql = f"UPDATE payment SET {type_notification}_notification=now() WHERE account_id={account_id}"
    await Database.execute(sql)
