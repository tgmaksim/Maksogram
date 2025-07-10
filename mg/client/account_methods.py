from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . maksogram_client import MaksogramClient


from typing import Optional
from mg.core.functions import full_name

from telethon.tl.patched import Message
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import User, Authorization, Birthday, InputUserSelf, UserFull
from telethon.tl.functions.account import UpdateStatusRequest, GetAuthorizationsRequest


class AccountMethods:
    async def chat_name(self: 'MaksogramClient', chat_id: int, *, my_name="Избранное", unknown="Неизвестный пользователь") -> str:
        """
        Получает название канала, группы, имя контакта или пользователя

        :param chat_id: канал, группа или пользователь
        :param my_name: имя, если пользователь = клиент
        :param unknown: имя, если сущность не будет найдена
        :return: название канала, группы, имя контакта или пользователя
        """

        if chat_id == self.id:
            return my_name

        try:
            entity = await self.client.get_entity(chat_id)
        except ValueError as e:
            self.logger.info(f"сущность {chat_id} не найдена ({e})")
            return unknown

        if isinstance(entity, User):
            return full_name(entity)

        return entity.title

    async def get_message_by_id(self: 'MaksogramClient', chat_id: int, message_id: Optional[int]) -> Optional[Message]:
        """
        Ищет сообщение в чате с определенным `message_id`

        :param chat_id: группа, канала или пользователь
        :param message_id: искомое сообщение или `None`
        :return: `None`, если идентификатор сообщения пустой или сообщение не найдено, иначе объект сообщения
        """

        if message_id is None:
            return None

        async for message in self.client.iter_messages(chat_id, ids=message_id):
            return message

    async def get_authorization(self: 'MaksogramClient', authorization_hash: int) -> Optional[Authorization]:
        """
        Ищет авторизацию с данным hash'ем

        :param authorization_hash: уникальный hash авторизации
        :return: объект `Authorization`
        """

        for authorization in (await self.client(GetAuthorizationsRequest())).authorizations:
            if authorization.hash == authorization_hash:
                return authorization

    async def get_my_birthday(self: 'MaksogramClient') -> Optional[Birthday]:
        """Возвращает день рождения клиента, если указано"""

        request = GetFullUserRequest(InputUserSelf())
        full_user: UserFull = (await self.client(request)).full_user

        return full_user.birthday

    async def set_offline_status(self: 'MaksogramClient'):
        """Устанавливает статус offline для клиента. Необходимо после отправки любого сообщения"""

        await self.client(UpdateStatusRequest(offline=True))
