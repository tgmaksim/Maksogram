import os
import random

from mg.config import OWNER

from typing import Optional
from mg.core.database import Database
from mg.core.functions import time_now, www_path
from asyncpg.exceptions import UniqueViolationError

from mg.bot.types import bot
from . types import SpeedAnswer


MAX_COUNT_SPEED_ANSWERS = 5
BASE_DIR_SPEED_ANSWERS = "speed_answers"  # www_path


async def get_speed_answers(account_id: int) -> list[SpeedAnswer]:
    """Возвращает быстрые ответы клиента, отсортированные по неубыванию длины триггера"""

    sql = f"SELECT answer_id, trigger, text, entities, media FROM speed_answers WHERE account_id={account_id}"
    data: list[dict] = await Database.fetch_all(sql)

    answers = SpeedAnswer.list_from_json(data)

    return sorted(answers, key=lambda answer: len(answer.trigger))  # Сортировка по неубыванию длины триггера


async def check_count_speed_answers(account_id: int) -> bool:
    """Проверяет, можно ли добавить еще один быстрый ответ клиенту"""

    if account_id == OWNER:
        return True

    sql = f"SELECT COUNT(*) FROM speed_answers WHERE account_id={account_id}"
    data: int = await Database.fetch_row_for_one(sql)

    return data < MAX_COUNT_SPEED_ANSWERS


async def check_unique_trigger(account_id: int, trigger: str) -> bool:
    """Проверяет уникальность триггера в быстрых ответах"""

    sql = f"SELECT true FROM speed_answers WHERE account_id={account_id} AND trigger=$1"
    data: Optional[bool] = await Database.fetch_row_for_one(sql, trigger)

    return not data


def get_path_speed_answer_media(account_id: int, answer_id: int, access_hash: int, ext: str) -> str:
    """Возвращает path к скаченному медиа быстрого ответа"""

    return www_path(get_link_speed_answer_media(account_id, answer_id, access_hash, ext))


def get_link_speed_answer_media(account_id: int, answer_id: int, access_hash: int, ext: str) -> str:
    """Возвращает ссылку на медиа быстрого ответа"""

    return f"{BASE_DIR_SPEED_ANSWERS}/{account_id}.{answer_id}.{access_hash}.{ext}"


async def download_speed_answer_media(account_id: int, answer_id: int, media_id: str, access_hash: int, ext: str):
    """Скачивает медиа для быстрого ответа"""

    path = get_path_speed_answer_media(account_id, answer_id, access_hash, ext)
    await bot.download(media_id, path)


async def add_speed_answer(account_id: int, trigger: str, text: str, entities: list[dict], media_id: Optional[str], media_ext: Optional[str]) -> Optional[int]:
    """
    Сохраняет медиа и создает новый быстрый ответ для клиента с параметрами

    :return: answer_id, если быстрый ответ создан успешно, иначе None (если для клиента уже есть быстрый ответ с таким trigger)
    """

    answer_id = int(time_now().timestamp() * 1000000 % 100000000000)
    entities = Database.serialize(entities)
    media = None

    if media_id:
        access_hash = random.randint(10**10, 10**12)
        media = Database.serialize(dict(access_hash=access_hash, ext=media_ext))
        await download_speed_answer_media(account_id, answer_id, media_id, access_hash, media_ext)

    sql = "INSERT INTO speed_answers (account_id, answer_id, trigger, text, entities, media) VALUES ($1, $2, $3, $4, $5, $6)"
    try:
        await Database.execute(sql, account_id, answer_id, trigger, text, entities, media)
    except UniqueViolationError:
        return None  # Быстрый ответ с таким trigger у клиента уже есть

    return answer_id


async def get_speed_answer(account_id: int, answer_id: int) -> Optional[SpeedAnswer]:
    """
    Возвращает быстрый ответ у клиента по идентификатору

    :param account_id: клиент
    :param answer_id: идентификатор быстрого ответа
    :return: None, если быстрый ответ не найден, иначе SpeedAnswer
    """

    sql = f"SELECT answer_id, trigger, text, entities, media FROM speed_answers WHERE account_id={account_id} AND answer_id={answer_id}"
    data: Optional[dict] = await Database.fetch_row(sql)

    if data is None:
        return data

    return SpeedAnswer.from_json(data)


def delete_speed_answer_media(account_id: int, answer_id: int, access_hash: int, ext: str):
    """Удаляет медиа быстрого ответа"""

    os.remove(get_path_speed_answer_media(account_id, answer_id, access_hash, ext))


async def edit_speed_answer(account_id: int, answer_id: int, text: str, entities: list[dict], media_id: Optional[str], media_ext: Optional[str]) -> bool:
    """
    Изменяет текст и медиа быстрого ответа

    :return: True, если быстрый ответ успешно изменен, иначе False (быстрый ответ не найден)
    """

    answer = await get_speed_answer(account_id, answer_id)
    if answer is None:
        return False

    if answer.media:
        delete_speed_answer_media(account_id, answer_id, answer.media.access_hash, answer.media.ext)  # Удаляем прошлое медиа

    entities = Database.serialize(entities)
    media = None

    if media_id:
        access_hash = random.randint(10**10, 10**12)
        media = Database.serialize(dict(access_hash=access_hash, ext=media_ext))
        await download_speed_answer_media(account_id, answer_id, media_id, access_hash, media_ext)

    sql = f"UPDATE speed_answers SET text=$1, entities=$2, media=$3 WHERE account_id={account_id} AND answer_id={answer_id}"
    await Database.execute(sql, text, entities, media)

    return True


async def delete_speed_answer(account_id: int, answer_id: int):
    """Удаляет быстрый ответ и сохраненное медиа (если есть)"""

    answer = await get_speed_answer(account_id, answer_id)
    if not answer:
        return

    if answer.media:
        delete_speed_answer_media(account_id, answer_id, answer.media.access_hash, answer.media.ext)

    sql = f"DELETE FROM speed_answers WHERE account_id={account_id} AND answer_id={answer_id}"
    await Database.execute(sql)


async def get_speed_answer_by_text(account_id: int, text: str) -> Optional[SpeedAnswer]:
    """Ищет быстрый ответ, триггер которого входит в текст (без учета регистра)"""

    sql = f"SELECT answer_id, trigger, text, entities, media FROM speed_answers WHERE account_id={account_id} AND trigger=$1"
    data: Optional[dict] = await Database.fetch_row(sql, text)
    if not data:
        return None

    return SpeedAnswer.from_json(data)
