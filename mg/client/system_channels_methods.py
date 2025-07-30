from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . maksogram_client import MaksogramClient


from mg.config import CHANNEL, CHANNEL_ID

from . types import SystemChannelUpdate
from mg.core.types import MaksogramBot
from . create_chats import (
    join_admin_channel,
    create_my_messages,
    update_dialog_filter,
    create_message_changes,
    link_my_messages_to_message_changes,
)

from telethon.tl.types import ChannelFull, ChannelParticipantLeft, InputPeerSelf
from telethon.utils import get_peer_id, get_input_peer, get_peer, get_input_channel
from telethon.errors.rpcerrorlist import ChannelPrivateError, UserNotParticipantError
from telethon.tl.functions.channels import GetFullChannelRequest, GetParticipantRequest


class SystemChannelsMethods:
    async def check_system_channels(self: 'MaksogramClient') -> set[SystemChannelUpdate]:
        """Проверяет системные чаты на наличие и связанность"""

        result = set()

        try:  # Проверка наличия супергруппы для комментариев
            await self.client(GetFullChannelRequest(self.message_changes))
        except ChannelPrivateError:
            result.add(SystemChannelUpdate.message_changes_deleted)  # Супергруппа для комментариев удалена
            result.add(SystemChannelUpdate.unlinked_message_changes)  # Супергруппа для комментариев отвязана

        try:  # Проверка наличия системного канала
            my_messages: ChannelFull = (await self.client(GetFullChannelRequest(self.my_messages))).full_chat
        except ChannelPrivateError:
            result.add(SystemChannelUpdate.my_messages_deleted)  # Системный канал удален
            result.add(SystemChannelUpdate.unlinked_message_changes)  # Супергруппа для комментариев отвязана
        else:  # Системный канал НЕ удален
            if not my_messages.linked_chat_id:  # Супергруппа с комментариями отвязана (может быть удалена)
                result.add(SystemChannelUpdate.unlinked_message_changes)  # Супергруппа для комментариев отвязана

        return result

    async def update_system_dialog_filter(self: 'MaksogramClient'):
        """Обновляет (если изменилась) папку Maksogram до изначального положения"""

        await update_dialog_filter(self.client, self.my_messages)

    async def update_admin_channel(self: 'MaksogramClient') -> bool:
        """
        Подписывается на канал админа, если необходимо

        :return: True, если канал был удален, иначе False
        """

        input_channel = get_input_channel(await self.client.get_input_entity(CHANNEL_ID))

        try:
            participant = (await self.client(GetParticipantRequest(input_channel, InputPeerSelf()))).participant
        except UserNotParticipantError:
            participant = ChannelParticipantLeft(get_peer(self.id))

        if isinstance(participant, ChannelParticipantLeft):  # Аккаунт не является участником
            await join_admin_channel(self.client)
            await MaksogramBot.send_system_message(f"🚨 <b>Нарушение правил</b> ❗️\n{self.name} отписал(а)сь от канала")
            await MaksogramBot.send_message(
                self.id, "🚨 <b>Нарушение правил</b> ❗️\nЛюбой чат в папке Maksogram, а также сама системная папка являются "
                         f"неприкосновенными (в том числе канал @{CHANNEL})\n/help - пользовательское соглашение")

            return True  # Канал был удален

        return False  # Канал на месте, все нормально

    async def recover_system_channels(self: 'MaksogramClient', updates: set[SystemChannelUpdate]):
        """Восстановление системных чатов и папки Maksogram"""

        # Удалены особо значимые объекты
        if SystemChannelUpdate.my_messages_deleted in updates or SystemChannelUpdate.message_changes_deleted in updates:
            await self.delete_all_saved_messages()

        if SystemChannelUpdate.my_messages_deleted in updates:  # Системный канал удален
            my_messages = await create_my_messages(self.client)  # Создание системного канала
            self.set_channel_ids(my_messages=get_peer_id(my_messages, add_mark=True))
            await self.update_channel_ids(my_messages=self.my_messages)

        if SystemChannelUpdate.message_changes_deleted in updates:  # Супергруппа для комментариев удалена
            message_changes = await create_message_changes(self.client)  # Создание супергруппы для комментариев
            self.set_channel_ids(message_changes=get_peer_id(message_changes, add_mark=True))
            await self.update_channel_ids(message_changes=self.message_changes)

        if SystemChannelUpdate.unlinked_message_changes in updates:  # Супергруппа для комментариев отвязана
            await link_my_messages_to_message_changes(self.client, self.my_messages, self.message_changes)
