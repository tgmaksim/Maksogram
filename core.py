OWNER = 5128609241
support = "tgmaksim_company"
support_link = f"<a href='tg://resolve?domain={support}'>тех. поддержке</a>"
SITE = "https://tgmaksim.ru/проекты/maksogram"
subscribe = "https://t.me/+F5YW1gV3gdhjNjVi"
channel = "tgmaksim_ru"
feedback_post = 375
feedback_comment = 510
feedback_button = f"tg://resolve?domain={channel}&post={feedback_post}&comment={feedback_comment}"
feedback_link = f"<a href='{feedback_button}'>отзывы</a>"
morning = 5, 13

html = "HTML"
s1, s2 = "{}"

import os
import json
import string
import asyncio
import sys_keys
import traceback
import aiosmtplib

from aiogram import Bot
from typing import Union, Any
from database import Database
from email.header import Header
from dataclasses import dataclass
from telethon import TelegramClient
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from telethon.tl.types import StarGiftUnique
from telethon.tl.types.payments import SavedStarGifts
from telethon.tl.functions.photos import GetUserPhotosRequest
from telethon.tl.functions.payments import GetSavedStarGiftsRequest
from sys_keys import sessions_path, TOKEN, BOT_ID, USERNAME_BOT, email
from aiogram.types import LinkPreviewOptions, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile


@dataclass
class Gift:
    id: str
    unique: bool
    giver: dict[str, int]
    limited: bool
    stars: int
    slug: str


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


async def get_gifts(account_id: int, user_id: int) -> Union[dict[str, Gift], None]:
    result = {}
    saved_gifts: SavedStarGifts = (await telegram_clients[account_id](GetSavedStarGiftsRequest(peer=user_id, offset="", limit=32)))
    if saved_gifts.count > 32:
        return None
    for saved_gift in saved_gifts.gifts:
        gift = saved_gift.gift
        giver = None
        if saved_gift.from_id:
            giver_user = [user for user in saved_gifts.users if user.id == saved_gift.from_id.user_id][0]
            giver = {"user_id": giver_user.id, "name": f"{giver_user.first_name} {giver_user.last_name}".strip(),
                     "username": giver_user.username}
        if isinstance(gift, StarGiftUnique):
            result[str(gift.id)] = Gift(str(gift.id), True, giver, None, None, gift.slug)
        else:
            result[str(gift.id)] = Gift(str(gift.id), False, giver, gift.limited, gift.stars, None)
    return result


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
    if enabled_ordinary_auto_answer:
        return enabled_ordinary_auto_answer

    time_zone: int = await db.fetch_one(f"SELECT time_zone FROM settings WHERE account_id={account_id}", one_data=True)
    now = time_now() + timedelta(hours=time_zone)
    weekday = now.weekday()
    tomorrow_weekday = (weekday + 1) % 7
    timetable_auto_answers = await db.fetch_all("SELECT answer_id, start_time, end_time, weekdays FROM answering_machine WHERE "
                                                f"account_id={account_id} AND type='timetable' AND status=true")
    for answer in timetable_auto_answers:
        answer['start_time'] = answer['start_time'].replace(hour=(answer['start_time'].hour + time_zone) % 24)
        answer['end_time'] = answer['end_time'].replace(hour=(answer['end_time'].hour + time_zone) % 24)
        if answer['start_time'] < answer['end_time']:
            if answer['start_time'] <= now.time() <= answer['end_time'] and weekday in answer['weekdays']:
                return answer['answer_id']
        else:  # answer['start_time'] > answer['end_time']
            if answer['start_time'] <= now.time():  # До полуночи
                if tomorrow_weekday in answer['weekdays']:
                    return answer['answer_id']
            elif now.time() <= answer['end_time']:  # После полуночи
                if weekday in answer['weekdays']:
                    return answer['answer_id']


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


async def send_email_message(to: str, subject: str, text: str, *, subtype: str = 'plain'):
    msg = MIMEText(text, subtype, 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = email['user']
    msg['To'] = to

    smtp = aiosmtplib.SMTP(hostname=email['host'], port=25, start_tls=False)
    await smtp.connect()
    await smtp.starttls()
    await smtp.login(email['user'], email['password'])
    await smtp.send_message(msg)
    await smtp.quit()


class Variables:
    version = "2.6"
    version_string = "2.6.2 (45)"
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
