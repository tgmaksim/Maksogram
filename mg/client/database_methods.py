from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . maksogram_client import MaksogramClient

from datetime import datetime
from mg.core.database import Database
from mg.core.functions import time_now
from typing import Union, Optional, Type

from telethon.tl.patched import Message

from . functions import (
    media_id,
    message_hash,
    SavedMessage,
    set_is_started,
)


class DatabaseMethods:
    async def create_table(self: 'MaksogramClient'):
        """Создает таблицу в базе данных для хранения сохраненных сообщений"""

        sql = f"CREATE TABLE IF NOT EXISTS {self.table_name} (chat_id BIGINT NOT NULL, message_id INTEGER NOT NULL, " \
              "saved_message_id INTEGER NOT NULL, hash CHARACTER VARYING(128) NOT NULL, media BIGINT)"
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

    @property
    def table_name(self: 'MaksogramClient') -> str:
        """Имя таблицы в базе данных с сохраненными сообщениями"""

        return self.format_table_name(self.id)

    @classmethod
    def format_table_name(cls: Type['MaksogramClient'], account_id: int) -> str:
        return f"zz{account_id}"
