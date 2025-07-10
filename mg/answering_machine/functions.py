from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mg.client import MaksogramClient

import os
import random

from mg.config import OWNER

from typing import Optional
from . types import AutoAnswer
from mg.core.types import morning
from datetime import time, timedelta
from mg.core.database import Database
from asyncpg.exceptions import UniqueViolationError
from mg.core.functions import get_time_zone, time_now, www_path

from mg.bot.types import bot


MAX_COUNT_AUTO_ANSWERS = 10
MAX_COUNT_AUTO_ANSWER_TRIGGERS = 5
MAX_COUNT_AUTO_ANSWER_CHATS = 5
BASE_DIR_AUTO_ANSWERS = "auto_answers"
end_morning = time(morning[1], 0)


async def get_auto_answers(account_id: int) -> list[AutoAnswer]:
    """Возвращает список автоответов клиента, если status выбран, то только с определенным статусом"""

    sql = ("SELECT answer_id, status, text, entities, media, start_time, end_time, weekdays, triggers, offline, "
           f"chats, contacts, blacklist_chats FROM answering_machine WHERE account_id={account_id} ORDER BY answer_id")
    data: list[dict] = await Database.fetch_all(sql)

    sql = f"SELECT answer_id, user_id, time FROM answering_machine_triggering WHERE account_id={account_id}"
    data_triggering = await Database.fetch_all(sql)
    triggering = {}

    for answer_triggering in data_triggering:
        if triggering.get(answer_triggering['answer_id']) is None:
            triggering[answer_triggering['answer_id']] = {}

        triggering[answer_triggering['answer_id']][answer_triggering['user_id']] = answer_triggering['time']

    return AutoAnswer.list_from_json(data, triggering, await get_time_zone(account_id))


async def check_count_auto_answers(account_id: int) -> bool:
    """Считает количество автоответов у клиента и возвращает возможность добавить еще один"""

    if account_id == OWNER:
        return True

    sql = f"SELECT COUNT(*) FROM answering_machine WHERE account_id={account_id}"
    data: int = await Database.fetch_row_for_one(sql)

    return data < MAX_COUNT_AUTO_ANSWERS


async def add_auto_answer(account_id: int, text: str, entities: list[dict], media_id: Optional[str] = None, media_ext: Optional[str] = None) -> int:
    """Создает автоответ и возвращает его идентификатор"""

    answer_id = int(time_now().timestamp() * 1000000 % 100000000000)
    entities = Database.serialize(entities)
    media = None

    if media_id:
        access_hash = random.randint(10 ** 10, 10 ** 12)
        media = Database.serialize(dict(access_hash=access_hash, ext=media_ext))
        await download_auto_answer_media(account_id, answer_id, media_id, access_hash, media_ext)

    sql = "INSERT INTO answering_machine (account_id, answer_id, text, entities, media) VALUES ($1, $2, $3, $4, $5)"
    await Database.execute(sql, account_id, answer_id, text, entities, media)

    return answer_id


async def download_auto_answer_media(account_id: int, answer_id: int, media_id: str, access_hash: int, ext: str):
    """Скачивает медиа для автоответа"""

    path = get_path_auto_answer_media(account_id, answer_id, access_hash, ext)
    await bot.download(media_id, path)


def get_path_auto_answer_media(account_id: int, answer_id: int, access_hash: int, ext: str) -> str:
    """Возвращает path к скаченному медиа автоответа"""

    return www_path(get_link_auto_answer_media(account_id, answer_id, access_hash, ext))


def get_link_auto_answer_media(account_id: int, answer_id: int, access_hash: int, ext: str) -> str:
    """Возвращает ссылку на медиа автоответа"""

    return f"{BASE_DIR_AUTO_ANSWERS}/{account_id}.{answer_id}.{access_hash}.{ext}"


async def get_auto_answer(account_id: int, answer_id: int) -> Optional[AutoAnswer]:
    """Возвращает автоответ клиента"""

    sql = ("SELECT answer_id, status, text, entities, media, start_time, end_time, weekdays, triggers, offline, "
           f"chats, contacts, blacklist_chats FROM answering_machine WHERE account_id={account_id} AND answer_id={answer_id}")
    data: dict = await Database.fetch_row(sql)
    if not data:
        return None

    sql = f"SELECT user_id, time FROM answering_machine_triggering WHERE account_id={account_id} AND answer_id={answer_id}"
    data_triggering = await Database.fetch_all(sql)
    triggering = {}

    for answer_triggering in data_triggering:
        triggering[answer_triggering['user_id']] = answer_triggering['time']

    return AutoAnswer.from_json(data, triggering, await get_time_zone(account_id))


async def disable_ordinary_auto_answers(account_id: int) -> bool:
    """Выключает единственный обыкновенный автоответ без триггеров, возвращает его наличие"""

    sql = f"SELECT answer_id FROM answering_machine WHERE account_id={account_id} AND start_time IS NULL AND triggers IS NULL AND status=true"
    answer_id: int = await Database.fetch_row_for_one(sql)

    if answer_id:
        sql = f"UPDATE answering_machine SET status=false WHERE account_id={account_id} AND start_time IS NULL AND triggers IS NULL"
        await Database.execute(sql)

        await delete_auto_answer_triggering(account_id, answer_id)

    return bool(answer_id)


async def intersection_ordinary_auto_answers_by_triggers(account_id: int, answer: AutoAnswer) -> bool:
    """
    Проверяет все включенные автоответы клиента на соответствие п 2 Примечания к функции get_enabled_auto_answer:
    Включенные обыкновенные автоответы не должны иметь одинаковых триггеров

    :return: Возможность включить автоответ ``answer`` без нарушения п 2 Примечания
    """

    sql = f"SELECT triggers FROM answering_machine WHERE account_id={account_id} AND answer_id!={answer.id} AND status=true AND start_time IS NULL"
    data: list[dict[str, str]] = await Database.fetch_all_for_one(sql)

    for triggers in data:
        if intersection_triggers(list(answer.triggers.values()), list(triggers.values())):
            return True  # Триггеры равны или один из них является подстрокой другого

    return False


async def intersection_timetable_auto_answers_by_triggers(account_id: int, answer: AutoAnswer) -> bool:
    """
    Проверяет все включенные автоответы клиента на соответствие п 4 Примечания к функции get_enabled_auto_answer:
    Включенные автоответы по расписанию с пересечением по времени не должны иметь одинаковых триггеров

    :return: Возможность включить автоответ ``answer`` без нарушения п 4 Примечания
    """

    sql = (f"SELECT start_time, end_time, weekdays, triggers FROM answering_machine "
           f"WHERE account_id={account_id} AND answer_id!={answer.id} AND status=true AND start_time IS NOT NULL")
    data: list[dict] = await Database.fetch_all(sql)

    for other in data:
        if other['end_time'] is None:
            other['end_time'] = end_morning

        if not intersection_timetable_auto_answers(other['start_time'], other['end_time'], other['weekdays'],
                                                   answer.start_time, answer.end_time or end_morning, answer.weekdays):
            continue  # Автоответы не пересекаются по времени - могут иметь одинаковые триггеры

        if intersection_triggers(list(answer.triggers.values()), other['triggers']):
            return True  # Триггеры равны или один из них является подстрокой другого

    return False


def intersection_timetable_auto_answers(start_time0: time, end_time0: time, weekdays0: list[int], start_time1: time, end_time1: time, weekdays1: list[int]) -> bool:
    """Проверяет два расписания автоответа на пересечение"""

    if not set(weekdays0).intersection(weekdays1):
        return False  # Дни работы не пересекаются

    elif start_time0 < end_time0 <= start_time1 < end_time1 or \
            start_time1 < end_time1 <= start_time0 < end_time0 or \
            end_time0 <= start_time1 < end_time1 <= start_time0 or \
            end_time1 <= start_time0 < end_time0 <= start_time1:
        return False  # Расписания не пересекаются

    return True  # Существует хотя бы одна такая минута на неделе, когда расписание автоответов пересекается


async def intersection_auto_answers_by_timetable(account_id: int, answer: AutoAnswer) -> bool:
    """
    Проверяет все включенные автоответы клиента на соответствие п 3 Примечания к функции get_enabled_auto_answer:
    Включенные автоответы по расписанию без триггеров не должны пересекаться по времени

    :return: Возможность включить автоответ ``answer`` без нарушения п 3 Примечания
    """

    sql = ("SELECT start_time, end_time FROM answering_machine "
           f"WHERE account_id={account_id} AND answer_id!={answer.id} AND status=true AND start_time IS NOT NULL AND triggers IS NULL")
    data: list[dict] = await Database.fetch_all(sql)

    for other in data:
        if other['end_time'] is None:
            other['end_time'] = end_morning

        if intersection_timetable_auto_answers(other['start_time'], other['end_time'], other['weekdays'],
                                               answer.start_time, answer.end_time or end_morning, answer.weekdays):
            return True

    return False


async def set_status_auto_answer(account_id: int, answer_id: int, status: bool):
    """Включает/выключает автоответ у клиента"""

    sql = f"UPDATE answering_machine SET status=$1 WHERE account_id={account_id} AND answer_id={answer_id}"
    await Database.execute(sql, status)

    await delete_auto_answer_triggering(account_id, answer_id)


async def edit_auto_answer(account_id: int, answer_id: int, text: str, entities: list[dict], media_id: Optional[str] = None, media_ext: Optional[str] = None) -> bool:
    """
    Изменяет текст и медиа автоответа

    :return: True, если автоответ существует, иначе False
    """

    answer = await get_auto_answer(account_id, answer_id)
    if answer is None:
        return False

    if answer.media:
        delete_auto_answer_media(account_id, answer_id, answer.media.access_hash, answer.media.ext)  # Удаляем прошлое медиа

    entities = Database.serialize(entities)
    media = None

    if media_id:
        access_hash = random.randint(10 ** 10, 10 ** 12)
        media = Database.serialize(dict(access_hash=access_hash, ext=media_ext))
        await download_auto_answer_media(account_id, answer_id, media_id, access_hash, media_ext)

    sql = f"UPDATE answering_machine SET text=$1, entities=$2, media=$3 WHERE account_id={account_id} AND answer_id={answer_id}"
    await Database.execute(sql, text, entities, media)

    return True


def delete_auto_answer_media(account_id: int, answer_id: int, access_hash: int, ext: str):
    """Удаляет медиа автоответа"""

    os.remove(get_path_auto_answer_media(account_id, answer_id, access_hash, ext))


async def delete_auto_answer(account_id: int, answer_id: int):
    """Удаляет автоответ и сохраненное медиа (если есть)"""

    answer = await get_auto_answer(account_id, answer_id)
    if not answer:
        return

    if answer.media:
        delete_auto_answer_media(account_id, answer_id, answer.media.access_hash, answer.media.ext)

    sql = f"DELETE FROM answering_machine WHERE account_id={account_id} AND answer_id={answer_id}"
    await Database.execute(sql)


async def edit_auto_answer_timetable(account_id: int, answer_id: int, start_time: time, end_time: Optional[time]):
    """Создает расписание к автоответу на всю неделю"""

    weekdays = Database.serialize(list(range(7)))
    sql = (f"UPDATE answering_machine SET start_time=$1, end_time=$2, weekdays=$3 "
           f"WHERE account_id={account_id} AND answer_id={answer_id}")
    await Database.execute(sql, start_time, end_time, weekdays)


async def edit_auto_answer_weekdays(account_id: int, answer_id: int, weekdays: list[int]):
    """Изменяет дни работы автоответа"""

    sql = f"UPDATE answering_machine SET weekdays=$1 WHERE account_id={account_id} AND answer_id={answer_id}"
    await Database.execute(sql, Database.serialize(weekdays))


async def delete_auto_answer_timetable(account_id: int, answer_id: int):
    """Удаляет расписание работы автоответа"""

    sql = (f"UPDATE answering_machine SET start_time=NULL, end_time=NULL, weekdays=NULL "
           f"WHERE account_id={account_id} AND answer_id={answer_id}")
    await Database.execute(sql)


async def check_count_auto_answer_triggers(account_id: int, answer_id: int) -> bool:
    """Считает количество триггеров в автоответе и возвращает возможность добавить еще один"""

    if account_id == OWNER:
        return True

    sql = f"SELECT COUNT(*) FROM jsonb_object_keys((SELECT triggers FROM answering_machine WHERE account_id={account_id} AND answer_id={answer_id}))"
    data: int = await Database.fetch_row_for_one(sql)

    return data < MAX_COUNT_AUTO_ANSWER_TRIGGERS


def intersection_triggers(triggers0: list[str], triggers1: list[str]) -> bool:
    """Проверяет триггеры на пересечение"""

    for trigger0 in triggers0:
        for trigger1 in triggers1:
            if trigger0 == trigger1 or min(trigger0, trigger1, key=len) in max(trigger0, trigger1, key=len):
                return True  # Триггеры равны или один из них является подстрокой другого

    return False


async def add_auto_answer_trigger(account_id: int, answer_id: int, trigger: str):
    """Добавляет триггер в список триггеров автоответа"""

    trigger_id = int(time_now().timestamp() * 1000000 % 100000000000)

    sql = f"UPDATE answering_machine SET triggers=triggers || $1 WHERE account_id={account_id} AND answer_id={answer_id}"
    await Database.execute(sql, Database.serialize({str(trigger_id): trigger}))


async def delete_auto_answer_trigger(account_id: int, answer_id: int, trigger_id: int):
    """Удаляет триггер из списка триггеров автоответа"""

    sql = f"UPDATE answering_machine SET triggers=triggers - '{trigger_id}' WHERE account_id={account_id} AND answer_id={answer_id}"
    await Database.execute(sql)


async def set_auto_answer_settings(account_id: int, answer_id: int, function: str, command: Optional[bool]):
    """Изменяет настройку автоответа"""

    sql = f"UPDATE answering_machine SET {function}=$1 WHERE account_id={account_id} AND answer_id={answer_id}"
    await Database.execute(sql, command)


async def check_count_auto_answer_chats(account_id: int, answer_id: int) -> bool:
    """Считает количество чатов в исключениях автоответа и возвращает возможность добавить еще один"""

    sql = f"SELECT COUNT(*) FROM jsonb_object_keys((SELECT chats FROM answering_machine WHERE account_id={account_id} AND answer_id={answer_id}))"
    data: int = await Database.fetch_row_for_one(sql)

    return data < MAX_COUNT_AUTO_ANSWER_CHATS


async def add_auto_answer_chat(account_id: int, answer_id: int, chat_id: int, chat_name: str):
    """Добавляет чат в исключения автоответа"""

    chat = Database.serialize({str(chat_id): chat_name})
    sql = f"UPDATE answering_machine SET chats=chats || $1 WHERE account_id={account_id} AND answer_id={answer_id}"
    await Database.execute(sql, chat)


async def delete_auto_answer_chat(account_id: int, answer_id: int, chat_id: int):
    """Удаляет чат из исключений автоответа"""

    sql = f"UPDATE answering_machine SET chats=chats - '{chat_id}' WHERE account_id={account_id} AND answer_id={answer_id}"
    await Database.execute(sql)


async def update_auto_answer_triggering(account_id: int, answer_id: int, chat_id: int):
    """Обновляет срабатывание автоответа для чата"""

    sql = "INSERT INTO answering_machine_triggering (account_id, answer_id, user_id, time) VALUES ($1, $2, $3, now())"
    try:
        await Database.execute(sql, account_id, answer_id, chat_id)
    except UniqueViolationError:  # Чат уже есть
        sql = f"UPDATE answering_machine_triggering SET time=now() WHERE account_id={account_id} AND answer_id={answer_id} AND user_id={chat_id}"
        await Database.execute(sql)


async def delete_auto_answer_triggering(account_id: int, answer_id: int):
    """Удаляет все данные о срабатывании автоответа"""

    sql = f"DELETE FROM answering_machine_triggering WHERE account_id={account_id} AND answer_id={answer_id}"
    await Database.execute(sql)


async def get_enabled_auto_answer(maksogram_client: 'MaksogramClient', text: str) -> Optional[AutoAnswer]:
    """
    Возвращает активный автоответ клиента

    Примечание:
        * Включенный обыкновенный автоответ без триггеров может быть только один

        * Включенные обыкновенные автоответы не должны иметь одинаковых триггеров

        * Включенные автоответы по расписанию без триггеров не должны пересекаться по времени

        * Включенные автоответы по расписанию с пересечением по времени не должны иметь одинаковых триггеров

        * Если расписание автоответа пересекает полночь по клиентскому часовому поясу, то день недели считает на начало работы

    Главенство автоответов (от приоритетного):
        Включенный автоответ по расписанию с триггерами

        Включенный автоответ по расписанию без триггеров

        Включенный обыкновенный автоответ с триггерами

        Включенный обыкновенный автоответ без триггеров
    """

    answers = await get_auto_answers(maksogram_client.id)

    time_zone = await maksogram_client.get_time_zone()
    now = time_now(time_zone)
    awake_time = maksogram_client.awake_time + timedelta(hours=time_zone)

    awake = False
    if awake_time.date() == now.date() or now.time() >= end_morning:
        awake = True

    ordinary_auto_answers: list[AutoAnswer] = []  # Все включенные обыкновенные автоответы
    timetable_auto_answers: list[AutoAnswer] = []  # Все включенные автоответы по расписанию, которые работают в данное время

    for answer in answers:
        if not answer.status:
            continue
        if not answer.start_time:
            ordinary_auto_answers.append(answer)
            continue

        if answer.end_time is None:
            if awake is True:
                continue  # Автоответ "до пробуждения" уже не работает
        else:
            start_time = answer.start_time.replace((answer.start_time.hour + answer.time_zone) % 24)
            end_time = answer.end_time.replace((answer.end_time.hour + answer.time_zone) % 24)

            if start_time < end_time:
                if not (start_time <= now.time() < end_time and now.weekday() in answer.weekdays):
                    continue  # Время не подходит под расписание автоответа
            else:  # end_time < start_time
                if now.time() < time(0, 0):  # До полуночи
                    if not (now.time() >= start_time and now.weekday() in answer.weekdays):
                        continue  # Время не подходит под расписание автоответа
                else:  # После полуночи или полночь
                    if not (now.time() < end_time and (now.weekday() - 1) % 7 in answer.weekdays):  # Учитываем день недели вчерашнего дня
                        continue  # Время не подходит под расписание автоответа

        # Автоответ работает в данное время и день недели
        timetable_auto_answers.append(answer)

    # Сначала автоответы с триггерами от наименьшего по длине, потом автоответ без триггеров
    timetable_auto_answers.sort(key=lambda a: 0 if not a.triggers else len(a.triggers), reverse=True)

    for answer in timetable_auto_answers:
        if answer.triggers:
            for trigger in answer.triggers.values():
                if trigger in text:
                    return answer  # Включенный автоответ по расписанию с триггерами

        else:
            return answer  # Включенный автоответ по расписанию без триггеров

    for answer in ordinary_auto_answers:
        if answer.triggers:
            for trigger in answer.triggers.values():
                if trigger in text:
                    return answer

        else:
            return answer
