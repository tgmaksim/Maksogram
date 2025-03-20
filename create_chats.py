from typing import Union
from telethon import functions
from datetime import timedelta
from core import MaksogramBot, channel
from telethon.sync import TelegramClient
from telethon.tl.types.contacts import ResolvedPeer
from telethon.tl.functions.messages import UpdateDialogFilterRequest

from telethon.tl.types import (
    InputChannel,
    DialogFilter,
    InputPeerUser,
    InputNotifyPeer,
    InputPeerChannel,
    InputChatUploadedPhoto,
    InputPeerNotifySettings,
)
from telethon.tl.functions.channels import (
    EditPhotoRequest,
    JoinChannelRequest,
    CreateChannelRequest,
    SetDiscussionGroupRequest,
)


class CreateChatsError(Exception):
    pass


async def create_chats(client: TelegramClient) -> dict[str, Union[str, Exception]]:
    try:
        # Создание канала "Мои сообщения"
        my_messages = await client(CreateChannelRequest("Мои сообщения", "Мои сообщения", megagroup=False))
        my_messages_id = my_messages.updates[1].channel_id
        my_messages_access_hash = my_messages.chats[0].access_hash
        input_my_messages = InputChannel(my_messages_id, my_messages_access_hash)
        input_peer_my_messages = InputPeerChannel(my_messages_id, my_messages_access_hash)
        await client(EditPhotoRequest(input_my_messages, InputChatUploadedPhoto(await client.upload_file("resources/my_messages.jpg"))))
        await client.delete_messages(input_peer_my_messages, 2)  # Удаляем сообщение об изменении фото канала
        await client.edit_folder(input_peer_my_messages, 1)  # Кидаем в архив
    except Exception as e:
        return {
            'result': 'error',
            'error': e,
            'message': 'При попытке создать и настроить канал "Мои сообщения" произошла ошибка'
        }

    try:
        # Создание супергруппы "Изменение сообщения"
        message_changes = await client(CreateChannelRequest("Изменение сообщения", "Все изменения сообщений аккаунта", megagroup=True))
        message_changes_id = message_changes.updates[1].channel_id
        message_changes_access_hash = message_changes.chats[0].access_hash
        input_message_changes = InputChannel(message_changes_id, message_changes_access_hash)
        input_peer_message_changes = InputPeerChannel(message_changes_id, message_changes_access_hash)
        await client(EditPhotoRequest(input_message_changes, InputChatUploadedPhoto(await client.upload_file("resources/edit_message.jpg"))))
        await client(functions.account.UpdateNotifySettingsRequest(InputNotifyPeer(input_peer_message_changes), InputPeerNotifySettings(show_previews=False, mute_until=timedelta(days=1000))))
        await client.delete_messages(input_peer_message_changes, 2)  # Удаляем сообщение об изменении фото группы
        await client.edit_folder(input_peer_message_changes, 1)  # Кидаем в архив
        # Добавляем к каналу "Мои сообщения" группу для комментариев
        await client(SetDiscussionGroupRequest(input_my_messages, input_message_changes))
    except Exception as e:
        return {
            'result': 'error',
            'error': e,
            'message': 'При попытке создания и настройки группы "Изменение сообщения" произошла ошибка'
        }

    try:
        # Работаем с ботом "MaksogramBot"
        bot = await client(functions.contacts.ResolveUsernameRequest(MaksogramBot.username))
        bot = InputPeerUser(MaksogramBot.id, bot.users[0].access_hash)
        await client.edit_folder(bot, 1)  # Кидаем в архив
    except Exception as e:
        return {
            'result': 'error',
            'error': e,
            'message': 'При попытке настроить системного бота произошла ошибка'
        }

    try:
        # Присоединяемся к каналу tgmaksim.ru и добавляем в папку
        admin_channel: ResolvedPeer = await client(functions.contacts.ResolveUsernameRequest(channel))
        input_admin_channel: InputChannel = InputChannel(admin_channel.peer.channel_id, admin_channel.chats[0].access_hash)
        input_peer_admin_channel: InputPeerChannel = InputPeerChannel(admin_channel.peer.channel_id, admin_channel.chats[0].access_hash)
        await client(JoinChannelRequest(input_admin_channel))
        await client.edit_folder(input_peer_admin_channel, 1)  # Кидаем в архив
    except Exception as e:
        return {
            'result': 'error',
            'error': e,
            'message': f'При попытке подписаться на канал @{channel} произошла ошибка'
        }

    try:
        # Создаем папку с чатами "Maksogram" и добавляем канал "Мои сообщения" и системного бота "Maksogram"
        await client(UpdateDialogFilterRequest(
            42, DialogFilter(42, "Maksogram", [input_peer_my_messages, input_peer_admin_channel, bot], [], [])))
    except Exception as e:
        return {
            'result': 'error',
            'error': e,
            'message': 'При попытке создать и настроить папку произошла ошибка'
        }

    return {
        'result': 'ok',
        'my_messages': -10**12-my_messages_id,  # -100<id>
        'message_changes': -10**12-message_changes_id  # -100<id>
    }
