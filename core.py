OWNER = 5128609241
support = "tgmaksim_company"
SITE = "https://tgmaksim.ru/проекты/maksogram"
subscribe = "https://t.me/+F5YW1gV3gdhjNjVi"
channel = "tgmaksim_ru"
morning = 5, 12

html = "HTML"
s1, s2 = "{}"

import os
import json
import string
import asyncio
import sys_keys
import traceback

from aiogram import Bot
from typing import Union, Any
from database import Database
from telethon import TelegramClient
from datetime import datetime, timedelta
from telethon.tl.functions.photos import GetUserPhotosRequest
from sys_keys import sessions_path, TOKEN, BOT_ID, USERNAME_BOT
from aiogram.types import LinkPreviewOptions, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile


class UserIsNotAuthorized(Exception):
    pass


telegram_clients: dict[int, TelegramClient] = {}


def resources_path(path: str) -> str:
    return sys_keys.resources_path(path)


def json_decode(json_string: str) -> Union[dict, list]:
    return json.JSONDecoder().decode(json_string)


def json_encode(dictionary: Union[dict, list]) -> str:
    return json.JSONEncoder().encode(dictionary)


def zip_int_data(int_data: int) -> str:
    letters = string.digits + string.ascii_letters
    result = ''
    while int_data > 0:
        result = letters[int_data % len(letters)] + result
        int_data //= len(letters)
    return result


def unzip_int_data(data: str) -> int:
    letters = string.digits + string.ascii_letters
    result = 0
    for i, letter in enumerate(reversed(data)):
        result += letters.find(letter) * len(letters)**i
    return result


class db:
    @staticmethod
    async def execute(sql: str, *params) -> bool:
        async with Database() as conn:
            return await conn.execute(sql, *params)

    @staticmethod
    async def fetch_all(sql: str, *params, one_data: bool = False) -> Union[list[dict], list]:
        async with Database() as conn:
            return await conn.fetch_all(sql, *params, one_data=one_data)

    @staticmethod
    async def fetch_one(sql: str, *params, one_data: bool = False) -> Union[dict, Any]:
        async with Database() as conn:
            return await conn.fetch_one(sql, *params, one_data=one_data)


async def count_avatars(account_id: int, user_id: int) -> int:
    return len((await telegram_clients[account_id](GetUserPhotosRequest(user_id, 0, 0, 128))).photos)


async def check_connection(telegram_client: TelegramClient) -> bool:
    try:
        await telegram_client.is_user_authorized()
    except ConnectionError:
        return False
    else:
        return True


async def telegram_client_connect(telegram_client: TelegramClient) -> bool:
    await telegram_client.connect()
    for i in range(5):
        if await check_connection(telegram_client):
            return True
        await telegram_client.connect()
        await asyncio.sleep(1)
    return False  # Если за пять попыток соединение не установлено...


async def account_off(account_id: int):
    phone_number = f"+{await db.fetch_one(f'SELECT phone_number FROM accounts WHERE account_id={account_id}', one_data=True)}"
    await db.execute(f"UPDATE settings SET is_started=false WHERE account_id={account_id}")
    telegram_client, telegram_clients[account_id] = telegram_clients[account_id], new_telegram_client(phone_number)
    if telegram_client.is_connected():
        await telegram_client.disconnect()


async def account_on(account_id: int, Program):
    telegram_client = telegram_clients[account_id]
    if not await check_connection(telegram_client):  # Требуется соединение
        if not await telegram_client_connect(telegram_client):
            raise ConnectionError("За десять попыток соединение не установлено")
    if await telegram_client.is_user_authorized():
        await db.execute(f"UPDATE settings SET is_started=true WHERE account_id={account_id}")
        status_users = await db.fetch_all(f"SELECT user_id FROM status_users WHERE account_id={account_id}", one_data=True)
        morning_notification = await db.fetch_one(f"SELECT morning_notification FROM accounts WHERE account_id={account_id}", one_data=True)
        asyncio.get_running_loop().create_task(Program(telegram_clients[account_id], account_id, status_users, morning_notification)
                                               .run_until_disconnected())
    else:
        raise UserIsNotAuthorized()


async def get_enabled_auto_answer(account_id: int) -> Union[int, None]:
    # Если включен обыкновенный автоответ, то он будет главным, в противном случае - включенный автоответ по расписанию (если есть)
    enabled_ordinary_auto_answer = await db.fetch_one(f"SELECT answer_id FROM answering_machine WHERE account_id={account_id} AND "
                                                       f"type='ordinary' AND status=true", one_data=True)
    now = str(time_now().time())
    enabled_timetable_auto_answer = await db.fetch_one(
        f"SELECT answer_id FROM answering_machine WHERE account_id={account_id} AND type='timetable' "
        f"AND status=true AND (start_time < end_time AND start_time <= '{now}' AND end_time >= '{now}' OR "
        f"start_time > end_time AND (start_time <= '{now}' OR end_time >= '{now}'))", one_data=True)
    return enabled_ordinary_auto_answer or enabled_timetable_auto_answer  # Обыкновенный автоответ первостепеннее


def security(*arguments):
    def new_decorator(fun):
        async def new(_object, **kwargs):
            try:
                await fun(_object, **{kw: kwargs[kw] for kw in kwargs if kw in arguments})
            except Exception as e:
                exception = "".join(traceback.format_exception(e))
                await MaksogramBot.send_system_message(f"⚠️Ошибка⚠️\n\n{exception}")

        return new

    return new_decorator


def human_bytes(size: int):
    b = float(size)
    Kb = float(1 * 2**10)
    Mb = float(Kb * 2**10)
    Gb = float(Mb * 2**10)

    if b < Kb:
        return '{0} Б'.format(b)
    elif Kb <= b < Mb:
        return '{0:.2f} КБ'.format(b / Kb)
    elif Mb <= b < Gb:
        return '{0:.2f} МБ'.format(b / Mb)
    elif Gb <= b:
        return '{0:.2f} ГБ'.format(b / Gb)


def time_now() -> datetime:
    return datetime.utcnow()


def omsk_time(t: datetime):
    tz = int(t.tzinfo.utcoffset(None).total_seconds() // 3600)
    return (t + timedelta(hours=6-tz)).replace(tzinfo=None)


def preview_options(path="", site=SITE):
    return LinkPreviewOptions(prefer_large_media=True, url=f"{site}/{path}")


def new_telegram_client(phone_number: str) -> TelegramClient:
    return TelegramClient(
        sessions_path(phone_number),
        Variables.TelegramApplicationId,
        Variables.TelegramApplicationHash,
        device_model="Maksogram in Chat",
        system_version="Maksogram platform v2",
        app_version=Variables.version_string.replace(" ", "-").replace("(", "").replace(")", ""),
        lang_code="ru",
        system_lang_code="ru"
    )


class Variables:
    version = "2.5"
    version_string = "2.5.4 (35)"
    fee = 150

    TelegramApplicationId = int(os.environ['TelegramApplicationId'])
    TelegramApplicationHash = os.environ['TelegramApplicationHash']

    ApiKey = os.environ['ApiKey']
    ProcessId = os.environ['ProcessIdMaksogram']


class MaksogramBot:
    id = BOT_ID
    username = USERNAME_BOT
    bot = Bot(TOKEN)

    IMarkup = InlineKeyboardMarkup
    IButton = InlineKeyboardButton

    @staticmethod
    async def send_message(chat_id: int, message: str, photo=None, **kwargs):
        if photo:
            photo = FSInputFile(photo)
            return await MaksogramBot.bot.send_photo(chat_id, photo=photo, caption=message, **kwargs)
        return await MaksogramBot.bot.send_message(chat_id, str(message), **kwargs)

    @staticmethod
    async def send_system_message(message: str, **kwargs):
        return await MaksogramBot.bot.send_message(OWNER, str(message), **kwargs)
