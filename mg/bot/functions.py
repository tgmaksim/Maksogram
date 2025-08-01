from mg.config import testing, OWNER, SITE

from html import escape
from mg.core.database import Database
from datetime import datetime, timedelta
from typing import Optional, Literal, Union
from mg.core.functions import admin_time, time_now, zip_int_data

from telethon.hints import Entity
from mg.client.types import maksogram_clients
from mg.client.functions import get_is_started
from telethon.utils import parse_username, parse_phone, get_peer
from telethon.tl.types import User, Chat, Channel, PeerUser, InputPeerSelf
from aiogram.types import Message, CallbackQuery, LinkPreviewOptions, InlineQuery, ChosenInlineResult
from . types import Sleep, bot, Blocked, SubscriptionVariant, CallbackData, RequestUserResult, RequestChatResult


cb = CallbackData()
callbacks: dict[int, tuple[Union[int, str], str, datetime]] = {}  # Последнее нажатие кнопки пользователем в сообщении


async def new_message(message: Message, *, params: Optional[dict[str, str]] = None, accept_album: bool = False) -> bool:
    """
    Обрабатывает новое сообщение от пользователя боту и возвращает необходимость прервать диалог

    :param message: сообщение от пользователя
    :param params: дополнительные параметры для уведомления админа
    :param accept_album: если False (по умолчанию), то сообщение-альбом не будет обработан (только сообщение админу), True, если альбом нужен
    :return: True, если необходимо прервать диалог с пользователей (не нужно отвечать), иначе False
    """

    if message.chat.id == OWNER:
        if Sleep.reload or Sleep.loading:
            await message.answer("Бот перезагружается..." if Sleep.reload else "Бот загружается...")
        return Sleep.reload or Sleep.loading

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

    text = (f"User: <a href='tg://openmessage?user_id={message.chat.id}'>{message.chat.id}</a>",
            f"Msg: {message.message_id}",
            f"Username: @{message.from_user.username}" if message.from_user.username else None,
            f"Имя: {escape(message.from_user.first_name)}",
            f"Фамилия: {escape(message.from_user.last_name)}" if message.from_user.last_name else None,
            content,
            f"Время: {admin_time(message.date)}",
            *(f"{key}: {value}" for key, value in (params or {}).items()))
    await bot.send_message(OWNER, '\n'.join(filter(None, text)))

    if (message.entities and not message.entities[0].type == "bot_command") or message.contact:
        await message.forward(OWNER)  # В тексте есть форматирование (кроме команды) или отправлен контакт

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
        if Sleep.reload or Sleep.loading:
            await callback_query.answer("Бот перезагружается..." if Sleep.reload else "Бот загружается...", True)
        return Sleep.reload or Sleep.loading

    message_id = callback_query.inline_message_id or callback_query.message.message_id

    text = (f"User: <a href='tg://openmessage?user_id={callback_query.from_user.id}'>{callback_query.from_user.id}</a>",
            f"Msg: {message_id}",
            f"Username: @{callback_query.from_user.username}" if callback_query.from_user.username else None,
            f"Имя: {callback_query.from_user.first_name}",
            f"Фамилия: {callback_query.from_user.last_name}" if callback_query.from_user.last_name else None,
            callback_query.data,
            *(f"{key}: {value}" for key, value in (params or {}).items()))
    await bot.send_message(OWNER, '\n'.join(filter(None, text)))

    if callback := callbacks.get(callback_query.from_user.id):
        if callback[0] == message_id and callback[1] == callback_query.data and time_now() - callback[2] < timedelta(seconds=1):
            return True
    callbacks[callback_query.from_user.id] = (message_id, callback_query.data, time_now())  # Обновляем данные

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
        return Sleep.reload or Sleep.loading

    text = (f"User: <a href='tg://openmessage?user_id={inline_query.from_user.id}'>{inline_query.from_user.id}</a>",
            f"Query: {inline_query.id}",
            f"Username: @{inline_query.from_user.username}" if inline_query.from_user.username else None,
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


async def new_inline_result(inline_result: ChosenInlineResult, *, params: Optional[dict[str, str]] = None) -> bool:
    """
    Обрабатывает результаты inline-запросов от пользователя и возвращает необходимость прервать диалог

    :param inline_result: данные о результате запроса
    :param params: дополнительные параметры для уведомления админа
    :return: True, если необходимо прервать диалог с пользователей (не нужно отвечать), иначе False
    """

    if inline_result.from_user.id == OWNER:
        return Sleep.reload or Sleep.loading

    text = (f"User: <a href='tg://openmessage?user_id={inline_result.from_user.id}'>{inline_result.from_user.id}</a>",
            f"Result: {inline_result.result_id}",
            f"Username: @{inline_result.from_user.username}" if inline_result.from_user.username else None,
            f"Имя: {inline_result.from_user.first_name}",
            f"Фамилия: {inline_result.from_user.last_name}" if inline_result.from_user.last_name else None,
            inline_result.inline_message_id,
            *(f"{key}: {value}" for key, value in (params or {}).items()))
    await bot.send_message(OWNER, '\n'.join(filter(None, text)))

    if Sleep.reload or Sleep.loading:
        await bot.send_message(OWNER, "Бот перезагружается..." if Sleep.reload else "Бот загружается...")
        return True

    if testing:
        await bot.send_message(OWNER, "Ведется тестирование...")
        return True

    if inline_result.from_user.id in Blocked.users:
        await bot.send_message(OWNER, "Пользователь заблокирован")

    return inline_result.from_user.id in Blocked.users


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
    Запрашивает entity у Telegram из идентификатора пользователя, username'а, номера телефона или ``users_shared`` сообщения

    * Поиск по номеру телефона производится только по контактам или из сохраненных в кеше сессии

    * Поиск по username производится с помощью метода ``ResolveUsernameRequest`` (самый надежный)

    * Поиск по идентификатору пользователя производится из сохраненных в кеше сессии (или другими менее результативными способами)

    :param message: сообщение с данными
    :param can_yourself: можно ли выбрать себя
    :return: результат обработки сообщения с данные о статусе, ``User`` и предупреждении
    """

    account_id = message.chat.id

    if not await get_is_started(account_id):
        return RequestUserResult(
            ok=False,
            user=None,
            warning="Maksogram выключен"
        )

    user: Optional[Entity] = None
    entity, username, phone = None, (None, False), None
    if message.text:
        username = parse_username(message.text)
    if message.text and message.text.startswith('+'):  # Без + будет считаться ID
        phone = parse_phone(message.text)

    if message.text == "Себя":
        entity = InputPeerSelf()
    elif message.users_shared:
        entity = PeerUser(user_id=message.users_shared.user_ids[0])
    elif username[0] and username[1] is False:  # username имеет формат @username, а не ссылка-приглашение
        entity = f"@{username[0]}"
    elif phone:
        entity = f"+{phone}"
    elif message.text and message.text.isdigit():  # ID пользователя
        entity = PeerUser(user_id=int(message.text))

    if isinstance(entity, InputPeerSelf) or (isinstance(entity, PeerUser) and entity.user_id == account_id):
        user: User = await maksogram_clients[account_id].client.get_me()
    elif entity:
        try:
            user: Entity = await maksogram_clients[account_id].client.get_entity(entity)
        except ValueError as e:
            maksogram_clients[account_id].logger.warning(f"entity '{entity}' не найден (ошибка {e.__class__.__name__}: {e})")

    if not user:  # Пользователь не найден или данные неверные
        suggestion = "Попробуйте отправить @username пользователя" if not (username[0] and username[1] is False) else None
        return RequestUserResult(
            ok=False,
            user=None,
            warning='\n'.join(filter(None, ("Пользователь не найден", suggestion)))  # Предложение использовать username
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
            user=user,  # User
            warning=None
        )


async def request_chat(message: Message) -> RequestChatResult:
    """
    Запрашивает entity у Telegram из идентификатора чата, username'а или ``chat_shared`` сообщения

    * Поиск по username производится с помощью метода ``ResolveUsernameRequest`` (самый надежный)

    * Поиск по ссылке-приглашению производится с помощью метода ``CheckChatInviteRequest`` (тоже надежный)

    * Поиск по идентификатору чата или канала производится из сохраненных в кеше сессии (или другими менее результативными способами).
    Идентификатор должен быть отрицательный ('-' для чата, '-100' для канала)

    :param message: сообщение с данными
    :return: результат обработки сообщения с данные о статусе, ``Chat`` или ``Channel`` и предупреждении
    """

    account_id = message.chat.id

    if not await get_is_started(account_id):
        return RequestChatResult(
            ok=False,
            chat=None,
            warning="Maksogram выключен"
        )

    chat: Optional[Entity] = None
    entity, username = None, (None, False)
    if message.text:
        username = parse_username(message.text)

    if message.chat_shared:
        entity = get_peer(message.chat_shared.chat_id)  # Entity (Chat, Channel)
    elif username[0] and username[1] is False:  # username имеет формат @username, а не ссылка-приглашение
        entity = f"@{username[0]}"
    elif username[0] and username[1] is True:  # ссылка-приглашение
        entity = message.text
    elif message.text and (message.text[0] == '-' and message.text[1:].isdigit() or message.text.isdigit()):  # ID чата
        entity = get_peer(int(message.text))  # Entity (User, Chat, Channel)

    if entity:
        try:
            chat = await maksogram_clients[account_id].client.get_entity(entity)
        except ValueError as e:
            maksogram_clients[account_id].logger.warning(f"entity '{entity}' не найден (ошибка {e.__class__.__name__}: {e})")

    if not chat:  # Чат не найден или данные неверные
        suggestion = "Попробуйте отправить @username чата или ссылку приглашение" if not username[0] else None
        return RequestChatResult(
            ok=False,
            chat=None,
            warning='\n'.join(filter(None, ("Групповой чат или канал не найден!", suggestion)))  # Предложение использовать username
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


async def get_subscription_variants() -> list[SubscriptionVariant]:
    """Возвращает доступные варианты подписки"""

    sql = "SELECT subscription_id, duration, discount, about FROM subscriptions ORDER BY subscription_id"
    data: list[dict] =  await Database.fetch_all(sql)

    return SubscriptionVariant.list_from_json(data)


async def get_subscription_variant(subscription_id: int) -> SubscriptionVariant:
    """Возвращает вариант подписки с subscription_id"""

    sql = f"SELECT subscription_id, duration, discount, about FROM subscriptions WHERE subscription_id={subscription_id}"
    data: dict = await Database.fetch_row(sql)

    return SubscriptionVariant.from_json(data)


async def set_time_subscription_notification(account_id: int, type_notification: Literal["first", "second"]):
    """Обновляет время отправки уведомления о подписки"""

    sql = f"UPDATE payment SET {type_notification}_notification=now() WHERE account_id={account_id}"
    await Database.execute(sql)
