import string
import aiosmtplib

from mg import config
from mg.config import email_config

from math import ceil
from functools import wraps
from email.header import Header
from email.mime.text import MIMEText
from traceback import format_exception
from datetime import datetime, timedelta, UTC
from typing import Callable, Awaitable, Union, Optional

from . database import Database
from aiogram.types import MessageEntity
from . types import MaksogramBot, AccountSettings, PaymentData

from telethon.tl.types import (
    User,

    MessageEntityPre,
    MessageEntityCode,
    MessageEntityBold,
    TypeMessageEntity,
    MessageEntityItalic,
    MessageEntityStrike,
    MessageEntitySpoiler,
    MessageEntityTextUrl,
    MessageEntityUnderline,
    MessageEntityBlockquote,
    MessageEntityCustomEmoji,
)


ADMIN_TIME_ZONE = +6


def resources_path(path: str) -> str:
    """Возвращает абсолютный путь к файлу в системе"""

    return f"{config.resources_path}/{path}"


def session_path(path: str) -> str:
    """Возвращает абсолютный путь к файлу сессии"""

    return f"{config.sessions_path}/{path}.session"


def www_path(path: str) -> str:
    """Возвращает полный путь к фалу в папке, из которой можно скачать файл"""

    return f"{config.www_path}/{path}"


def log_path(path: str) -> str:
    """Возвращает полный путь к файлу в папке с логами"""

    return f"{config.log_path}/{path}"


def format_error(error: Exception):
    return ''.join(format_exception(error))


def error_notify(*fun_parameters: str):
    """Декоратор для уведомления об ошибке админа"""

    def decorator(func: Callable[..., Awaitable]):
        @wraps(func)
        async def wrapper(_obj, **kwargs):
            parameters = {key: kwargs[key] for key in kwargs if key in fun_parameters}  # Список параметров, которых ждет функция
            try:
                await func(_obj, **parameters)
            except Exception as error:
                text = format_error(error)
                for i in range(0, len(text), 4096):
                    await MaksogramBot.send_system_message(text[i:min(i + 4096, len(text))], parse_mode=None)

        return wrapper

    return decorator


def time_now(time_zone: int = 0) -> datetime:
    """Возвращает текущее время в заданном часовом поясе"""

    return (datetime.now(UTC) + timedelta(hours=time_zone)).replace(tzinfo=None)


def admin_time(t: datetime):
    """Изменяет часовой пояс времени на время админа"""

    tz = int(t.tzinfo.utcoffset(None).total_seconds() // 3600)  # Часовой пояс

    return (t + timedelta(hours=ADMIN_TIME_ZONE-tz)).replace(tzinfo=None)


def zip_int_data(number: int) -> str:
    """Сжимает число в строковый формат"""

    letters = string.digits + string.ascii_letters
    result = ''

    while number > 0:
        result = letters[number % len(letters)] + result
        number //= len(letters)

    return result


def unzip_int_data(data: str) -> int:
    """Конвертирует обратно сжатую строку в число"""

    letters = string.digits + string.ascii_letters
    result = 0

    for i, letter in enumerate(reversed(data)):
        result += letters.find(letter) * len(letters) ** i

    return result


def human_timedelta(t: Union[timedelta, int]) -> str:
    """
    Форматирует timedelta в понятный для человека формат

    :param t: timedelta или количество секунд
    :return: строка со временем в понятном для человека формате
    """

    if isinstance(t, timedelta):
        t = t.total_seconds()

    years = f"{int(t / (365 * 24 * 60 * 60))}г " if int(t / (365 * 24 * 60 * 60)) > 0 else ""
    months = f"{int(t % (365 * 24 * 60 * 60) / (30 * 24 * 60 * 60))}м " if int(t / (30 * 24 * 60 * 60)) > 0 else ""
    days = f"{int(t % (30 * 24 * 60 * 60) / (24 * 60 * 60))}д " if int(t / (24 * 60 * 60)) > 0 else ""
    hours = f"{int(t % (24 * 60 * 60) / (60 * 60))}ч "
    minutes = f"{ceil(t % (60 * 60) / 60)}мин"

    return f"{years}{months}{days}{hours}{minutes}"


async def get_account_status(account_id: int) -> Optional[bool]:
    """
    Возвращает статус клиента (включен Maksogram, выключен или незарегистрирован)

    :param account_id: клиент
    :return: None, если незарегистрирован, True, если включен, иначе False
    """

    sql = f"SELECT is_started FROM settings WHERE account_id={account_id}"
    data: Optional[bool] = await Database.fetch_row_for_one(sql)

    return data


async def send_email_message(to: str, subject: str, text: str, *, subtype: str = 'plain'):
    msg = MIMEText(text, subtype, 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = email_config['user']
    msg['To'] = to

    smtp = aiosmtplib.SMTP(hostname=email_config['host'], port=25, start_tls=False)
    await smtp.connect()
    await smtp.starttls()
    await smtp.login(email_config['user'], email_config['password'])
    await smtp.send_message(msg)
    await smtp.quit()


def full_name(user: User) -> str:
    """Возвращает полное имя пользователя (имя + фамилия)"""

    if user.last_name:
        return f"{user.first_name} {user.last_name}"

    return user.first_name


async def renew_subscription(account_id: int, days: int):
    """Продлевает подписку клиенту на заданный период"""

    # Если подписка истекла, то прибавляем к текущему времени, иначе к окончанию подписки
    sql = "UPDATE payment SET ending=((CASE WHEN ending IS NOT NULL AND ending > CURRENT_TIMESTAMP THEN ending ELSE CURRENT_TIMESTAMP END) + "\
          f"INTERVAL '{days} days'), subscription='premium' WHERE account_id={account_id}"
    await Database.execute(sql)


async def get_settings(account_id: int) -> AccountSettings:
    """Возвращает настройки клиента из базы данных"""

    sql = f"SELECT is_started, added_chats, removed_chats, time_zone, city, gender, saving_messages, notify_changes FROM settings WHERE account_id={account_id}"
    data: dict = await Database.fetch_row(sql)

    return AccountSettings.from_json(data)


async def get_subscription(account_id: int) -> Optional[str]:
    """Возвращает вариант подключенной подписки"""

    sql = f"SELECT subscription FROM payment WHERE account_id={account_id}"
    data: Optional[str] = await Database.fetch_row_for_one(sql)

    return data


async def get_payment_data(account_id: int) -> PaymentData:
    """Возвращает данные подписки клиента из базы данных"""

    sql = f"SELECT subscription, fee, ending, first_notification, second_notification FROM payment WHERE account_id={account_id}"
    data: dict = await Database.fetch_row(sql)

    return PaymentData.from_json(data)


async def reset_subscription(account_id: int):
    """Удаляет подписку у клиента"""

    sql = f"UPDATE payment SET subscription=NULL, ending=NULL WHERE account_id={account_id}"
    await Database.execute(sql)

    sql = f"UPDATE modules SET auto_audio_transcription=false WHERE account_id={account_id}"
    await Database.execute(sql)

    # Удаляет все автоответы с нейро-ответами
    sql = f"DELETE FROM answering_machine WHERE account_id={account_id} AND ai=true"
    await Database.execute(sql)

    # Удаляет все автоответы клиента кроме самого старого
    sql = (f"DELETE FROM answering_machine WHERE answer_id!="
           f"(SELECT MIN(answer_id) FROM answering_machine WHERE account_id={account_id}) AND account_id={account_id}")
    await Database.execute(sql)

    # Удаляет все быстрые ответы клиента кроме самого старого
    sql = f"DELETE FROM changed_profiles WHERE user_id!=(SELECT MIN(user_id) FROM changed_profiles WHERE account_id={account_id}) AND account_id={account_id}"
    await Database.execute(sql)

    # Удаляет всех пользователей в Профиле друга кроме одного с минимальным user_id
    sql = f"DELETE FROM speed_answers WHERE answer_id!=(SELECT MIN(answer_id) FROM speed_answers WHERE account_id={account_id}) AND account_id={account_id}"
    await Database.execute(sql)

    # Удаляет всех пользователей в "Друг в сети" кроме одного с минимальным user_id
    sql = f"DELETE FROM status_users WHERE user_id!=(SELECT MIN(user_id) FROM status_users WHERE account_id={account_id}) AND account_id={account_id}"
    await Database.execute(sql)

    # Удаляет все добавленные рабочие чаты
    sql = f"UPDATE settings SET added_chats='{{}}' WHERE account_id={account_id}"
    await Database.execute(sql)

    # Удаляет все огоньки клиента кроме самого продолжительного по серии
    sql = (f"DELETE FROM fires WHERE user_id!=(SELECT user_id FROM fires WHERE days="
           f"(SELECT MAX(days) FROM fires WHERE account_id={account_id}) AND account_id={account_id} LIMIT 1) AND account_id={account_id}")
    await Database.execute(sql)


def serialize_aiogram_entities(entities: list[MessageEntity]) -> list[dict]:
    """Сериализует список MessageEntity (aiogram) в JSON-формат"""

    return [entity.model_dump() for entity in entities]


def deserialize_aiogram_entities(json_data: list[dict]) -> list[MessageEntity]:
    """Десериализует JSON-список в список MessageEntity (aiogram)"""

    return [MessageEntity.model_validate(data) for data in json_data]


def deserialize_tl_entities(json_data: list[dict]) -> list[TypeMessageEntity]:
    """Десериализует JSON-список в список MessageEntity (telethon)"""

    entities = []
    for entity in json_data:
        match entity['type']:
            case "bold":
                entities.append(MessageEntityBold(entity['offset'], entity['length']))
            case "italic":
                entities.append(MessageEntityItalic(entity['offset'], entity['length']))
            case "underline":
                entities.append(MessageEntityUnderline(entity['offset'], entity['length']))
            case "strikethrough":
                entities.append(MessageEntityStrike(entity['offset'], entity['length']))
            case "spoiler":
                entities.append(MessageEntitySpoiler(entity['offset'], entity['length']))
            case "blockquote":
                entities.append(MessageEntityBlockquote(entity['offset'], entity['length']))
            case "expandable_blockquote":
                entities.append(MessageEntityBlockquote(entity['offset'], entity['length'], True))
            case "code":
                entities.append(MessageEntityCode(entity['offset'], entity['length']))
            case "pre":
                entities.append(MessageEntityPre(entity['offset'], entity['length'], entity['language']))
            case "text_link":
                entities.append(MessageEntityTextUrl(entity['offset'], entity['length'], entity['url']))
            case "custom_emoji":
                entities.append(MessageEntityCustomEmoji(entity['offset'], entity['length'], int(entity['custom_emoji_id'])))

    return entities


async def get_time_zone(account_id: int) -> int:
    """Возвращает часовой пояс клиента"""

    sql = f"SELECT time_zone FROM settings WHERE account_id={account_id}"
    data: int = await Database.fetch_row_for_one(sql)

    return data
