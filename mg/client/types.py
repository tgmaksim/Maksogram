from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . maksogram_client import MaksogramClient


from enum import StrEnum
from typing import Optional
from dataclasses import dataclass


maksogram_clients: dict[int, 'MaksogramClient'] = {}


@dataclass
class SavedMessage:
    id: int
    hash: str
    media: Optional[int]


class UserIsNotAuthorized(Exception):
    pass


class CreateChatsError(Exception):
    pass


@dataclass
class CreateChatsResult:
    ok: bool
    my_messages: Optional[int] = None
    message_changes: Optional[int] = None
    error: Optional[Exception] = None
    error_message: Optional[str] = None


class SystemChannelUpdate(StrEnum):
    my_messages_deleted = "my_messages_deleted"
    message_changes_deleted = "message_changes_deleted"
    unlinked_message_changes = "unlinked_message_changes"
