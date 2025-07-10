from mg.config import CHANNEL

from datetime import timedelta
from mg.core.types import MaksogramBot
from mg.core.functions import resources_path
from mg.client.types import CreateChatsResult

from telethon import TelegramClient
from telethon.tl.functions.account import UpdateNotifySettingsRequest
from telethon.tl.functions.messages import GetDialogFiltersRequest, UpdateDialogFilterRequest
from telethon.tl.types import (
    Updates,
    DialogFilter,
    InputNotifyPeer,
    TextWithEntities,
    InputChatUploadedPhoto,
    InputPeerNotifySettings,
)
from telethon.tl.functions.channels import (
    EditPhotoRequest,
    JoinChannelRequest,
    CreateChannelRequest,
    SetDiscussionGroupRequest,
)


async def create_my_messages(client: TelegramClient) -> int:
    """
    Создает системный канал Мои сообщения и возвращает его идентификатор

    :param client: клиент
    :return: идентификатор системного канала
    """

    my_messages: Updates = await client(CreateChannelRequest("Мои сообщения", "Мои сообщения", megagroup=False))
    my_messages_id = my_messages.updates[1].channel_id

    await client(EditPhotoRequest(my_messages_id, InputChatUploadedPhoto(await client.upload_file(resources_path("my_messages.jpg")))))
    await client.delete_messages(my_messages_id, 2)  # Удаляем сообщение об изменении фото канала
    await client.edit_folder(my_messages_id, 1)  # Кидаем в архив

    return my_messages_id


async def create_message_changes(client: TelegramClient) -> int:
    """
    Создает супергруппу для комментариев системного канала

    :param client: клиент
    :return:идентификатор супергруппы
    """

    message_changes = await client(CreateChannelRequest("Изменение сообщения", "Все изменения сообщений аккаунта", megagroup=True))
    message_changes_id = message_changes.updates[1].channel_id

    await client(EditPhotoRequest(message_changes_id, InputChatUploadedPhoto(await client.upload_file(resources_path("edit_message.jpg")))))
    await client(UpdateNotifySettingsRequest(InputNotifyPeer(message_changes_id),
                                             InputPeerNotifySettings(show_previews=False, mute_until=timedelta(days=1000))))
    await client.delete_messages(message_changes_id, 2)  # Удаляем сообщение об изменении фото группы
    await client.edit_folder(message_changes_id, 1)  # Кидаем в архив

    return message_changes_id


async def link_my_messages_to_message_changes(client: TelegramClient, my_messages_id: int, message_changes_id: int):
    await client(SetDiscussionGroupRequest(my_messages_id, message_changes_id))


async def join_admin_channel(client: TelegramClient):
    """Присоединяется к каналу админа"""

    await client(JoinChannelRequest(CHANNEL))
    await client.edit_folder(CHANNEL, 1)  # Кидаем в архив


async def create_dialog_filter(client: TelegramClient, my_messages_id: int):
    """Создает папку Maksogram и добавляет системный канал Мои сообщения, канал админа и бота"""

    title = TextWithEntities("Maksogram", [])
    my_messages = await client.get_input_entity(my_messages_id)
    admin_channel = await client.get_input_entity(CHANNEL)
    bot = await client.get_input_entity(MaksogramBot.username)

    await client(UpdateDialogFilterRequest(42, DialogFilter(42, title, [my_messages, admin_channel, bot], [], [])))


async def update_dialog_filter(client: TelegramClient, my_messages_id: int):
    """Обновляет папку Maksogram, если она изменилась"""

    title = TextWithEntities("Maksogram", [])
    my_messages = await client.get_input_entity(my_messages_id)
    admin_channel = await client.get_input_entity(CHANNEL)
    bot = await client.get_input_entity(MaksogramBot.username)

    system_dialog_filter = DialogFilter(42, title, [my_messages, admin_channel, bot], [], [])
    dialog_filters = (await client(GetDialogFiltersRequest())).filters

    for dialog_filter in dialog_filters:
        if isinstance(dialog_filter, DialogFilter) and dialog_filter.id == system_dialog_filter.id:
            if dialog_filter != system_dialog_filter:  # Если папка изменилась
                await client(UpdateDialogFilterRequest(42, system_dialog_filter))
            return

    await client(UpdateDialogFilterRequest(42, system_dialog_filter))  # Папка удалена, восстанавливаем


async def create_chats(client: TelegramClient) -> CreateChatsResult:
    try:
        # Создание канала "Мои сообщения"
        my_messages_id = await create_my_messages(client)
    except Exception as e:
        return CreateChatsResult(
            ok=False,
            error=e,
            error_message="При попытке создать и настроить канал 'Мои сообщения' произошла ошибка"
        )

    try:
        # Создание супергруппы "Изменение сообщения"
        message_changes_id = await create_message_changes(client)

        # Добавляем к каналу "Мои сообщения" группу для комментариев
        await link_my_messages_to_message_changes(client, my_messages_id, message_changes_id)
    except Exception as e:
        return CreateChatsResult(
            ok=False,
            error=e,
            error_message="При попытке создания и настройки группы 'Изменение сообщения' произошла ошибка"
        )

    try:
        # Работаем с ботом "MaksogramBot"
        await client.edit_folder(MaksogramBot.username, 1)  # Кидаем в архив
    except Exception as e:
        return CreateChatsResult(
            ok=False,
            error=e,
            error_message="При попытке создать папку с системными чатами произошла ошибка"
        )

    try:
        # Присоединяемся к каналу tgmaksim.ru и добавляем в папку
        await join_admin_channel(client)
    except Exception as e:
        return CreateChatsResult(
            ok=False,
            error=e,
            error_message=f"При попытке подписаться на канал @{CHANNEL} произошла ошибка"
        )

    try:
        # Создаем папку с чатами "Maksogram" и добавляем канал "Мои сообщения", канал "tgmaksim.ru" и бота "Maksogram"
        await create_dialog_filter(client, my_messages_id)
    except Exception as e:
        return CreateChatsResult(
            ok=False,
            error=e,
            error_message="При попытке создать и настроить папку с системными чатами произошла ошибка"
        )

    return CreateChatsResult(
        ok=True,
        my_messages=int(f"-100{my_messages_id}"),
        message_changes=int(f"-100{message_changes_id}")
    )