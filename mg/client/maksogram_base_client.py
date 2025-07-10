from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . maksogram_client import MaksogramClient


import asyncio
import logging

from mg.config import OWNER, VERSION, CHANNEL_ID

from asyncio import Task
from typing import Type, Optional
from mg.core.types import MaksogramBot
from datetime import datetime, timedelta
from mg.core.functions import log_path, time_now, error_notify, format_error

from telethon import TelegramClient
from mg.client.types import maksogram_clients, UserIsNotAuthorized
from mg.client.functions import new_telegram_client, check_connection, client_connect
from telethon.errors.rpcerrorlist import AuthKeyInvalidError, AuthKeyUnregisteredError

from telethon.tl.types import (
    UpdateChannel,
    MessageService,
    UserStatusOnline,
    UserStatusOffline,

    UpdateNewMessage,
    UpdateNewAuthorization,
)
from telethon.events import (
    Raw,
    UserUpdate,
    NewMessage,
    MessageRead,
    MessageEdited,
    MessageDeleted,
)


class LastEvent:
    """Клиент обрабатывает большой поток Update'ов через промежутки времени"""

    seconds: int = 1

    def __init__(self):
        self._datetime = datetime(2009, 12, 9)

    def add(self):
        self._datetime = max(time_now(), self._datetime) + timedelta(seconds=self.seconds)

    @property
    def datetime(self) -> datetime:
        return self._datetime


class MaksogramBaseClient:
    def __init__(self: 'MaksogramClient', account_id: int, client: TelegramClient):
        self._id = account_id
        self._client = client

        self._last_event = LastEvent()
        self._status = None
        self.recovery_system_channels = False

        # Логирование некоторых данных для выявления причин ошибок и их исправления
        self._logger = logging.getLogger(f"account{account_id}")
        if self.is_owner:
            self._logger.setLevel(logging.DEBUG)
        else:
            self._logger.setLevel(logging.INFO)  # Для обычных клиентов DEBUG пропускается
        handler = logging.FileHandler(log_path(f"account{account_id}.log"))
        handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
        self._logger.addHandler(handler)

        # Инициализируются при запуске
        self._my_messages: int = 0
        self._message_changes: int = 0
        self._name: str = '0'
        self._is_premium: bool = False
        self._status_users: dict[int, bool] = {}
        self._awake_time: datetime = datetime(2009, 12, 9)
        self._async_tasks: list[Task] = []

    def handlers_initial(self: 'MaksogramClient'):
        @self.client.on(NewMessage(func=self.check_chat_processing))
        @error_notify()
        async def new_message(event: NewMessage.Event):
            await self.sleep()
            await self.new_message(event)  # Обрабатываем сообщение

            if self.offline:  # Если клиент был offline
                await self.set_offline_status()  # Возвращаем статус после появления в сети из-за отправки сообщения

        @self.client.on(Raw(UpdateNewMessage, func=lambda update: isinstance(update.message, MessageService)))
        @error_notify()
        async def new_message_service(update: UpdateNewMessage):
            await self.sleep()
            await self.new_message_service(NewMessage.Event(update.message))

        @self.client.on(NewMessage(chats=777000, incoming=True))
        @error_notify()
        async def official(event: NewMessage.Event):
            await self.official(event)

        @self.client.on(NewMessage(chats=MaksogramBot.id, outgoing=True))
        @error_notify()
        async def maksogram_bot(event: NewMessage.Event):
            await self.maksogram_bot(event)

        @self.client.on(Raw(UpdateNewAuthorization))
        @error_notify()
        async def new_authorization(update: UpdateNewAuthorization):
            await self.new_authorization(update)

        @self.client.on(MessageEdited(func=self.check_chat_processing))
        @error_notify()
        async def message_edited(event: MessageEdited.Event):
            await self.sleep()
            await self.message_edited(event)

            if self.offline:  # Если клиент был offline
                await self.set_offline_status()  # Возвращаем статус после появления в сети из-за отправки сообщения

        @self.client.on(MessageRead(inbox=False, func=self.check_chat_processing))
        @error_notify()
        async def message_read(event: MessageRead.Event):
            await self.sleep()
            await self.message_read(event)

        @self.client.on(MessageRead(chats=CHANNEL_ID, inbox=True))
        @error_notify()
        async def channel_read(_: MessageRead.Event):
            await self.sleep()
            await self.channel_read()

        @self.client.on(MessageDeleted())
        @error_notify()
        async def message_deleted(event: MessageDeleted.Event):
            if event.is_private is True:
                if not await self.in_added_chats(event.chat_id):
                    return  # Сообщение удалено в группе или канале и чат не добавлен в added_chats клиента

            await self.sleep()
            await self.message_deleted(event)

            if self.offline:  # Если клиент был offline
                await self.set_offline_status()  # Возвращаем статус после появления в сети из-за отправки сообщения

        @self.client.on(UserUpdate(chats=self.status_users, func=lambda event: isinstance(event.status, (UserStatusOnline, UserStatusOffline))))
        @error_notify()
        async def user_update(event: UserUpdate.Event):
            await self.user_update(event)

        @self.client.on(UserUpdate(chats=self.id, func=lambda event: isinstance(event.status, (UserStatusOnline, UserStatusOffline))))
        @error_notify()
        async def self_update(event: UserUpdate.Event):
            await self.self_update(event)

        @self.client.on(Raw(UpdateChannel, func=lambda update: update.channel_id in (self.my_messages_channel_id, self.message_changes_channel_id)))
        @error_notify()
        async def update_system_channels(_):
            if self.is_owner:
                return

            if not self.recovery_system_channels:  # Если событие еще не обрабатывается
                self.recovery_system_channels = True
                updates = await self.check_system_channels()  # Получаем список значительных изменений
                if updates:
                    await MaksogramBot.send_system_message(f"🚨 <b>Нарушение правил</b> ❗️\n<b>{self.name}</b> изменил системные чаты\n"
                                                           f"Коды ошибок: {', '.join(updates)}")
                    await MaksogramBot.send_message(
                        self.id, "🚨 <b>Нарушение правил</b> ❗️\nБыло замечено значительное изменение в системных чатах или папке Maksogram. "
                                 "Maksogram остановлен! Попробуйте перезапустить в /menu\n\n/help - пользовательское соглашение")
                    await self.off_account(self.id)  # Если есть значительные изменения, останавливаем (исправляем при запуске)
                else:
                    self.recovery_system_channels = False  # Если нет значительных изменений, продолжаем работать

        @self.client.on(Raw(UpdateChannel, func=lambda update: update.channel_id == CHANNEL_ID))
        @error_notify()
        async def update_admin_channel(_):
            if self.is_owner:
                return

            await self.update_admin_channel()
            await self.update_system_dialog_filter()

    async def sleep(self: 'MaksogramClient'):
        """Ожидает обработки Update перед ним + `LastEvent.seconds`, чтобы не было перегрузки"""

        difference = (time_now() - self.last_event.datetime).total_seconds()  # Разница между текущим временем и последним событием
        if difference < LastEvent.seconds:  # Если прошло менее необходимого
            self.last_event.add()  # Добавляем время, чтобы следующее событие ожидало

            await asyncio.sleep(LastEvent.seconds - difference)

    async def check_chat_processing(self: 'MaksogramClient', event: NewMessage.Event) -> bool:
        """Проверяет необходимость обработки Event'а с новым сообщением"""

        if event.is_private and not await self.not_in_removed_chats(event.chat_id):
            return False  # Клиент добавил пользователя в список чатов, которых не нужно обрабатывать
        if not event.is_private and not await self.in_added_chats(event.chat_id):
            return False  # Клиент не добавил группу/канал в список чатов, которых нужно обрабатывать

        if event.is_private:
            try:
                entity = await self.client.get_entity(event.chat_id)
            except ValueError:
                return False

            return not (entity.bot or entity.support)  # Не обрабатываются любые боты и служебные аккаунты

        return True  # Группы/каналы из списка added_chats обрабатываются без дополнительных условий

    @classmethod
    async def on_account(cls: Type['MaksogramClient'], account_id: int):
        """Запускает работу MaksogramClient для клиента"""

        maksogram_client = maksogram_clients.get(account_id)
        if maksogram_client is None:
            maksogram_client = cls(account_id, new_telegram_client(account_id))
            maksogram_clients[account_id] = maksogram_client

        if not await check_connection(maksogram_client.client):
            if not await client_connect(maksogram_client.client):
                raise ConnectionError(f"Соединение с сервером не установлено для {maksogram_client.id}")

        if await maksogram_client.client.is_user_authorized():
            await maksogram_client.set_is_started(True)
            asyncio.create_task(maksogram_client.run_until_disconnected())

        else:
            raise UserIsNotAuthorized

    @classmethod
    async def off_account(cls: Type['MaksogramClient'], account_id: int):
        """Останавливает работу MaksogramClient для клиента"""

        maksogram_client = maksogram_clients[account_id]

        await maksogram_client.set_is_started(False)

        await maksogram_client.disconnect()

    async def run_until_disconnected(self: 'MaksogramClient'):
        await self.create_table()
        await self.update_initial_data()  # Заполняем данные
        self.handlers_initial()  # Создаем обработчики событий

        try:
            if not self.is_owner:
                await self.update_admin_channel()  # Подписываемся на канал, если нужно

                if updates := await self.check_system_channels():  # Проверяем состояние системных чатов
                    await MaksogramBot.send_system_message(
                        f"🚨 <b>Нарушение правил</b> ❗️\n<b>{self.name}</b> изменил системные чаты\nКоды ошибок: {', '.join(updates)}")
                    await self.recover_system_channels(updates)  # Восстанавливаем системные чаты

                await self.update_system_dialog_filter()  # Восстанавливаем папку Maksogram, если нужно

            self.async_tasks.append(asyncio.get_running_loop().create_task(self.changed_profile_center()))
            self.async_tasks.append(asyncio.get_running_loop().create_task(self.admin_logger()))
            self.async_tasks.append(asyncio.get_running_loop().create_task(self.reminder_center()))

            await MaksogramBot.send_system_message(f"Maksogram {VERSION} для {self.name} запущен")
            self.logger.info("MaksogramClient запущен")

            await self.client.run_until_disconnected()
        except (AuthKeyInvalidError, AuthKeyUnregisteredError) as e:
            self.logger.error(f"ошибка при выполнении {e.__class__.__name__} ({e})")
            await MaksogramBot.send_message(self.id, "Вы удалили сессию, она необходима для работы Maksogram")
            if not self.is_owner:
                await MaksogramBot.send_system_message(f"Удалена сессия у {self.name}")
            await self.off_account(self.id)
        except ConnectionError as e:
            self.logger.error(f"ошибка ConnectionError при запуске MaksogramClient")
            await MaksogramBot.send_system_message(format_error(e))
            await MaksogramBot.send_message(self.id, "Произошла временная ошибка при запуске, откройте /menu и запустите вручную")
        except Exception as e:
            self.logger.error(f"ошибка {e.__class__.__name__} при запуске MaksogramClient ({e})")
            await MaksogramBot.send_system_message(format_error(e))

        await MaksogramBot.send_system_message(f"Maksogram {VERSION} для {self.name} остановлен")
        self.logger.info("MaksogramClient остановлен")

    async def disconnect(self: 'MaksogramClient'):
        """Разрывает соединение с TelegramClient и очищает MaksogramClient"""

        for task in self.async_tasks:
            task.cancel()

        await self.client.disconnect()
        self._client = new_telegram_client(self.id)

    async def set_init_data(self: 'MaksogramClient', name: str, my_messages: int, message_changes: int, status_users: list[int], awake_time: datetime):
        """Изменяет основные данные клиента"""

        self._name = name
        self._is_premium = (await self.client.get_me()).premium
        self._my_messages = my_messages
        self._message_changes = message_changes
        self._status_users = {user_id: False for user_id in status_users if user_id != self.id}
        self._awake_time = awake_time

    @property
    def id(self: 'MaksogramClient') -> int:
        return self._id

    @property
    def client(self: 'MaksogramClient') -> TelegramClient:
        return self._client

    @property
    def last_event(self: 'MaksogramClient') -> LastEvent:
        return self._last_event

    @property
    def status(self: 'MaksogramClient') -> bool:
        return self._status

    def set_status(self: 'MaksogramClient', value: bool):
        self._status = value

    @property
    def logger(self: 'MaksogramClient') -> logging.Logger:
        return self._logger

    @property
    def my_messages(self: 'MaksogramClient') -> int:
        return self._my_messages

    @property
    def message_changes(self: 'MaksogramClient') -> int:
        return self._message_changes

    def set_channel_ids(self: 'MaksogramClient', *, my_messages: Optional[int] = None, message_changes: Optional[int] = None):
        if my_messages:
            self._my_messages = my_messages
        if message_changes:
            self._message_changes = message_changes

    @property
    def name(self: 'MaksogramClient') -> str:
        return self._name

    @property
    def is_premium(self: 'MaksogramClient') -> bool:
        return self._is_premium

    @property
    def status_users(self: 'MaksogramClient') -> dict[int, bool]:
        return self._status_users

    def add_status_user(self: 'MaksogramClient', user_id: int):
        if user_id == self.id:
            return

        self.status_users[user_id] = False

        for handler in self.client.list_event_handlers():
            if handler[0].__name__ == 'user_update':
                handler[1].chats = set(self.status_users)

    def delete_status_user(self: 'MaksogramClient', user_id: int):
        if user_id == self.id:
            return

        self.status_users.pop(user_id)

        for handler in self.client.list_event_handlers():
            if handler[0].__name__ == 'user_update':
                handler[1].chats = set(self.status_users)

    @property
    def awake_time(self: 'MaksogramClient') -> datetime:
        return self._awake_time

    def set_awake_time(self: 'MaksogramClient', value: datetime):
        self._awake_time = value

    @property
    def async_tasks(self: 'MaksogramClient') -> list[Task]:
        return self._async_tasks

    @property
    def offline(self: 'MaksogramClient') -> bool:
        return not self.status

    @property
    def is_owner(self: 'MaksogramClient') -> bool:
        return self.id == OWNER

    @property
    def my_messages_channel_id(self: 'MaksogramClient') -> int:
        """my_messages без -100 в начале"""

        return int(str(self.my_messages)[4:])

    @property
    def message_changes_channel_id(self: 'MaksogramClient') -> int:
        """message_changes без -100 в начале"""

        return int(str(self.message_changes)[4:])

    def link_to_saved_message(self: 'MaksogramClient', saved_message_id: int) -> str:
        """Ссылка на сообщение в системном канале"""

        return f"t.me/c/{self.my_messages_channel_id}/{saved_message_id}"
