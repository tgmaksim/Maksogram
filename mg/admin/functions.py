from mg.config import OWNER, NETANGELS_API_KEY, MAKSOGRAM_PROCESS_ID, VIRTUALHOST_ID

from aiohttp import ClientSession
from datetime import datetime, timedelta

from mg.bot.types import Blocked
from mg.core.database import Database
from mg.core.functions import time_now


GATEWAY_TOKEN_URL = "https://panel.netangels.ru/api/gateway/token/"
NETANGELS_API_URL = "https://api-ms.netangels.ru/api/v1/hosting"


async def reload_server():
    """Перезагружает полностью весь сервер: от фоновых процессов до сайта"""

    print("Перезапуск сервера")

    async with ClientSession() as sessions:
        async with sessions.post(GATEWAY_TOKEN_URL, data={'api_key': NETANGELS_API_KEY}) as response:
            token = (await response.json())['token']
            # С помощью полученного токена перезапускает полностью сервер
            await sessions.post(f"{NETANGELS_API_URL}/virtualhosts/{VIRTUALHOST_ID}/restart", headers={'Authorization': f'Bearer {token}'})


async def reload_maksogram(logging=True):
    """Перезагружает фоновый процесс Maksogram"""

    if logging:
        print("Перезапуск Maksogram")

    async with ClientSession() as session:
        async with session.post(GATEWAY_TOKEN_URL, data={'api_key': NETANGELS_API_KEY}) as response:
            token = (await response.json())['token']
            # С помощью полученного токена перезапускает фоновый процесс Maksogram
            await session.post(f"{NETANGELS_API_URL}/background-processes/{MAKSOGRAM_PROCESS_ID}/restart", headers={'Authorization': f'Bearer {token}'})


async def stop_maksogram():
    """Останавливает фоновый процесс Maksogram"""

    print("Остановка Maksogram")

    async with ClientSession() as session:
        async with session.post(GATEWAY_TOKEN_URL, data={'api_key': NETANGELS_API_KEY}) as response:
            token = (await response.json())['token']
            # С помощью токена останавливается фоновый процесс Maksogram
            await session.post(f"{NETANGELS_API_URL}/background-processes/{MAKSOGRAM_PROCESS_ID}/stop", headers={'Authorization': f'Bearer {token}'})


async def count_users() -> int:
    """Считает количество пользователей, которые когда-либо запустили Maksogram"""

    sql = "SELECT COUNT(*) FROM users"
    data: int = await Database.fetch_row_for_one(sql)

    return data


async def count_accounts() -> int:
    """Считает количество клиентов (зарегистрированных пользователей) Maksogram"""

    sql = "SELECT COUNT(*) FROM accounts"
    data: int = await Database.fetch_row_for_one(sql)

    return data


async def count_working_accounts() -> int:
    """Считает количество активных (работающих) клиентов (зарегистрированных пользователей)"""

    sql = "SELECT COUNT(*) FROM settings WHERE is_started=true"
    data: int = await Database.fetch_row_for_one(sql)

    return data


async def get_working_time() -> timedelta:
    """Считает количество времени со дня регистрации аккаунта админа"""

    sql = f"SELECT registration_date FROM accounts WHERE account_id={OWNER}"
    date: datetime = await Database.fetch_row_for_one(sql)

    return time_now() - date


async def block_user(user_id: int):
    """Добавляет пользователя в список заблокированных"""

    Blocked.users.append(user_id)

    sql = "INSERT INTO blocked_users (user_id, blocking_time) VALUES($1, now())"
    await Database.execute(sql, user_id)