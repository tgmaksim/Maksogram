import hashlib
import asyncio

from mg.config import OWNER, CHANNEL_ID, TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_DC_ID, TELEGRAM_DC_IP, TELEGRAM_DC_PORT, VERSION, VERSION_ID

from typing import Optional, Union
from mg.core.database import Database
from mg.core.functions import www_path, session_path, resources_path

from telethon import TelegramClient
from telethon.tl.patched import Message
from telethon.helpers import add_surrogate

from telethon.tl.types import (
    PhotoEmpty,
    WebPageEmpty,
    GeoPointEmpty,
    DocumentEmpty,
    StoryItemDeleted,
    StoryItemSkipped,
    WebPageNotModified,

    MessageMediaGeo,
    MessageMediaDice,
    MessageMediaStory,
    MessageMediaVenue,
    MessageMediaPhoto,
    MessageMediaWebPage,
    MessageMediaContact,
    MessageMediaDocument,
)

from . types import SavedMessage


def new_telegram_client(account_id: int) -> TelegramClient:
    client = TelegramClient(
        session_path(str(account_id)),
        TELEGRAM_API_ID,
        TELEGRAM_API_HASH,
        device_model=f"MG-Client-{account_id}",
        system_version=f"Maksogram {VERSION_ID}",
        app_version=VERSION.replace('(', '[').replace(')', ']'),
        lang_code="ru",
        system_lang_code="ru"
    )
    client.session.set_dc(TELEGRAM_DC_ID, TELEGRAM_DC_IP, TELEGRAM_DC_PORT)

    return client


async def check_connection(client: TelegramClient) -> bool:
    """Проверяет соединение TelegramClient с сервером"""

    try:
        await client.is_user_authorized()
    except ConnectionError:
        return False
    return True


async def client_connect(client: TelegramClient):
    """Устанавливает соединение TelegramClient с сервером"""

    for i in range(5):
        await client.connect()

        if await check_connection(client):
            return True  # Соединение установлено

        await asyncio.sleep(1)

    return False  # Соединение так и не было установлено


def is_one_line(text: Optional[str]) -> Optional[bool]:
    """
    Проверяет, является ли текст одной строкой

    :param text: текст или `None`
    :return: `None`, если в текст является `None`, `True`, если текст является одной строкой, иначе `False`
    """

    if text is None:
        return None

    return '\n' not in text


def has_command(text: Optional[str], commands: Union[str, list[str]], *, has_all: bool = False) -> Optional[bool]:
    """
    Проверяет наличие хотя бы одной (или всех) команд в тексте

    :param text: текст сообщения или `None`
    :param commands: команды (команды), которые должны быть в тексте
    :param has_all: `True`, если все команды должны быть в тексте, иначе `False`
    :return: `None`, если текст пустой, `True`, если необходимое количество команд присутствует в тексте, иначе `False`
    """

    if not text:
        return None

    if isinstance(commands, str):
        commands = [commands]

    function = all if has_all else any

    return function([command in commands for command in text.split()])


async def download_voice(account_id: int, message: Message) -> str:
    """
    Сохраняет голосовое или кружок из сообщения и возвращает ссылку на него

    :param account_id: клиент
    :param message: сообщение с голосовым или кружком
    :return: ссылка для скачивания медиа на сервере
    """

    path = f"sounds/{account_id}.{message.chat_id}.{message.id}.ogg"
    await message.download_media(www_path(path))

    return path


async def download_video(account_id: int, message: Message) -> str:
    """
    Сохраняет видео и возвращает path к файлу

    :param account_id: клиент
    :param message: сообщение с медиа
    :return: path к сохраненному видео
    """

    path = resources_path(f"round_video/{account_id}.{message.chat_id}.{message.id}.mp4")
    await message.download_media(path)

    return path


async def update_statistics_by_module(account_id: int, module_name: str):
    """Обновляет время последнего использования модуля"""

    sql = f"UPDATE statistics SET {module_name}=now() WHERE account_id={account_id}"
    await Database.execute(sql)


def len_text(text: str) -> int:
    """Подсчитывает длину текста в кодировке, которую использует Telegram"""

    return len(add_surrogate(text))


def message_hash(message: Message) -> str:
    """
    Подсчитывает hash (хеш-функцией md5) текста сообщения для распознавания изменений

    :param message: сообщение
    :return: подсчитанный хеш
    """

    data = message.text.encode('utf-16')

    return hashlib.md5(data).hexdigest()


def check_edited_message(message: Message, saved_message: SavedMessage) -> bool:
    """
    Проверяет, изменилось ли содержание сообщения (текст или медиа)

    :param message: измененное сообщение
    :param saved_message: сохраненное сообщение
    :return: `True`, если сообщение изменило содержание, иначе `False`
    """

    if saved_message.media != media_id(message):  # Медиа изменилось
        return True

    return message_hash(message) != saved_message.hash


def is_storable_message(message: Message) -> bool:
    """Проверяет медиа на необходимость сохранения"""

    if isinstance(message.media, MessageMediaPhoto):
        return not isinstance(message.media.photo, PhotoEmpty)

    if isinstance(message.media, MessageMediaDocument):
        return not isinstance(message.media.document, DocumentEmpty)

    if isinstance(message.media, MessageMediaWebPage):
        return not isinstance(message.media.webpage, (WebPageEmpty, WebPageNotModified))

    if isinstance(message.media, MessageMediaStory):
        return not isinstance(message.media.story, (StoryItemDeleted, StoryItemSkipped))

    if isinstance(message.media, (MessageMediaGeo, MessageMediaVenue)):
        return not isinstance(message.media.geo, GeoPointEmpty)

    if isinstance(message.media, (MessageMediaContact, MessageMediaDice)):
        return True

    return not bool(message.media)


def media_id(message: Message) -> Optional[int]:
    """Получает идентификатор медиа"""

    if isinstance(message.media, MessageMediaPhoto):
        return message.media.photo.id

    if isinstance(message.media, MessageMediaDocument):
        return message.media.document.id

    if isinstance(message.media, MessageMediaWebPage):
        return message.media.webpage.id

    if isinstance(message.media, (MessageMediaContact, MessageMediaStory, MessageMediaGeo, MessageMediaVenue, MessageMediaDice)):
        return 0  # Изменить сообщение невозможно, значит идентификатор можно оставить 0

    return None


async def get_phone_number(account_id: int) -> str:
    """Возвращает номер телефона в формате международном формате"""

    sql = f"SELECT phone_number FROM accounts WHERE account_id={account_id}"
    phone_data: int = await Database.fetch_row_for_one(sql)

    return f"+{phone_data}"


async def set_is_started(account_id: int, value: bool):
    """Изменяет состояние клиента в базе данных"""

    sql = f"UPDATE settings SET is_started=$1 WHERE account_id={account_id}"
    await Database.execute(sql, value)


async def get_is_started(account_id: int) -> Optional[bool]:
    """Возвращает состояние клиента"""

    sql = f"SELECT is_started FROM settings WHERE account_id={account_id}"
    data: Optional[bool] = await Database.fetch_row_for_one(sql)

    return data


async def get_is_paid(account_id: int) -> bool:
    """Возвращает статус оплаты подписки у клиента"""

    sql = f"SELECT is_paid FROM payment WHERE account_id={account_id}"
    data: bool = await Database.fetch_row_for_one(sql)

    return data


async def get_accounts() -> list[tuple[int, bool]]:
    """
    Возвращает список клиентов с их идентификатором и статусом (выключен, включен)

    :return: список клиентов с идентификатором и статусом (выключен, включен)
    """

    sql = "SELECT account_id, is_started FROM settings"
    data: list[dict[str, Union[int, bool]]] = await Database.fetch_all(sql)
    accounts = [(account_data['account_id'], account_data['is_started']) for account_data in data]

    return accounts


async def get_min_admin_log_id() -> int:
    """Возвращает минимальный log_id в канале админа"""

    sql = f"SELECT min_log_id FROM channel_event_logger WHERE account_id={OWNER} AND channel_id={CHANNEL_ID}"
    data: int = await Database.fetch_row_for_one(sql)

    return data


async def set_min_admin_log_id(log_id: int):
    """Изменяет минимальный log_id в канале админа"""

    sql = f"UPDATE channel_event_logger SET min_log_id={log_id} WHERE account_id={OWNER} AND channel_id={CHANNEL_ID}"
    await Database.execute(sql)


async def get_morning_functions(account_id: int) -> tuple[bool, bool]:
    """Возвращает статус утренних модулей (погода и курсы валют)"""

    sql = f"SELECT morning_weather, morning_currencies FROM modules WHERE account_id={account_id}"
    data: dict[str, bool] = await Database.fetch_row(sql)

    return data['morning_weather'], data['morning_currencies']
