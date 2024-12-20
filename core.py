OWNER = 5128609241
SITE = "https://tgmaksim.ru/проекты/maksogram"
subscribe = "https://t.me/+F5YW1gV3gdhjNjVi"
channel = "@tgmaksim_ru"

markdown = "Markdown"
html = "HTML"

import os
import json
import string
import sys_keys
import aiosqlite
import traceback

from aiogram import Bot
from typing import Union
from telethon.sync import TelegramClient
from datetime import datetime, timedelta
from aiogram.types import LinkPreviewOptions
from sys_keys import TOKEN, sessions_path, BOT_ID, USERNAME_BOT


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
    db_path = "db.sqlite3"

    @staticmethod
    async def execute(sql: str, params: tuple = None) -> tuple[tuple[Union[str, int]]]:
        async with aiosqlite.connect(resources_path(db.db_path)) as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                result = await cur.fetchall()
            await conn.commit()
        return result


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
    return datetime.utcnow() + timedelta(hours=6)


def omsk_time(t: datetime):
    tz = int(t.tzinfo.utcoffset(None).total_seconds() // 3600)
    return (t + timedelta(hours=6-tz)).replace(tzinfo=None)


async def get_users() -> set:
    return set(map(lambda x: int(x[0]), await db.execute("SELECT id FROM users")))


def preview_options(path="", site="https://tgmaksim.ru/проекты/maksogram"):
    return LinkPreviewOptions(prefer_large_media=True, url=f"{site}/{path}")


def get_telegram_client(phone_number: str):
    return TelegramClient(
        sessions_path(phone_number),
        Variables.TelegramApplicationId,
        Variables.TelegramApplicationHash,
        device_model="Maksogram in Chat",
        system_version="Maksogram v%s" % Variables.version,
        app_version=Variables.version,
        lang_code="ru",
        system_lang_code="ru"
    )


class Variables:
    version = "2.2"
    fee = 150

    TelegramApplicationId = int(os.environ['TelegramApplicationId'])
    TelegramApplicationHash = os.environ['TelegramApplicationHash']

    ApiKey = os.environ['ApiKey']
    ProcessId = os.environ['ProcessIdMaksogram']


class MaksogramBot:
    id = BOT_ID
    username = USERNAME_BOT
    bot = Bot(TOKEN)

    @staticmethod
    async def send_message(chat_id: int, message: str, **kwargs):
        return await MaksogramBot.bot.send_message(chat_id, str(message), **kwargs)

    @staticmethod
    async def send_system_message(message: str, **kwargs):
        return await MaksogramBot.bot.send_message(OWNER, str(message), **kwargs)
