import aiohttp

from mg.config import CRYPTO_API_KEY

from math import log10
from . types import Remind
from datetime import datetime
from mg.core.database import Database
from telethon.tl.patched import Message
from asyncpg.exceptions import UniqueViolationError


async def enabled_module(account_id: int, module_name: str) -> bool:
    """Проверяет статус модуля у клиента"""

    sql = f"SELECT {module_name} FROM modules WHERE account_id={account_id}"
    data: bool = await Database.fetch_row_for_one(sql)

    return data


async def set_status_module(account_id: int, module: str, status: bool):
    """Включает/выключает модуль у клиента"""

    sql = f"UPDATE modules SET {module}=$1 WHERE account_id={account_id}"
    await Database.execute(sql, status)


async def set_main_currency(account_id: int, main_currency: str):
    """Устанавливает валюту по умолчанию у клиента"""

    sql = f"UPDATE modules SET main_currency='{main_currency}' WHERE account_id={account_id}"
    await Database.execute(sql)


async def set_my_currencies(account_id: int, my_currencies: str):
    """Изменяет список валют для уведомления по утрам"""

    sql = f"UPDATE modules SET my_currencies=$1 WHERE account_id={account_id}"
    await Database.execute(sql, my_currencies)


async def get_main_currency(account_id: int) -> str:
    """Возвращает валюту по умолчанию"""

    sql = f"SELECT main_currency FROM modules WHERE account_id={account_id}"
    data: str = await Database.fetch_row_for_one(sql)

    return data


async def get_my_currencies(account_id: int) -> list[str]:
    """Возвращает список валют для уведомления по утрам"""

    sql = f"SELECT my_currencies FROM modules WHERE account_id={account_id}"
    data: list[str] = await Database.fetch_row_for_one(sql)

    return data


async def get_city(account_id: int) -> str:
    """Возвращает город, выбранный в настройках клиента"""

    sql = f"SELECT city FROM settings WHERE account_id={account_id}"
    data: str = await Database.fetch_row_for_one(sql)

    return data


async def add_remind(account_id: int, message: Message, time: datetime, chat_name: str) -> bool:
    """Создает напоминание для клиента на сообщение, если такое уже есть, возвращает False"""

    sql = "INSERT INTO reminds (account_id, chat_id, message_id, time, chat_name) VALUES ($1, $2, $3, $4, $5)"

    try:
        await Database.execute(sql, account_id, message.chat_id, message.id, time, chat_name)
    except UniqueViolationError:  # Напоминание с такими параметрами уже существует
        return False

    return True


async def get_reminds(account_id: int) -> list[Remind]:
    """Возвращает список напоминаний у клиента, которые уже должны быть объявлены"""

    sql = f"SELECT chat_id, message_id, time, chat_name FROM reminds WHERE account_id={account_id} AND (now() - time) >= INTERVAL '3 seconds'"
    data: list[dict] = await Database.fetch_all(sql)

    return Remind.list_from_json(data)


async def delete_remind(account_id: int, chat_id: int, message_id: int, time: datetime):
    """Удаляет напоминание на сообщение у клиента"""

    sql = f"DELETE FROM reminds WHERE account_id={account_id} AND chat_id={chat_id} AND message_id={message_id} AND time='{time}'"
    await Database.execute(sql)


async def convert_currencies(value: float, currency0: str, currency1: str) -> float:
    """
    Переводит суммы одной валюты в другую

    :param value: сумма
    :param currency0: исходная валюта
    :param currency1: необходимая валюта
    :return: сумма в необходимой валюте
    """

    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {"X-CMC_PRO_API_KEY": CRYPTO_API_KEY}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params={"symbol": "USDT", "convert": currency0}) as response:
            data = await response.json()
            currency0 = data['data']["USDT"]['quote'][currency0]['price']

        async with session.get(url, headers=headers, params={"symbol": "USDT", "convert": currency1}) as response:
            data = await response.json()
            currency1 = data['data']["USDT"]['quote'][currency1]['price']

        res = value * (currency1 / currency0)
        if res < 1:
            return round(res, -round(log10(res))+2)

        return round(res, max(0, 5 - round(log10(res))))
