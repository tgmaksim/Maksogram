import os
import aiosqlite

from aiogram import Bot
from typing import Union
from dotenv import load_dotenv


dotenv_path = os.path.join(os.path.dirname(__file__), '.env')  # путь к переменным окружения (debug)
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)  # загрузка переменных


def resources_path(path: str):
    return os.path.join(os.path.dirname(__file__), "resources", path)


async def execute(sql: str, params: tuple = None) -> tuple[tuple[Union[str, int]]]:
    async with aiosqlite.connect(resources_path("db.sqlite3")) as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, params)
            result = await cur.fetchall()
        await conn.commit()
    return result


class Data:
    version = "2.1"
    BOT_API_KEY = os.environ['SYSTEM_BOT_API_KEY']
    APPLICATION_ID = int(os.environ['APPLICATION_ID'])
    APPLICATION_HASH = os.environ['APPLICATION_HASH']


class SystemBot:
    id = 7025564473
    username = "SystemMaksimBot"
    bot = Bot(Data.BOT_API_KEY)

    @staticmethod
    async def send_system_message(chat_id: int, text: str, **kwargs):
        await SystemBot.bot.send_message(chat_id, text, **kwargs)
