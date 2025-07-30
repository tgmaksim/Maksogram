from mg.config import CHANNEL

from typing import Optional
from datetime import timedelta
from mg.bot.types import support_link
from mg.core.types import MaksogramBot
from mg.client.types import CreateChatsResult
from mg.core.functions import resources_path, time_now

from telethon import TelegramClient
from telethon.tl.functions.account import UpdateNotifySettingsRequest
from telethon.utils import get_input_channel, get_input_peer, get_peer_id
from telethon.tl.functions.messages import GetDialogFiltersRequest, UpdateDialogFilterRequest
from telethon.errors.rpcerrorlist import (
    ChatInvalidError,
    UserRestrictedError,
    ChannelsTooMuchError,
)
from telethon.tl.types import (
    Updates,
    Channel,
    PeerChannel,
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


SYSTEM_DIALOG_FILTER_ID = 42


async def create_my_messages(client: TelegramClient) -> Channel:
    """
    Создает системный канал Мои сообщения и возвращает его идентификатор

    :param client: клиент
    :return: ``Channel``

    :raises ChannelsTooMuchError: у клиента слишком много чатов
    :raises UserRestrictedError: клиент не может создавать чаты из-за спамбана
    :raises ChatInvalidError: внутренняя ошибка Telegram API
    """

    my_messages: Updates = await client(CreateChannelRequest("Мои сообщения", "Мои сообщения", megagroup=False))
    input_channel = get_input_channel(my_messages.chats[0])

    await client(EditPhotoRequest(
        input_channel,
        InputChatUploadedPhoto(await client.upload_file(resources_path("my_messages.jpg"))))
    )
    await client.edit_folder(input_channel, 1)  # Кидаем в архив

    return my_messages.chats[0]


async def create_message_changes(client: TelegramClient) -> Channel:
    """
    Создает супергруппу для комментариев системного канала

    :param client: клиент
    :return: ``Channel``

    :raises ChannelsTooMuchError: у клиента слишком много чатов
    :raises UserRestrictedError: клиент не может создавать чаты из-за спамбана
    :raises ChatInvalidError: внутренняя ошибка Telegram API
    """

    message_changes: Updates = await client(CreateChannelRequest("Изменение сообщения", "Все изменения сообщений аккаунта", megagroup=True))
    input_channel = get_input_channel(message_changes.chats[0])

    await client(EditPhotoRequest(
        input_channel,
        InputChatUploadedPhoto(await client.upload_file(resources_path("edit_message.jpg"))))
    )
    await client(UpdateNotifySettingsRequest(
        InputNotifyPeer(get_input_peer(message_changes.chats[0])),
        InputPeerNotifySettings(show_previews=False, mute_until=time_now() + timedelta(days=1000))))
    await client.edit_folder(input_channel, 1)  # Кидаем в архив

    return message_changes.chats[0]


async def link_my_messages_to_message_changes(client: TelegramClient, my_messages_id: int, message_changes_id: int):
    """
    Связывает системную супергруппу для комментариев и системный канал

    :param client: TelegramClient
    :param my_messages_id: идентификатор системного канала
    :param message_changes_id: идентификатор системной супергруппу для комментариев
    """

    await client(SetDiscussionGroupRequest(
        get_input_channel(await client.get_input_entity(PeerChannel(channel_id=my_messages_id))),
        get_input_channel(await client.get_input_entity(PeerChannel(channel_id=message_changes_id)))
    ))


async def join_admin_channel(client: TelegramClient):
    """
    Присоединяется к каналу админа

    :param client: TelegramClient

    :raises ChannelsTooMuchError: у клиента слишком много чатов
    """

    input_channel = get_input_channel(await client.get_input_entity(CHANNEL))

    await client(JoinChannelRequest(input_channel))
    await client.edit_folder(input_channel, 1)  # Кидаем в архив


async def create_dialog_filter(client: TelegramClient, my_messages_id: int):
    """
    Создает папку Maksogram и добавляет системный канал Мои сообщения, канал админа и бота

    :param client: TelegramClient
    :param my_messages_id: идентификатор системного канала
    """

    title = TextWithEntities("Maksogram", [])
    my_messages = get_input_peer(await client.get_input_entity(PeerChannel(channel_id=my_messages_id)))
    admin_channel = get_input_peer(await client.get_input_entity(CHANNEL))
    bot = get_input_peer(await client.get_input_entity(MaksogramBot.username))

    await client(UpdateDialogFilterRequest(
        SYSTEM_DIALOG_FILTER_ID,
        DialogFilter(
            SYSTEM_DIALOG_FILTER_ID,
            title,
            [my_messages, admin_channel, bot],
            [],
            []
        )
    ))


async def update_dialog_filter(client: TelegramClient, my_messages_id: int):
    """
    Обновляет папку Maksogram, если она изменилась

    :param client: TelegramClient
    :param my_messages_id: идентификатор системного канала
    """

    title = TextWithEntities("Maksogram", [])
    my_messages = get_input_peer(await client.get_input_entity(PeerChannel(channel_id=my_messages_id)))
    admin_channel = get_input_peer(await client.get_input_entity(CHANNEL))
    bot = get_input_peer(await client.get_input_entity(MaksogramBot.username))

    system_dialog_filter = DialogFilter(
        SYSTEM_DIALOG_FILTER_ID,
        title,
        [my_messages, admin_channel, bot],
        [],
        []
    )
    dialog_filters = (await client(GetDialogFiltersRequest())).filters

    for dialog_filter in dialog_filters:
        if isinstance(dialog_filter, DialogFilter) and dialog_filter.id == SYSTEM_DIALOG_FILTER_ID:
            if dialog_filter != system_dialog_filter:  # Если папка изменилась
                await client(UpdateDialogFilterRequest(SYSTEM_DIALOG_FILTER_ID, system_dialog_filter))
            return

    await client(UpdateDialogFilterRequest(SYSTEM_DIALOG_FILTER_ID, system_dialog_filter))  # Папка удалена, восстанавливаем


async def create_chats(client: TelegramClient) -> CreateChatsResult:
    error = None
    error_message = None

    my_messages: Optional[Channel] = None
    message_changes: Optional[Channel] = None

    try:
        my_messages: Channel = await create_my_messages(client)
    except ChannelsTooMuchError as e:
        error, error_message = e, "Слишком много каналов, в которых вы состоите. Удалите не менее трех, чтобы Maksogram создал системные чаты"
    except UserRestrictedError as e:
        error, error_message = e, "Произошла ошибка при создании системных чатов из-за спамбана"
    except ChatInvalidError as e:
        error, error_message = e, f"Произошла внутренняя ошибка Telegram. Напишите {support_link}, мы поможем"
    except Exception as e:
        error, error_message = e, f"При попытке создать и настроить канал 'Мои сообщения' произошла неизвестная ошибка. Напишите {support_link}"

    if error:
        return CreateChatsResult(
            ok=False,
            error=error,
            error_message=error_message
        )

    try:
        message_changes: Channel = await create_message_changes(client)
    except ChannelsTooMuchError as e:
        error, error_message = e, "Слишком много каналов, в которых вы состоите. Удалите не менее двух, чтобы Maksogram создал системные чаты"
    except UserRestrictedError as e:
        error, error_message = e, "Произошла ошибка при создании системных чатов из-за спамбана"
    except ChatInvalidError as e:
        error, error_message = e, f"Произошла внутренняя ошибка Telegram. Напишите {support_link}, мы поможем"
    except Exception as e:
        error, error_message = e, f"При попытке создать и настроить канал 'Мои сообщения' произошла неизвестная ошибка. Напишите {support_link}"

    if error:
        return CreateChatsResult(
            ok=False,
            error=error,
            error_message=error_message
        )

    try:
        await link_my_messages_to_message_changes(client, my_messages.id, message_changes.id)
    except Exception as e:
        error, error_message = e, f"При попытке связать системный канал и группу для комментариев произошла неизвестная ошибка. Напишите {support_link}"

    if error:
        return CreateChatsResult(
            ok=False,
            error=error,
            error_message=error_message
        )

    try:
        await join_admin_channel(client)

        input_peer = get_input_peer(await client.get_input_entity(MaksogramBot.username))
        await client.edit_folder(input_peer, folder=1)
    except ChannelsTooMuchError as e:
        error, error_message = e, "Слишком много каналов, в которых вы состоите. Удалите не менее одного, чтобы Maksogram создал системные чаты"
    except Exception as e:
        error, error_message = e, f"При попытке подписаться на канал @{CHANNEL} произошла неизвестная ошибка. Напишите {support_link}"

    if error:
        return CreateChatsResult(
            ok=False,
            error=error,
            error_message=error_message
        )

    try:
        await create_dialog_filter(client, my_messages.id)
    except Exception as e:
        error, error_message = e, f"При попытке создать и настроить папку с системными чатами произошла неизвестная ошибка. Напишите {support_link}"

    if error:
        return CreateChatsResult(
            ok=False,
            error=error,
            error_message=error_message
        )

    return CreateChatsResult(
        ok=True,
        my_messages=get_peer_id(get_input_peer(my_messages, check_hash=False), add_mark=True),
        message_changes=get_peer_id(get_input_peer(message_changes, check_hash=False), add_mark=True)
    )