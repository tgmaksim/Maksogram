from mg.config import OWNER

from typing import Literal
from datetime import datetime
from mg.core.database import Database
from asyncpg.exceptions import UniqueViolationError

from mg.client import MaksogramClient


MAX_ADDED_CHATS = 3


async def update_referral(account_id: int, friend_id: int):
    """
    Добавляет нового друга клиенту

    :param account_id: клиент (владелец реферальной ссылки)
    :param friend_id: друг (новый пользователей)
    """

    try:
        sql = f"INSERT INTO referrals (account_id, friend_id) VALUES ({account_id}, {friend_id})"
        await Database.execute(sql)
    except UniqueViolationError:  # Друг ранее уже переходил по чьей-то реферальной ссылке
        sql = f"UPDATE referrals SET account_id={account_id}, friend_id={friend_id}"
        await Database.execute(sql)


def get_registration_date_by_id(account_id: int) -> str:
    """Рассчитывает примерную дату регистрации аккаунта в Telegram по идентификатору клиента"""

    main_bits = account_id // (10 ** 8)  # Пара первых цифр идентификатора (или одно число, если всего 9 цифр)

    if main_bits == 0: return "до 2016 года"
    if 0 < main_bits <= 5: return "2017 года"
    if 5 < main_bits < 10: return "2018 года"
    if 10 <= main_bits < 15: return "2019 года"
    if 15 <= main_bits <= 18: return "2020 года"
    if 18 < main_bits <= 22: return "2021 года"
    if 22 < main_bits < 60: return "2022 года"
    if 60 <= main_bits < 70: return "2023 года"
    if 70 <= main_bits < 80: return "2024 года"

    return "2025 года"


async def get_registration_date(account_id: int) -> datetime:
    """Возвращает дату регистрации клиента в Maksogram"""

    sql = f"SELECT registration_date FROM accounts WHERE account_id={account_id}"
    date: datetime = await Database.fetch_row_for_one(sql)

    return date


async def count_messages(account_id: int) -> tuple[int, int]:
    """
    Считает количество сообщений в личных чатах клиента и количество сохраненных сообщений

    :param account_id: клиент
    :return: всего сообщений, сохраненных сообщений
    """

    table_name = MaksogramClient.format_table_name(account_id)
    sql = f"SELECT MAX(message_id) as count_messages, MAX(saved_message_id) as count_saved_messages FROM {table_name}"
    data: dict = await Database.fetch_row(sql)

    return data['count_messages'], data['count_saved_messages']


async def set_city(account_id: int, city: str):
    """Меняет название города у клиента в базе данных"""

    sql = f"UPDATE settings SET city=$1 WHERE account_id={account_id}"
    await Database.execute(sql, city)


async def set_time_zone(account_id: int, time_zone: int):
    """Меняет часовой пояс у клиента в базе данных"""

    sql = f"UPDATE settings SET time_zone={time_zone} WHERE account_id={account_id}"
    await Database.execute(sql)


async def set_gender(account_id: int, gender: bool):
    """Меняет пол клиента в базе данных (True - мужчина, False - женщина, обнулить пол нельзя!)"""

    sql = f"UPDATE settings SET gender=$1 WHERE account_id={account_id}"
    await Database.execute(sql, gender)


async def set_saving_messages(account_id: int, saving_messages: bool):
    """Включает/выключает Сохранение сообщений у клиента"""

    sql = f"UPDATE settings SET saving_messages=$1 WHERE account_id={account_id}"
    await Database.execute(sql, saving_messages)


async def set_notify_changes(account_id: int, notify_changes: bool):
    """Включает/выключает Уведомления об изменении сообщений у клиента"""

    sql = f"UPDATE settings SET notify_changes=$1 WHERE account_id={account_id}"
    await Database.execute(sql, notify_changes)


async def check_count_added_chats(account_id: int) -> bool:
    """Проверяет количество добавленных чатов у клиента возвращает возможность добавить еще один"""

    if account_id == OWNER:
        return True  # Неограниченное количество для админа

    sql = f"SELECT COUNT(*) FROM jsonb_object_keys((SELECT added_chats FROM settings WHERE account_id={account_id}))"
    data: int = await Database.fetch_row_for_one(sql)

    return data < MAX_ADDED_CHATS


async def add_chat(account_id: int, chat_id: int, chat_name: str):
    """Добавляет новый чат в рабочие чаты клиента"""

    new_chat = Database.serialize({str(chat_id): chat_name})
    sql = f"UPDATE settings SET added_chats = added_chats || $1 WHERE account_id={account_id}"
    await Database.execute(sql, new_chat)


async def remove_chat(account_id: int, chat_id: int, chat_name: str):
    """Удаляет личный чат из рабочих чатов клиента"""

    new_chat = Database.serialize({str(chat_id): chat_name})
    sql = f"UPDATE settings SET removed_chats = removed_chats || $1 WHERE account_id={account_id}"
    await Database.execute(sql, new_chat)


async def delete_chat(account_id: int, type_chat: Literal["added", "removed"], chat_id: int):
    """Удаляет добавленный или добавляет обратно удаленный рабочий чат Maksogram"""

    sql = f"UPDATE settings SET {type_chat}_chats = {type_chat}_chats - '{chat_id}' WHERE account_id={account_id}"
    await Database.execute(sql)
