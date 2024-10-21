import asyncio

from accounts import Account
from telethon import functions
from datetime import timedelta
from core import Data, SystemBot
from telethon.sync import TelegramClient
from telethon.tl.functions.messages import StartBotRequest, UpdateDialogFilterRequest

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
    CreateChannelRequest,
    UpdateUsernameRequest,
    SetDiscussionGroupRequest,
)


async def main():
    account = Account.get_accounts()[int(input("ID пользователя: "))]
    username_channel_status = input("Username канала для статуса: ")
    title_channel_status = input("Название канала для статуса: ")
    print()
    client = TelegramClient(
        account.get_session_path(),
        Data.APPLICATION_ID,
        Data.APPLICATION_HASH,
        system_version="4.16.30-vxCUSTOM",
        app_version=Data.version
    )
    client.start(phone=account.phone, password=account.password)

    my_messages = await client(CreateChannelRequest("Мои сообщения", "Мои сообщения", megagroup=False))
    my_messages_id = my_messages.updates[1].channel_id
    my_messages_access_hash = my_messages_id.chats[0].access_hash
    input_my_messages = InputChannel(my_messages_id, my_messages_access_hash)
    input_peer_my_messages = InputPeerChannel(my_messages_id, my_messages_access_hash)
    await client(EditPhotoRequest(input_my_messages, InputChatUploadedPhoto(await client.upload_file("resources/my_messages.jpg"))))
    await client.edit_folder(input_peer_my_messages, 1)
    print("Канал \"Мои сообщения\" создан")

    message_changes = await client(CreateChannelRequest("Изменение сообщения", "Все изменения сообщений аккаунта", megagroup=True))
    message_changes_id = message_changes.updates[1].channel_id
    message_changes_access_hash = message_changes.chats[0].access_hash
    input_message_changes = InputChannel(message_changes_id, message_changes_access_hash)
    input_peer_message_changes = InputPeerChannel(message_changes_id, message_changes_access_hash)
    await client(EditPhotoRequest(input_message_changes, InputChatUploadedPhoto(await client.upload_file("resources/edit_message.jpg"))))
    await client(functions.account.UpdateNotifySettingsRequest(InputNotifyPeer(input_peer_message_changes), InputPeerNotifySettings(show_previews=False, mute_until=timedelta(days=365))))
    await client.edit_folder(input_peer_message_changes, 1)
    print("Группа \"Изменение сообщения\" создана")

    await client(SetDiscussionGroupRequest(input_message_changes, input_message_changes))
    print("Группа теперь стала комментариями к каналу\n")

    channel_status = await client(CreateChannelRequest(title_channel_status, "В сети я или нет...", megagroup=False))
    channel_status_id = channel_status.updates[1].channel_id
    channel_status_access_hash = channel_status.chats[0].access_hash
    input_status_channel = InputChannel(channel_status_id, channel_status_access_hash)
    input_peer_status_channel = InputPeerChannel(channel_status_id, channel_status_access_hash)
    await client(UpdateUsernameRequest(input_status_channel, username_channel_status))
    await client(EditPhotoRequest(input_status_channel, InputChatUploadedPhoto(await client.upload_file("resources/status_channel.jpg"))))
    message_status_id = (await client.send_message(input_peer_status_channel, "в сети")).id
    await client.edit_folder(input_peer_status_channel, 1)
    print(f"Канал \"{username_channel_status}\" создан")

    await client(StartBotRequest(SystemBot.username, SystemBot.username, 'start'))
    bot = await client(functions.contacts.ResolveUsernameRequest("SystemMaksimBot"))
    bot = InputPeerUser(SystemBot.id, bot.users[0].access_hash)
    await client.edit_folder(bot, 1)
    print("Системный бот запущен")

    await client(UpdateDialogFilterRequest(42, DialogFilter(42, "Программа", [input_peer_my_messages, input_peer_status_channel, bot], [], [])))
    print("Папка создана")

    print("my_messages_id:", my_messages_id)
    print("message_changes_id:", message_changes_id)
    print("message_status_id:", message_status_id)
    print("channel_status_id:", channel_status_id)

    print("Все!")


if __name__ == '__main__':
    asyncio.run(main())
