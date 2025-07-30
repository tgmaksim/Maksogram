from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . maksogram_client import MaksogramClient


from enum import StrEnum
from typing import Optional
from dataclasses import dataclass


maksogram_clients: dict[int, 'MaksogramClient'] = {}


@dataclass
class SavedMessage:
    """
    Сохраненное сообщение в базе данных

    :param hash: md5-хеш текста сообщения с форматированием (message.text)
    :param media: file_id медиа
    """

    id: int
    hash: str
    media: Optional[int]


class UserIsNotAuthorized(Exception):
    """Сессия TelegramClient удалена или сброшена. Требуется повторный вход"""


class CreateChatsError(Exception):
    """Ошибка при создании системных чатов"""


@dataclass
class CreateChatsResult:
    """
    Результат создания системных чатов

    :param ok: успех операции
    :param my_messages: идентификатор системного канала
    :param message_changes: идентификатор системной супергруппы для комментариев
    :param error: ошибка (Exception), возникшая при попытке создания системных чатов
    :param error_message: текст сообщения, который необходимо показать пользователю
    """

    ok: bool
    my_messages: Optional[int] = None
    message_changes: Optional[int] = None
    error: Optional[Exception] = None
    error_message: Optional[str] = None


class SystemChannelUpdate(StrEnum):
    """Варианты критических изменений системных чатов"""

    my_messages_deleted = "my_messages_deleted"
    message_changes_deleted = "message_changes_deleted"
    unlinked_message_changes = "unlinked_message_changes"


@dataclass
class AccountWithStatus:
    """Идентификатор клиента с его статусом"""

    id: int
    is_started: bool
