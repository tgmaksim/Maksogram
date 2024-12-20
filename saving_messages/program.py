import emoji
import string
import asyncio

from typing import Union
from telethon.tl.patched import Message
from . accounts import Account, accounts
from datetime import timedelta, datetime
from telethon import TelegramClient, events
from telethon.events.common import EventCommon
from telethon.errors import ChatForwardsRestrictedError
from core import MaksogramBot, Variables, security, time_now
from telethon.errors.rpcerrorlist import MsgIdInvalidError, AuthKeyInvalidError, BroadcastPublicVotersForbiddenError
from telethon.tl.functions.messages import GetCustomEmojiDocumentsRequest, GetMessagesRequest, GetDiscussionMessageRequest
from telethon.tl.types import (
    User,
    PeerUser,
    PeerChat,
    PeerChannel,
    ReactionEmoji,
    InputMessageID,
    MessageMediaGeo,
    UserStatusOnline,
    MessageMediaDice,
    MessageMediaPoll,
    UserStatusOffline,
    MessageMediaVenue,
    MessageMediaPhoto,
    ReactionCustomEmoji,
    MessageMediaGeoLive,
    MessageMediaDocument,
    DocumentAttributeAudio,
    DocumentAttributeVideo,
    MessageEntityCustomEmoji,
    DocumentAttributeSticker,
    DocumentAttributeFilename,
    DocumentAttributeAnimated,
    DocumentAttributeCustomEmoji,
)


class LastEvent:
    seconds: int = 1

    def __init__(self):
        self.__datetime = datetime(2009, 12, 9)

    def add(self, add_seconds: bool):
        self.__datetime = max([time_now(), self.__datetime]) + \
                          (timedelta(seconds=self.seconds) if add_seconds else timedelta(seconds=0))

    def get(self) -> datetime:
        return self.__datetime


class Program:
    __version__ = Variables.version

    async def sleep(self):
        difference = (time_now() - self.last_event.get()).total_seconds()
        self.last_event.add(not (difference > LastEvent.seconds))
        if difference < LastEvent.seconds:
            await asyncio.sleep(LastEvent.seconds - difference)

    @property
    def account(self) -> Account:
        return accounts[self.id]

    def __init__(self, client: TelegramClient, account_id: int):
        self.id = account_id
        self.name = self.account.name
        self.client = client
        self.last_event = LastEvent()

        self.status_users: dict[int, bool] = {user: None for user in self.account.status_users}  # {id: True} -> id в сети

        @client.on(events.NewMessage(func=self.initial_checking_event))
        @security()
        async def new_message(event: events.newmessage.NewMessage.Event):
            if await self.secondary_checking_event(event):
                await self.sleep()
                await self.new_message(event)
                if not isinstance(self.account.answering_machine, bool) and event.is_private:
                    auto_message = await self.answering_machine(event)
                    new_event = events.newmessage.NewMessage.Event(auto_message)
                    await self.new_message(new_event)

        @client.on(events.MessageEdited(func=self.initial_checking_event))
        @security()
        async def message_edited(event: events.messageedited.MessageEdited.Event):
            if await self.secondary_checking_event(event):
                await self.sleep()
                await self.message_edited(event)

        @client.on(events.MessageDeleted())
        @security()
        async def message_delete(event: events.messagedeleted.MessageDeleted.Event):
            if event.is_private is False:  # Сообщение удалено в группе, супергруппе или канале
                if event.chat_id not in self.account.added_chats:
                    return
            await self.sleep()
            await self.message_delete(event)

        @client.on(events.MessageRead(func=self.initial_checking_event, inbox=False))
        @security()
        async def message_read_outbox(event: events.messageread.MessageRead.Event):
            if await self.secondary_checking_event(event):
                await self.message_read(event, me=False)

        @client.on(events.MessageRead(func=self.initial_checking_event, inbox=True))
        @security()
        async def message_read_inbox(event: events.messageread.MessageRead.Event):
            if await self.secondary_checking_event(event):
                await self.message_read(event, me=True)

        @client.on(events.UserUpdate(
            chats=self.account.status_users,
            func=lambda event: isinstance(event.status, (UserStatusOnline, UserStatusOffline)))
        )
        @security()
        async def user_update(event: events.userupdate.UserUpdate.Event):
            await self.sleep()
            await self.user_update(event)

        @client.on(events.NewMessage(chats=[MaksogramBot.id], outgoing=True))
        @security()
        async def system_bot(event: events.newmessage.NewMessage.Event):
            await self.system_bot(event)

        @client.on(events.NewMessage(chats=[MaksogramBot.id], incoming=True, pattern=r'[\d\D]*#s'))
        @security()
        async def synchronize_status_users(_):
            client.list_event_handlers()[5][1].chats = set(self.account.status_users)

    def initial_checking_event(self, event: EventCommon) -> bool:
        return event.is_private and event.chat_id not in self.account.removed_chats or event.chat_id in self.account.added_chats

    async def secondary_checking_event(self, event: EventCommon) -> bool:
        if event.is_private:
            try:
                entity = await self.client.get_entity(event.chat_id)
            except ValueError:
                return False
            else:
                return not entity.bot
        return True

    # Получает название чата (имя контакта или название группы)
    async def chat_name(self, chat_id: int, /, my_name: str = "Избранное", unknown: str = "Неизвестный пользователь", is_hashtag: bool = False) -> str:
        def get_name(first_name: str, last_name: str = ""):
            text = f"{first_name} {last_name}" if last_name else first_name
            if is_hashtag:
                for letter in string.punctuation:
                    text = text.replace(letter, "")

            return text.replace(" ", "_") if is_hashtag else text

        if chat_id == self.id:
            name = get_name(my_name)
        else:
            try:
                chat = await self.client.get_entity(chat_id)
            except ValueError:
                name = get_name(unknown)
            else:
                if isinstance(chat, User):
                    name = get_name(chat.first_name, chat.last_name)
                else:
                    name = get_name(chat.title)
        return name

    # Получает id пользователя или группы
    def get_id(self, peer: Union[PeerUser, PeerChat, PeerChannel, None]) -> int:
        if peer is None:
            return self.id
        if isinstance(peer, PeerUser):
            return peer.user_id
        if isinstance(peer, PeerChat):
            return peer.chat_id
        if isinstance(peer, PeerChannel):
            return peer.channel_id
        raise TypeError("peer isn't instance PeerUser, PeerChat, PeerChannel or NoneType")

    # Считает длину сообщения
    @staticmethod
    def get_length_message(message: str) -> int:
        return message.__len__() + emoji.emoji_list(message).__len__()

    async def is_premium(self) -> bool:
        return (await self.client.get_me()).premium

    async def new_message(self, event: events.newmessage.NewMessage.Event):
        message: Message = event.message
        if self.get_id(message.from_id) == 777000:
            return

        try:
            saved_message = await self.client.forward_messages(self.account.my_messages, message)
        except (ChatForwardsRestrictedError, BroadcastPublicVotersForbiddenError):
            return

        name = await self.chat_name(event.chat_id, is_hashtag=True)

        title = f"Сообщение ({message.id})\n"
        chat_prefix = 'u' if event.is_private else 'c'
        chat_id = f"#{chat_prefix}{str(message.chat_id).replace('-', '_')} " if name != "Избранное" else ""
        name = f"#{name} "
        type_message = "#Исходящее " if self.get_id(message.from_id) == self.id else "#Входящее "
        media = ""
        if not message.media:
            media += "#Текст "
        if message.media:
            media += "#Медиа "
            if isinstance(message.media, MessageMediaPhoto):
                media += "#Фото "
            elif isinstance(message.media, MessageMediaDocument):
                type_media = list(map(type, message.media.document.attributes))
                if DocumentAttributeFilename in type_media:
                    media += "#Файл "
                    extensions = {
                        "wav": "#Звук ", "avi": "#Звук ", "mp3": "#Звук ", "m4a": "#Звук ", "jpg": "#Картинка ",
                        "png": "#Картинка ", "jpeg": "#Картинка ", "bmp": "#Картинка ", "doc": "#Word ",
                        "docx": "#Word ", "docm": "#Word ", "dot": "#Word ", "dotx": "#Word ", "exe": "#Программа ",
                        "apk": "#Android_приложение ", "flv": "#Видео ", "gif": "#Видео ", "mov": "#Видео ",
                        "mpeg": "#Видео ", "mp4": "#Видео ", "pdf": "#PDF ", "pptx": "#Презентация ",
                        "pptm": "#Презентация ", "ppt": "#Презентация ", "ppsx": "#Презентация ", "rar": "#Архив ",
                        "zip": "#Архив ", "7z": "#Архив ", "txt": "#Текстовый_документ ", "rtf": "#Текстовый_документ ",
                        "py": "#Python "
                    }
                    type_file = message.media.document.attributes[-1].file_name.split('.')
                    if type_file:
                        type_file = type_file[-1]
                        media += extensions.get(type_file, "")
                    else:
                        media += "#Бинарный "
                if type_media == [DocumentAttributeVideo, DocumentAttributeAudio]:
                    media += "#Видео " + "#Аудио " + "#Кружочек "
                elif DocumentAttributeVideo in type_media:
                    media += "#Видео " + "#Прямоугольное_видео "
                elif DocumentAttributeAudio in type_media:
                    media += "#Аудио "
                    if type_media == [DocumentAttributeAudio, DocumentAttributeFilename]:
                        media += "#Аудиофайл "
                    elif type_media == [DocumentAttributeAudio]:
                        media += "#ГС "
                elif DocumentAttributeSticker in type_media:
                    media += "#Стикер "
                    if DocumentAttributeFilename in type_media:
                        file_name = message.media.document.attributes[type_media.index(DocumentAttributeFilename)]
                        if file_name.file_name.split('.')[-1] == 'webp':
                            media += "#Статический_стикер "
                        elif file_name.file_name.split('.')[-1] == 'tgs':
                            media += "#Анимационный_стикер "
                elif isinstance(message.media.document.attributes[0], DocumentAttributeCustomEmoji):
                    media += "#Стикер "
                    media += "#Эмодзи "
                elif isinstance(message.media.document.attributes[0], DocumentAttributeAnimated):
                    media += "#Стикер "
                    media += "#Анимация "
            elif isinstance(message.media, MessageMediaGeo):
                media += "#Геопозиция "
            elif isinstance(message.media, MessageMediaPoll):
                media += "#Опрос "
            elif isinstance(message.media, MessageMediaVenue):
                media += "#ГеоПункт "
            elif isinstance(message.media, MessageMediaDice):
                media += "#Кубик "
            elif isinstance(message.media, MessageMediaGeoLive):
                media += "#Геолокация "
        if not event.is_private:
            is_read = 0
        elif self.get_id(message.from_id) == self.id and message.chat_id == self.id:
            is_read = 1
        elif self.get_id(message.from_id) == self.id:
            is_read = -1
        else:
            is_read = -2
        await self.account.insert_new_message(message.chat_id, message.id, saved_message.id, is_read)
        system_message = await self.client.send_message(
            self.account.my_messages, f"{title}{chat_id}{name}{media}{type_message}",
            reply_to=saved_message.id)
        system_message_id = (await self.client(GetDiscussionMessageRequest(self.account.my_messages, system_message.id))).messages[0].id
        await self.client.delete_messages(self.account.message_changes, system_message_id)

    # Проверка на изменение
    async def check_reactions(self, event: events.messageedited.MessageEdited.Event) -> bool:
        message: Message = event.message
        last_reactions = await self.account.get_last_reactions(message.chat_id, message.id)
        if last_reactions is None:
            return False
        now_reactions, _ = await self.get_reactions(event)
        if not last_reactions:
            return bool(now_reactions)
        if last_reactions != now_reactions:
            return True
        return False

    # Получение реакций сообщения в формате str
    async def get_reactions(self, event: events.messageedited.MessageEdited.Event, /, is_premium: bool = False) -> tuple[str, list]:
        message: Message = event.message
        if not message.reactions:
            return "", []
        reactions = "Изменены реакции:\n"
        entities = []
        if message.reactions.recent_reactions:  # Реакции и их "владельцы" (например, в личном чате)
            for reaction in message.reactions.recent_reactions:
                user_id = self.get_id(reaction.peer_id)
                peer = await self.chat_name(user_id, 'Я')
                if isinstance(reaction.reaction, ReactionEmoji):
                    reactions += f"{peer}: {reaction.reaction.emoticon}\n"
                elif isinstance(reaction.reaction, ReactionCustomEmoji):
                    document_id = reaction.reaction.document_id
                    document = (await self.client(GetCustomEmojiDocumentsRequest([document_id])))[0].to_dict()
                    emoticon = document['attributes'][1]['alt']
                    if is_premium:
                        reactions += f"{peer}: {emoticon}\n"
                        offset = self.get_length_message(reactions[:-len(emoticon) - 1])
                        entities.append(MessageEntityCustomEmoji(document_id=document_id, length=2, offset=offset))
                    else:
                        reactions += f"{peer}: premium'{emoticon}'\n"
        elif message.reactions.results:  # Реакции и их количество (например, в канале)
            for reaction in message.reactions.results:
                count = reaction.count
                if count == 1:
                    word_reactions = "реакция"
                elif count < 5:
                    word_reactions = "реакции"
                else:
                    word_reactions = "реакций"
                if isinstance(reaction.reaction, ReactionEmoji):
                    reactions += f"{reaction.reaction.emoticon}: {count} {word_reactions}\n"
                elif isinstance(reaction.reaction, ReactionCustomEmoji):
                    document_id = reaction.reaction.document_id
                    document = (await self.client(GetCustomEmojiDocumentsRequest([document_id])))[0].to_dict()
                    emoticon = document['attributes'][1]['alt']
                    if is_premium:
                        offset = self.get_length_message(reactions)
                        reactions += f"{emoticon}: {count} {word_reactions}\n"
                        entities.append(MessageEntityCustomEmoji(document_id=document_id, length=2, offset=offset))
                    else:
                        reactions += f"premium'{emoticon}': {count} {word_reactions}\n"
        else:
            return "", []
        return reactions, entities

    # Взаимодействие с изменением сообщения
    async def message_edited(self, event: events.messageedited.MessageEdited.Event):
        message: Message = event.message
        saved_message_id = await self.account.get_saved_message_id(message.chat_id, message.id)
        if saved_message_id is None:  # Если сообщение не было обработано ранее функцией new_message
            return
        if not event.is_private:
            return await self.message_edited_in_group(event, saved_message_id)
        if not await self.check_reactions(event):  # Если изменено содержание сообщения (текст или медиа)
            try:
                await self.client.send_message(self.account.my_messages, message, comment_to=saved_message_id)
            except MsgIdInvalidError:
                await self.client.send_message(self.account.my_messages, message, reply_to=saved_message_id)
        else:  # Изменение реакций
            is_premium = await self.is_premium()
            reactions, entities = await self.get_reactions(event, is_premium=is_premium)
            reactions_str, _ = await self.get_reactions(event)
            await self.account.update_reactions(reactions_str, message.chat_id, message.id)

            reactions = reactions if reactions else "Реакции убраны"
            try:
                await self.client.send_message(self.account.my_messages, reactions,
                                               formatting_entities=entities, comment_to=saved_message_id)
            except MsgIdInvalidError:
                await self.client.send_message(self.account.my_messages, reactions,
                                               formatting_entities=entities, reply_to=saved_message_id)

    async def message_edited_in_group(self, event: events.MessageEdited.Event, saved_message_id: int):
        reactions = await self.get_reactions(event, is_premium=await self.is_premium())
        try:
            await self.client.send_message(self.account.my_messages, event.message, comment_to=saved_message_id)
            if reactions[0]:
                await self.client.send_message(self.account.my_messages, reactions[0],
                                               formatting_entities=reactions[1], comment_to=saved_message_id)
        except MsgIdInvalidError:
            await self.client.send_message(self.account.my_messages, event.message, reply_to=saved_message_id)
            if reactions[0]:
                await self.client.send_message(self.account.my_messages, reactions[0],
                                               formatting_entities=reactions[1], reply_to=saved_message_id)

    # Получение данных об удаленном сообщении
    async def get_data_delete_message(self, chat_id: int, is_private: bool, message_id: int):
        if is_private:
            data = await self.account.get_private_message_by_id(message_id)
            if data is None: return
            chat_id, saved_message_id = data
        else:
            saved_message_id = await self.account.get_saved_message_id(chat_id, message_id)
            if saved_message_id is None: return
        return chat_id, saved_message_id

    # Взаимодействие с удалением сообщения
    async def message_delete(self, event: events.messagedeleted.MessageDeleted.Event):
        is_private = event.is_private is None
        chat_id = event.chat_id
        delete_ids = event.deleted_ids
        if len(delete_ids) > 5:
            message_data = await self.get_data_delete_message(chat_id, is_private, min(delete_ids))
            if message_data is None:
                await MaksogramBot.send_message(self.id, f"Произошло удаление {len(delete_ids)} сообщений")
                return
            chat_id, saved_message_id = message_data
            await self.account.delete_message(saved_message_id)
            try:
                await self.client.send_message(self.account.my_messages, f"Сообщение (и еще {len(delete_ids)-1}) удалено", comment_to=saved_message_id)
            except MsgIdInvalidError:
                await self.client.send_message(self.account.my_messages, f"Сообщение (и еще {len(delete_ids)-1}) удалено", reply_to=saved_message_id)
            if chat_id != self.id:
                link_to_message = f"t.me/c/{str(self.account.my_messages)[4:]}/{saved_message_id}"  # Сис. канал
                chat_name = await self.chat_name(chat_id, my_name="Я")
                if is_private:
                    await MaksogramBot.send_message(self.id, f"В чате {chat_name} удалены {len(delete_ids)} сообщений, например, "
                                                             f"<a href='{link_to_message}'>это</a>", parse_mode="HTML")
                else:
                    await MaksogramBot.send_message(self.id, f"Кто-то из {chat_name} удалил(а) {len(delete_ids)} сообщений, например, "
                                                    f"<a href='{link_to_message}'>это</a>", parse_mode="HTML")
            return
        for id in delete_ids:
            message_data = await self.get_data_delete_message(chat_id, is_private, id)
            if message_data is None: continue
            chat_id, saved_message_id = message_data
            await self.account.delete_message(saved_message_id)
            try:
                await self.client.send_message(self.account.my_messages, "Сообщение удалено", comment_to=saved_message_id)
            except MsgIdInvalidError:
                await self.client.send_message(self.account.my_messages, "Сообщение удалено", reply_to=saved_message_id)
            if chat_id != self.id:
                link_to_message = f"t.me/c/{str(self.account.my_messages)[4:]}/{saved_message_id}"  # Сис. канал
                chat_name = await self.chat_name(chat_id, my_name="Я")
                if is_private:
                    await MaksogramBot.send_message(
                        self.id, f"В чате с {chat_name} удалено <a href='{link_to_message}'>сообщение</a>", parse_mode="HTML")
                else:
                    await MaksogramBot.send_message(
                        self.id, f"Кто-то из {chat_name} удалил(а) <a href='{link_to_message}'>сообщение</a>", parse_mode="HTML")

    # Взаимодействие с прочтением сообщений
    async def message_read(self, event: events.messageread.MessageRead.Event, /, me: bool):
        if not event.is_private:
            return
        if me:  # Прочитано аккаунтом
            read_user = "Я"
        else:  # Прочитано другим пользователем
            read_user = await self.chat_name(self.get_id(event.original_update.peer))
        max_id = event.max_id
        chat_id = (await event.get_chat()).id
        saved_message_ids = await self.account.get_read_messages(chat_id, max_id, -2 if me else -1)
        if saved_message_ids is None:
            return
        for saved_message_id in saved_message_ids:
            await asyncio.sleep(0.5)
            try:
                await self.client.send_message(self.account.my_messages, f"{read_user} прочитал(а) сообщение", comment_to=saved_message_id)
            except MsgIdInvalidError:
                await self.client.send_message(self.account.my_messages, f"{read_user} прочитал(а) сообщение", reply_to=saved_message_id)

    # Взаимодействие с изменением статуса (в сети/офлайн)
    async def user_update(self, event: events.userupdate.UserUpdate.Event):
        status = isinstance(event.status, UserStatusOnline)
        if self.status_users.get(event.chat_id) == status:
            return

        self.status_users[event.chat_id] = status
        user = await self.chat_name(event.chat_id, my_name="Я")
        status_str = "в сети" if status else "вышел(а) из сети"
        await MaksogramBot.send_message(self.id, f"{user} {status_str}\n<a href='t.me/{MaksogramBot.username}?"
                                                 f"start=du{event.chat_id}'>Отключить для него</a>",
                                        parse_mode="HTML", disable_web_page_preview=True)

    # Обработка сообщений системному боту от аккаунта
    async def system_bot(self, event: events.newmessage.NewMessage.Event):
        message: Message = event.message
        if message.text.startswith("/check"):
            send = "<a href='tg://message?slug=ADmr7VSSZWFi'>напишите</a>"
            await MaksogramBot.send_message(self.id, f"Программа работает штатно! Если возникли проблемы, {send} "
                                                     "админу программы", parse_mode="html")
        elif message.text.startswith("/stop_prog"):
            await MaksogramBot.send_message(self.id, "Программа завершила выполнение!\n/start_prog - запустить заново")
            await asyncio.sleep(1)
            await self.account.off()
            await self.client.disconnect()
        elif message.text == "/am":
            self.account.answering_machine = True
            await MaksogramBot.send_message(self.id, "Отправьте сообщение, которым я отвечу собеседнику, "
                                                     "например: \"Я сейчас не могу ответить\"")
        elif self.account.answering_machine is True:
            self.account.answering_machine = message.id
            await MaksogramBot.send_message(self.id, "Отлично! Если кто-то напишет сообщение, пока вы не отключите "
                                                     "автоответчик, я отправлю от Вашего имени ответ")
        elif message.text.startswith("/am_stop"):
            self.account.answering_machine = False
            await MaksogramBot.send_message(self.id, "Автоответчик выключен!")

    async def answering_machine(self, event: events.newmessage.NewMessage.Event):
        message: Message = event.message
        await asyncio.sleep(0.3)
        copy_message_id = self.account.answering_machine
        copy_message = (await self.client(GetMessagesRequest(id=[InputMessageID(copy_message_id)]))).messages[0]
        await self.client.send_message(message.chat_id, copy_message)

    async def run_until_disconnected(self):
        await self.account.create_table()
        await MaksogramBot.send_system_message(f"SavingMessages v{self.__version__} для {self.name} запущен")
        try:
            await self.client.run_until_disconnected()
        except AuthKeyInvalidError:
            await self.account.off()
            await MaksogramBot.send_message(self.id, "Вы удалили сессию, она была необходима для работы программы!")
            await MaksogramBot.send_system_message(f"Удалена сессия у пользователя {self.name}")
