from mg.config import OWNER

from datetime import datetime
from typing import Optional, Union
from mg.core.database import Database
from asyncpg.exceptions import UniqueViolationError

from . types import StatusUserSettings


MAX_COUNT_STATUS_USERS = 3


async def get_users_settings(account_id: int) -> list[StatusUserSettings]:
    """Возвращает всех пользователей, добавленных в "Друг в сети" клиента"""

    sql = f"SELECT user_id, name, online, offline, reading, awake, statistics, last_message FROM status_users WHERE account_id={account_id}"
    data: list[dict] = await Database.fetch_all(sql)

    users = StatusUserSettings.list_from_json(data)

    return sorted(users, key=lambda user: len(user.name))


async def check_count_status_users(account_id: int) -> bool:
    """Считает количество добавленных пользователей в "Друг в сети" клиента и проверяет возможность добавить еще одного"""

    if account_id == OWNER:
        return True

    sql = f"SELECT COUNT(*) FROM status_users WHERE account_id={account_id}"
    data: int = await Database.fetch_row_for_one(sql)

    return data < MAX_COUNT_STATUS_USERS


async def add_status_user(account_id: int, user_id: int, name: str):
    """Добавляет пользователя в "Друг в сети" клиента"""

    sql = "INSERT INTO status_users (account_id, user_id, name, online, offline, reading, awake, statistics, last_message) VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9)"
    try:
        await Database.execute(sql, account_id, user_id, name, False, False, False, None, False, None)
    except UniqueViolationError:
        pass


async def get_user_settings(account_id: int, user_id: int) -> Optional[StatusUserSettings]:
    """Возвращает настройки пользователя в "Друг в сети" по идентификатору"""

    sql = f"SELECT user_id, name, online, offline, reading, awake, statistics, last_message FROM status_users WHERE account_id={account_id} AND user_id={user_id}"
    data: dict = await Database.fetch_row(sql)
    if not data:
        return None

    return StatusUserSettings.from_json(data)


async def update_status_user(account_id: int, user_id: int, field: str, value: Union[bool, Optional[datetime]]):
    """Включает/выключает функцию у пользователя"""

    sql = f"UPDATE status_users SET {field}=$1 WHERE account_id={account_id} AND user_id={user_id}"
    await Database.execute(sql, value)


async def delete_status_user(account_id: int, user_id: int):
    """Удаляет пользователя из "Друг в сети" и очищает собранную статистику"""

    sql = (f"DELETE FROM statistics_status_users WHERE account_id={account_id} AND user_id={user_id};"
           f"DELETE FROM statistics_time_reading WHERE account_id={account_id} AND user_id={user_id};"
           f"DELETE FROM status_users WHERE account_id={account_id} AND user_id={user_id}")
    await Database.execute(sql)


async def update_statistics(account_id: int, user_id: int, status: bool):
    """Добавляет статистические данные для пользователя"""

    if status:  # Удаляем неполные пары данных и добавляем новую пару
        sql = (f"DELETE FROM statistics_status_users WHERE account_id={account_id} AND user_id={user_id} AND offline_time IS NULL",
               f"INSERT INTO statistics_status_users (account_id, user_id, online_time, offline_time) VALUES ({account_id}, {user_id}, now(), NULL)")
    else:  # Завершаем пару данных
        sql = (f"UPDATE statistics_status_users SET offline_time=now() WHERE account_id={account_id} AND user_id={user_id}",)

    for s in sql:
        await Database.execute(s)


async def update_last_message(account_id: int, user_id: int):
    """Обновляет время последнего отправленного сообщения для будущего подсчета времени ответа"""

    sql = f"UPDATE status_users SET last_message=now() WHERE account_id={account_id} AND user_id={user_id}"
    await Database.execute(sql)


async def update_reading_statistics(account_id: int, user_id: int):
    """Добавляет данные о времени прочтения сообщения"""

    sql = ("INSERT INTO statistics_time_reading (account_id, user_id, time) (SELECT account_id, user_id, now() - last_message "
           f"FROM status_users WHERE account_id={account_id} AND user_id={user_id} AND last_message IS NOT NULL)")
    await Database.execute(sql)

    sql = f"UPDATE status_users SET last_message=NULL WHERE account_id={account_id} AND user_id={user_id}"
    await Database.execute(sql)


async def get_my_users_settings(account_id: int) -> list[StatusUserSettings]:
    """
    Когда пользователь в "Друг в сети" является клиентом Maksogram, он обрабатывается отдельно

    :param account_id: клиент
    :return: список StatusUserSettings с user_id=account_id
    """

    sql = f"SELECT account_id AS user_id, name, online, offline, reading, awake, statistics, last_message FROM status_users WHERE user_id={account_id}"
    data: list[dict] = await Database.fetch_all(sql)

    return StatusUserSettings.list_from_json(data)
