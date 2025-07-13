from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . maksogram_client import MaksogramClient

from datetime import datetime
from typing import Union, Optional
from mg.core.database import Database
from mg.core.functions import time_now, get_subscription

from telethon.tl.patched import Message

from . functions import (
    media_id,
    message_hash,
    SavedMessage,
    set_is_started,
)

MAX_COUNT_SAVED_MESSAGES_PER_DAY = 500
MAX_COUNT_SAVED_MESSAGES_PER_DAY_FOR_PREMIUM = 5000

MAX_COUNT_USAGE_AUDIO_TRANSCRIPTION = 1
MAX_COUNT_USAGE_AUDIO_TRANSCRIPTION_FRO_PREMIUM = 10

MAX_COUNT_USAGE_ROUND_VIDEO = 1
MAX_COUNT_USAGE_ROUND_VIDEO_FRO_PREMIUM = 5

MAX_COUNT_USAGE_REMINDER = 1
MAX_COUNT_USAGE_REMINDER_FRO_PREMIUM = 10


class DatabaseMethods:
    async def create_table(self: 'MaksogramClient'):
        """Создает таблицу в базе данных для хранения сохраненных сообщений"""

        sql = f"CREATE TABLE IF NOT EXISTS {self.table_name} (chat_id BIGINT NOT NULL, message_id INTEGER NOT NULL, " \
              "saved_message_id INTEGER NOT NULL, hash CHARACTER VARYING(128) NOT NULL, media BIGINT, time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        await Database.execute(sql)

    async def update_initial_data(self: 'MaksogramClient'):
        """Заполняет данные при инициализации из базы данных"""

        sql = f"SELECT name, my_messages, message_changes, awake_time FROM accounts WHERE account_id={self.id}"
        data: dict[str, Union[str, int, datetime]] = await Database.fetch_row(sql)

        sql = f"SELECT user_id FROM status_users WHERE account_id={self.id}"
        users: list[int] = await Database.fetch_all_for_one(sql)

        await self.set_init_data(data['name'], data['my_messages'], data['message_changes'], users, data['awake_time'])

    async def update_channel_ids(self: 'MaksogramClient', *, my_messages: Optional[int] = None, message_changes: Optional[int] = None):
        """Изменяет идентификаторы my_messages и message_changes в базе данных"""

        if my_messages:
            sql = f"UPDATE accounts SET my_messages={my_messages} WHERE account_id={self.id}"
            await Database.execute(sql)

        if message_changes:
            sql = f"UPDATE accounts SET message_changes={message_changes} WHERE account_id={self.id}"
            await Database.execute(sql)

    async def enabled_saving_messages(self: 'MaksogramClient') -> bool:
        """Проверяет, включена ли настройка "Сохранение сообщений" у клиента"""

        sql = f"SELECT saving_messages FROM settings WHERE account_id={self.id}"
        data: bool = await Database.fetch_row_for_one(sql)

        return data

    async def enabled_notify_changes(self: 'MaksogramClient') -> bool:
        """Проверяет, включены ли уведомления об изменении сообщений"""

        sql = f"SELECT notify_changes FROM settings WHERE account_id={self.id}"
        data: bool = await Database.fetch_row_for_one(sql)

        return data

    async def add_saved_message(self: 'MaksogramClient', message: Message, saved_message_id: int):
        """Добавляет в базу данных сохраненное сообщение с параметрами"""

        sql = f"INSERT INTO {self.table_name} (chat_id, message_id, saved_message_id, hash, media) VALUES ($1, $2, $3, $4, $5)"
        await Database.execute(sql, message.chat_id, message.id, saved_message_id, message_hash(message), media_id(message))

    async def update_saved_message(self: 'MaksogramClient', saved_message_id: int, message: Message):
        """Изменят сохраненное в базе данных сообщение с новыми параметрами"""

        sql = f"UPDATE {self.table_name} SET hash=$1, media=$2 WHERE saved_message_id={saved_message_id}"
        await Database.execute(sql, message_hash(message), media_id(message))

    async def set_is_started(self: 'MaksogramClient', value: bool):
        """Изменяет состояние клиента в базе данных"""

        await set_is_started(self.id, value)

    async def get_saved_message(self: 'MaksogramClient', chat_id: int, message_id: int) -> Optional[SavedMessage]:
        """
        Ищет сохраненное сообщение в базе данных

        :param chat_id: чат с сообщением
        :param message_id: сообщение
        :return: `None`, если сохраненное сообщение не найдено,
            иначе объект `SavedMessage` с saved_message_id, hash'ем сохраненного сообщения для проверки на изменение и media (file_id)
        """

        sql = f"SELECT saved_message_id, hash, media FROM {self.table_name} WHERE chat_id={chat_id} AND message_id={message_id}"
        data: dict[str, Union[int, str]] = await Database.fetch_row(sql)

        if not data:
            return None  # Сохраненное сообщение не найдено

        return SavedMessage(id=data['saved_message_id'], hash=data['hash'], media=data['media'])

    async def get_saved_deleted_message(self: 'MaksogramClient', is_private: bool, chat_id: Optional[int], message_id: int) -> tuple[Optional[int], Optional[int]]:
        """
        Ищет сохраненное сообщение в базе данных, которое уже удалено

        :param is_private: `True`, если сообщение удалено в личном чате, иначе `False`
        :param chat_id: `None`, если сообщение удалено в личном чате, иначе чат с удаленным сообщением
        :param message_id: идентификатор сообщения, которое удалено
        :return: (`None`, `None`), если сохраненное сообщение не найдено, иначе chat_id и saved_message_id`
        """

        if is_private:
            sql = f"SELECT chat_id, saved_message_id FROM {self.table_name} WHERE message_id={message_id} AND saved_message_id > 0"
        else:
            sql = f"SELECT chat_id, saved_message_id FROM {self.table_name} WHERE chat_id={chat_id} AND message_id={message_id}"

        data: dict[str, int] = await Database.fetch_row(sql)
        if not data:
            return None, None  # Сохраненное сообщение не найдено в базе данных

        return data['chat_id'], data['saved_message_id']

    async def delete_all_saved_messages(self: 'MaksogramClient'):
        """Удаляет все сохраненные сообщения в базе данных"""

        sql = f"DELETE FROM {self.table_name}"
        await Database.execute(sql)

        self.logger.info("удалены все сохраненные сообщения из базы данных")

    async def delete_saved_messages(self: 'MaksogramClient', ids: Union[int, tuple[int]]):
        """Удаляет нужные(ое) сохраненные сообщения из базы данных"""

        if isinstance(ids, int):
            ids = (ids,)
        ids = tuple(map(str, ids))

        sql = f"DELETE FROM {self.table_name} WHERE saved_message_id IN ({','.join(ids)})"
        await Database.execute(sql)

        self.logger.info(f"удалены {len(ids)} сохраненных сообщений в базе данных")

    async def in_added_chats(self: 'MaksogramClient', chat_id: int) -> bool:
        """Проверяет вхождение группы/канала в added_chats клиента"""

        sql = f"SELECT added_chats ? '{chat_id}' FROM settings WHERE account_id={self.id}"
        data: bool = await Database.fetch_row_for_one(sql)

        return data

    async def not_in_removed_chats(self: 'MaksogramClient', user_id: int) -> bool:
        """Проверяет отсутствие пользователя в removed_chats клиента"""

        sql = f"SELECT removed_chats ? '{user_id}' FROM settings WHERE account_id={self.id}"
        data: bool = await Database.fetch_row_for_one(sql)

        return not data

    async def get_time_zone(self: 'MaksogramClient') -> int:
        """Часовой пояс клиента в базе данных"""

        sql = f"SELECT time_zone FROM settings WHERE account_id={self.id}"
        data: int = await Database.fetch_row_for_one(sql)

        return data

    async def get_gender(self: 'MaksogramClient') -> Optional[bool]:
        """Пол клиента, выбранный в настройках. True - мужчина, False - женщина, None - не указан"""

        sql = f"SELECT gender FROM settings WHERE account_id={self.id}"
        data: Optional[bool] = await Database.fetch_row_for_one(sql)

        return data

    async def update_awake_time(self: 'MaksogramClient'):
        """Обновляет время пробуждения на текущее локально, в базе данных для самого клиента и всех, кто добавил в "Друг в сети"."""

        self.set_awake_time(time_now())

        sql = f"UPDATE accounts SET awake_time=now() WHERE account_id={self.id}"
        await Database.execute(sql)

        sql = f"UPDATE status_users SET awake=now() WHERE user_id={self.id} AND awake IS NOT NULL"
        await Database.execute(sql)

    async def check_count_saved_messages(self: 'MaksogramClient') -> bool:
        """Считает количество сохраненных сообщений за день с учетом часового пояса клиента и возвращает возможность сохранить еще одно"""

        subscription = await get_subscription(self.id)
        if subscription == 'admin':
            return True

        # Считает количество сообщений, у которых дата отправки больше прошедшей полночи с учетом часового пояса клиента
        sql = (f"SELECT COUNT(*) FROM {self.table_name} WHERE (now() + INTERVAL '1 hour' * (SELECT time_zone FROM settings WHERE account_id={self.id}))"
               f"::date::timestamp - INTERVAL '1 hour' * (SELECT time_zone FROM settings WHERE account_id={self.id}) <= time")
        count: int = await Database.fetch_row_for_one(sql)

        if subscription == 'premium':
            return count < MAX_COUNT_SAVED_MESSAGES_PER_DAY_FOR_PREMIUM
        return count < MAX_COUNT_SAVED_MESSAGES_PER_DAY

    async def update_limit(self: 'MaksogramClient', limit: str):
        """Обновляет лимит"""

        value = 'true' if limit == 'saving_messages' else f'{limit} + 1'
        sql = f"UPDATE limits SET {limit}={value} WHERE account_id={self.id}"
        await Database.execute(sql)

    async def get_limit(self: 'MaksogramClient', limit: str) -> Union[bool, int]:
        """Возвращает текущее значение использования функции"""

        # Обновляет reset_time, если время пришло
        sql = ("UPDATE limits SET saving_messages=false, audio_transcription=0, round_video=0, reminder=0, ghost_stories=0, ghost_copy=0, "
               f"reset_time=(now() + INTERVAL '1 hour' * (SELECT time_zone FROM settings WHERE account_id={self.id}))::date::timestamp - "
               f"INTERVAL '1 hour' * (SELECT time_zone FROM settings WHERE account_id={self.id}) + INTERVAL '1 day' "
               f"WHERE reset_time <= now() AND account_id={self.id}")
        await Database.execute(sql)

        sql = f"SELECT {limit} FROM limits WHERE account_id={self.id}"
        data: Union[bool, int] = await Database.fetch_row_for_one(sql)

        return data

    async def check_count_usage_module(self: 'MaksogramClient', module: str) -> bool:
        """Считает количество использований функции и возвращает возможность один раз ее вызвать"""

        subscription = await get_subscription(self.id)
        if subscription == 'admin':
            return True

        limit = await self.get_limit(module)
        if subscription == 'premium':
            if module == 'audio_transcription':
                return limit < MAX_COUNT_USAGE_AUDIO_TRANSCRIPTION_FRO_PREMIUM
            if module == 'round_video':
                return limit < MAX_COUNT_USAGE_ROUND_VIDEO_FRO_PREMIUM
            if module == 'reminder':
                return limit < MAX_COUNT_USAGE_REMINDER_FRO_PREMIUM
        else:
            if module == 'audio_transcription':
                return limit < MAX_COUNT_USAGE_AUDIO_TRANSCRIPTION
            if module == 'round_video':
                return limit < MAX_COUNT_USAGE_ROUND_VIDEO
            if module == 'reminder':
                return limit < MAX_COUNT_USAGE_REMINDER

        raise ValueError(f"module {module} не найден")
