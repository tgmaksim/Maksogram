import os
import emoji
import string
import asyncio

from modules.calculator import main as calculator
from modules.qrcode import create as create_qrcode

from typing import Union
from telethon.tl.patched import Message
from datetime import timedelta, datetime
from telethon import TelegramClient, events
from telethon.events.common import EventCommon
from telethon.errors import ChatForwardsRestrictedError
from telethon.tl.functions.account import UpdateStatusRequest
from telethon.tl.functions.messages import GetCustomEmojiDocumentsRequest
from core import db, MaksogramBot, Variables, security, time_now, count_avatars, account_off
from telethon.errors.rpcerrorlist import MsgIdInvalidError, AuthKeyInvalidError, BroadcastPublicVotersForbiddenError, AuthKeyUnregisteredError
from telethon.tl.types import (
    User,
    PeerUser,
    PeerChat,
    PeerChannel,
    ReactionEmoji,
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
    DocumentAttributeSticker,
    DocumentAttributeFilename,
    DocumentAttributeAnimated,
    DocumentAttributeCustomEmoji,
)
from telethon.tl.types import (
    MessageEntityUrl,
    MessageEntityBold,
    MessageEntityItalic,
    MessageEntityStrike,
    MessageEntitySpoiler,
    MessageEntityTextUrl,
    MessageEntityUnderline,
    MessageEntityBlockquote,
    MessageEntityCustomEmoji,
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

    def __init__(self, client: TelegramClient, account_id: int, status_users: list[int]):
        self.id = account_id
        self.client = client
        self.last_event = LastEvent()

        self.status_users: dict[int, bool] = {user: None for user in status_users}  # {id: True} -> id в сети

        @client.on(events.NewMessage(func=self.initial_checking_event))
        @security()
        async def new_message(event: events.newmessage.NewMessage.Event):
            if await self.secondary_checking_event(event):
                await self.sleep()
                await self.new_message(event)
                await self.client(UpdateStatusRequest(offline=True))
                if await db.fetch_one(f"SELECT answering_machine['main'] FROM accounts WHERE id={self.id}", one_data=True) \
                        and event.is_private and (not event.message.from_id or event.message.from_id.user_id != self.id) \
                        and not await db.fetch_one(f"SELECT answering_machine['sending'] @> '{event.chat_id}' "
                                                   f"FROM accounts WHERE id={self.id}", one_data=True):
                    auto_message = await self.answering_machine(event)
                    new_event = events.newmessage.NewMessage.Event(auto_message)
                    await self.new_message(new_event, auto_answer=True)

        @client.on(events.MessageEdited(func=self.initial_checking_event))
        @security()
        async def message_edited(event: events.messageedited.MessageEdited.Event):
            if await self.secondary_checking_event(event):
                await self.sleep()
                await self.message_edited(event)
                await self.client(UpdateStatusRequest(offline=True))

        @client.on(events.MessageDeleted())
        @security()
        async def message_delete(event: events.messagedeleted.MessageDeleted.Event):
            if event.is_private is False:  # Сообщение удалено в группе, супергруппе или канале
                if not await db.fetch_one(f"SELECT added_chats @> '{event.chat_id}' FROM accounts WHERE id={self.id}", one_data=True):
                    return
            await self.sleep()
            await self.message_delete(event)
            await self.client(UpdateStatusRequest(offline=True))

        @client.on(events.MessageRead(func=self.initial_checking_event, inbox=False))
        @security()
        async def message_read_outbox(event: events.messageread.MessageRead.Event):
            if await self.secondary_checking_event(event):
                await self.message_read(event, me=False)
                await self.client(UpdateStatusRequest(offline=True))

        @client.on(events.MessageRead(func=self.initial_checking_event, inbox=True))
        @security()
        async def message_read_inbox(event: events.messageread.MessageRead.Event):
            if await self.secondary_checking_event(event):
                await self.message_read(event, me=True)
                await self.client(UpdateStatusRequest(offline=True))

        @client.on(events.UserUpdate(
            chats=self.status_users,
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

    async def initial_checking_event(self, event: EventCommon) -> bool:
        return not event.chat_id or event.is_private and \
            not await db.fetch_one(f"SELECT removed_chats @> '{event.chat_id}' FROM accounts WHERE id={self.id}", one_data=True) or \
            await db.fetch_one(f"SELECT added_chats @> '{event.chat_id}' FROM accounts WHERE id={self.id}", one_data=True)

    async def secondary_checking_event(self, event: EventCommon) -> bool:
        if event.is_private:
            try:
                entity = await self.client.get_entity(event.chat_id)
            except ValueError:
                return False
            else:
                return not entity.bot and entity.id != 777000
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
    async def get_id(self, peer: Union[PeerUser, PeerChat, PeerChannel, None]):
        if peer is None:
            return self.id
        if isinstance(peer, PeerUser):
            return peer.user_id
        if isinstance(peer, PeerChat):
            return peer.chat_id
        if isinstance(peer, PeerChannel):
            return peer.channel_id
        name = await db.fetch_one(f"SELECT name FROM accounts WHERE id={self.id}", one_data=True)
        await MaksogramBot.send_system_message(f"⚠️ Ошибка ⚠️\n\nТип peer - {peer.__class__.__name__} ({name})")
        raise TypeError("peer isn't instance PeerUser, PeerChat, PeerChannel or NoneType")

    # Считает длину сообщения
    @staticmethod
    def get_length_message(message: str) -> int:
        return message.__len__() + emoji.emoji_list(message).__len__()

    async def is_premium(self) -> bool:
        return (await self.client.get_me()).premium

    @property
    def my_messages(self):
        return db.fetch_one(f"SELECT my_messages FROM accounts WHERE id={self.id}", one_data=True)

    async def new_message(self, event: events.newmessage.NewMessage.Event, auto_answer: bool = False):
        message: Message = event.message
        text = message.text.lower()

        if await db.fetch_one(f"SELECT modules['qrcode'] FROM accounts WHERE id={self.id}", one_data=True) \
                and ("создай" in text or "сгенерируй" in text or "qr" in text or "создать" in text or "сгенерировать" in text) \
                and len(message.entities) == 1 and isinstance(message.entities[0], MessageEntityUrl):  # Генератор Qr-кодов в чате
            link = message.text[message.entities[0].offset:message.entities[0].length+message.entities[0].offset]
            qr = create_qrcode(link)
            await message.edit("Maksogram в чате (qr-код)", file=qr)
            return os.remove(qr)

        module = ""
        if await db.fetch_one(f"SELECT modules['calculator'] FROM accounts WHERE id={self.id}", one_data=True) and \
                not message.media and text[-1] == "=" and text.find("\n") == -1:  # Калькулятор в чате
            request = calculator(text[:-1])
            if request:
                await self.client.edit_message(message.chat_id, message, request)
                module = "#Калькулятор"

        try:
            saved_message = await self.client.forward_messages(await self.my_messages, message)
        except (ChatForwardsRestrictedError, BroadcastPublicVotersForbiddenError):
            return

        name = await self.chat_name(event.chat_id, is_hashtag=True)

        title = f"Сообщение ({message.id})\n"
        chat_prefix = 'u' if event.is_private else 'c'
        chat_id = f"#{chat_prefix}{str(message.chat_id).replace('-', '_')} " if name != "Избранное" else ""
        name = f"#{name} "
        type_message = "#Исходящее " if await self.get_id(message.from_id) == self.id else "#Входящее "
        auto_answer = "#Автоответ " if auto_answer else ""
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
        elif await self.get_id(message.from_id) == self.id and message.chat_id == self.id:
            is_read = 1
        elif await self.get_id(message.from_id) == self.id:
            is_read = -1
        else:
            is_read = -2
        await db.execute(f"INSERT INTO \"{self.id}_messages\" VALUES "
                         f"({message.chat_id}, {message.id}, {saved_message.id}, {is_read}, '')")
        await self.client.send_message(await self.my_messages, f"{title}{chat_id}{name}{media}{type_message}{auto_answer}{module}",
                                       reply_to=saved_message.id)

    # Проверка на изменение
    async def check_reactions(self, event: events.messageedited.MessageEdited.Event) -> bool:
        message: Message = event.message
        last_reactions = await db.fetch_one(f"SELECT reactions FROM \"{self.id}_messages\" "
                                            f"WHERE chat_id={message.chat_id} AND message_id={message.id}", one_data=True)
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
                user_id = await self.get_id(reaction.peer_id)
                peer = await self.chat_name(user_id, my_name="Я")
                if isinstance(reaction.reaction, ReactionEmoji):
                    reactions += f"{peer}: {reaction.reaction.emoticon}\n"
                elif isinstance(reaction.reaction, ReactionCustomEmoji):
                    document_id = reaction.reaction.document_id
                    document = (await self.client(GetCustomEmojiDocumentsRequest([document_id])))[0].to_dict()
                    emoticon = document['attributes'][1]['alt']
                    if is_premium:
                        reactions += f"{peer}: {emoticon}\n"
                        offset = self.get_length_message(reactions[:-len(emoticon)-1])
                        entities.append(MessageEntityCustomEmoji(document_id=document_id, length=2, offset=offset))
                    else:
                        reactions += f"{peer}: premium{emoticon}\n"
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
                        reactions += f"premium{emoticon}: {count} {word_reactions}\n"
        else:
            return "", []
        return reactions, entities

    # Взаимодействие с изменением сообщения
    async def message_edited(self, event: events.messageedited.MessageEdited.Event):
        message: Message = event.message
        saved_message_id: int = await db.fetch_one(f"SELECT saved_message_id FROM \"{self.id}_messages\" "
                                                   f"WHERE chat_id={message.chat_id} AND message_id={message.id}", one_data=True)
        if saved_message_id is None:  # Если сообщение не было обработано ранее функцией new_message
            return
        if not event.is_private:
            return await self.message_edited_in_group(event, saved_message_id)
        if not await self.check_reactions(event):  # Если изменено содержание сообщения (текст или медиа)
            try:
                await self.client.send_message(await self.my_messages, message, comment_to=saved_message_id)
            except MsgIdInvalidError:
                await self.client.send_message(await self.my_messages, message, reply_to=saved_message_id)
        else:  # Изменение реакций
            is_premium = await self.is_premium()
            reactions, entities = await self.get_reactions(event, is_premium=is_premium)
            reactions_str, _ = await self.get_reactions(event)
            await db.execute(f"UPDATE \"{self.id}_messages\" SET reactions='{reactions_str}' "
                             f"WHERE chat_id={message.chat_id} AND message_id={message.id}")
            reactions = reactions if reactions else "Реакции убраны"
            try:
                await self.client.send_message(await self.my_messages, reactions,
                                               formatting_entities=entities, comment_to=saved_message_id)
            except MsgIdInvalidError:
                await self.client.send_message(await self.my_messages, reactions,
                                               formatting_entities=entities, reply_to=saved_message_id)

    async def message_edited_in_group(self, event: events.MessageEdited.Event, saved_message_id: int):
        reactions = await self.get_reactions(event, is_premium=await self.is_premium())
        try:
            await self.client.send_message(await self.my_messages, event.message, comment_to=saved_message_id)
            if reactions[0]:
                await self.client.send_message(await self.my_messages, reactions[0],
                                               formatting_entities=reactions[1], comment_to=saved_message_id)
        except MsgIdInvalidError:
            await self.client.send_message(await self.my_messages, event.message, reply_to=saved_message_id)
            if reactions[0]:
                await self.client.send_message(await self.my_messages, reactions[0],
                                               formatting_entities=reactions[1], reply_to=saved_message_id)

    # Получение данных об удаленном сообщении
    async def get_data_delete_message(self, chat_id: int, is_private: bool, message_id: int):
        if is_private:
            data = await db.fetch_one(f"SELECT chat_id, saved_message_id FROM \"{self.id}_messages\" "
                                      f"WHERE message_id={message_id} AND chat_id>-10000000000")
            if data is None: return
            chat_id, saved_message_id = data.values()
        else:
            saved_message_id = await db.fetch_one(f"SELECT saved_message_id FROM \"{self.id}_messages\" "
                                                  f"WHERE message_id={message_id}", one_data=True)
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
            await db.execute(f"DELETE FROM \"{self.id}_messages\" WHERE saved_message_id={saved_message_id}")
            try:
                await self.client.send_message(await self.my_messages, f"Сообщение (и еще {len(delete_ids)-1}) удалено", comment_to=saved_message_id)
            except MsgIdInvalidError:
                await self.client.send_message(await self.my_messages, f"Сообщение (и еще {len(delete_ids)-1}) удалено", reply_to=saved_message_id)
            if chat_id != self.id:
                link_to_message = f"t.me/c/{str(await self.my_messages)[4:]}/{saved_message_id}"  # Сис. канал
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
            await db.execute(f"DELETE FROM \"{self.id}_messages\" WHERE saved_message_id={saved_message_id}")
            try:
                await self.client.send_message(await self.my_messages, "Сообщение удалено", comment_to=saved_message_id)
            except MsgIdInvalidError:
                await self.client.send_message(await self.my_messages, "Сообщение удалено", reply_to=saved_message_id)
            if chat_id != self.id:
                link_to_message = f"t.me/c/{str(await self.my_messages)[4:]}/{saved_message_id}"  # Сис. канал
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
            read_user = await self.chat_name(await self.get_id(event.original_update.peer))
        max_id = event.max_id
        chat_id = (await event.get_chat()).id
        if await db.fetch_one(f"SELECT status_users['{chat_id}']['reading'] FROM accounts WHERE id={self.id}", one_data=True) \
                and not me:
            await db.execute(f"UPDATE accounts SET status_users['{chat_id}']['reading']='false' WHERE id={self.id}")
            await MaksogramBot.send_message(self.id, f"🌐 {read_user} прочитал сообщение", reply_markup=MaksogramBot.IMarkup(
                inline_keyboard=[[MaksogramBot.IButton(text="Настройки", callback_data=f"status_user_menu{event.chat_id}")]]))
        saved_message_ids: list[int] = await db.fetch_all(
            f"SELECT saved_message_id FROM \"{self.id}_messages\" WHERE is_read={-2 if me else -1} "
            f"AND chat_id={chat_id} AND message_id<={max_id}", one_data=True)
        if saved_message_ids is None:
            return
        await db.execute(f"UPDATE \"{self.id}_messages\" SET is_read='1' WHERE chat_id={chat_id} AND message_id<={max_id}")
        for saved_message_id in saved_message_ids:
            await asyncio.sleep(0.5)
            try:
                await self.client.send_message(await self.my_messages, f"{read_user} прочитал(а) сообщение", comment_to=saved_message_id)
            except MsgIdInvalidError:
                await self.client.send_message(await self.my_messages, f"{read_user} прочитал(а) сообщение", reply_to=saved_message_id)

    # Взаимодействие с изменением статуса (в сети/офлайн)
    async def user_update(self, event: events.userupdate.UserUpdate.Event):
        status = isinstance(event.status, UserStatusOnline)
        if self.status_users.get(event.chat_id) == status:
            return
        self.status_users[event.chat_id] = status
        function = await db.fetch_one(f"SELECT status_users['{event.chat_id}']['online'] AS online, "
                                      f"status_users['{event.chat_id}']['offline'] AS offline FROM accounts WHERE id={self.id}")
        online = function['online'] and status is True
        offline = function['offline'] and status is False
        if online or offline:
            user = await self.chat_name(event.chat_id, my_name="Я")
            status_str = "в сети" if status else "вышел(а) из сети"
            await MaksogramBot.send_message(self.id, f"🌐 {user} {status_str}", reply_markup=MaksogramBot.IMarkup(
                inline_keyboard=[[MaksogramBot.IButton(text="Настройки", callback_data=f"status_user_menu{event.chat_id}")]]))

    # Обработка сообщений системному боту от аккаунта
    async def system_bot(self, event: events.newmessage.NewMessage.Event):
        pass

    async def answering_machine(self, event: events.newmessage.NewMessage.Event):
        message: Message = event.message
        answer = await db.fetch_one(f"SELECT answering_machine->'variants'->(SELECT answering_machine['main']::text "
                                    f"FROM accounts WHERE id={self.id}) FROM accounts WHERE id={self.id}", one_data=True)
        if not answer: return
        await db.execute(f"UPDATE accounts SET answering_machine['sending']=answering_machine['sending'] || '{message.chat_id}' "
                         f"WHERE id={self.id}")
        entities = []
        for entity in answer['entities']:
            match entity['type']:
                case "bold":
                    entities.append(MessageEntityBold(entity['offset'], entity['length']))
                case "italic":
                    entities.append(MessageEntityItalic(entity['offset'], entity['length']))
                case "underline":
                    entities.append(MessageEntityUnderline(entity['offset'], entity['length']))
                case "strikethrough":
                    entities.append(MessageEntityStrike(entity['offset'], entity['length']))
                case "spoiler":
                    entities.append(MessageEntitySpoiler(entity['offset'], entity['length']))
                case "blockquote":
                    entities.append(MessageEntityBlockquote(entity['offset'], entity['length']))
                case "text_link":
                    entities.append(MessageEntityTextUrl(entity['offset'], entity['length'], entity['url']))
                case "custom_emoji":
                    entities.append(MessageEntityCustomEmoji(entity['offset'], entity['length'], document_id=int(entity['custom_emoji_id'])))
        return await self.client.send_message(message.chat_id, answer['text'], formatting_entities=entities)

    async def new_avatar(self):
        while await db.fetch_one(f"SELECT is_started FROM accounts WHERE id={self.id}", one_data=True):
            for user_id, user in (await db.fetch_one(f"SELECT avatars FROM accounts WHERE id={self.id}", one_data=True)).items():
                count = await count_avatars(self.id, int(user_id))
                if user['count'] > count:
                    await MaksogramBot.send_message(
                        self.id, f"📸 <b><a href='tg://user?id={user_id}'>{user['name']}</a></b> удалил(а) аватарку",
                        reply_markup=MaksogramBot.IMarkup(
                            inline_keyboard=[[MaksogramBot.IButton(text="🔴 Выключить", callback_data=f"avatar_del{user_id}")]]),
                        parse_mode="html")
                elif user['count'] < count:
                    await MaksogramBot.send_message(
                        self.id, f"📸 <b><a href='tg://user?id={user_id}'>{user['name']}</a></b> добавил(а) аватарку",
                        reply_markup=MaksogramBot.IMarkup(
                            inline_keyboard=[[MaksogramBot.IButton(text="🔴 Выключить", callback_data=f"avatar_del{user_id}")]]),
                        parse_mode="html")
                else: continue
                await db.execute(f"UPDATE accounts SET avatars['{user_id}']['count']='{count}' WHERE id={self.id}")
            await asyncio.sleep(5*60)

    async def run_until_disconnected(self):
        await db.execute(f"CREATE TABLE IF NOT EXISTS \"{self.id}_messages\" (chat_id BIGINT NOT NULL, message_id BIGINT NOT NULL, "
                           "saved_message_id BIGINT NOT NULL, is_read INTEGER NOT NULL, reactions TEXT NOT NULL)")
        name = await db.fetch_one(f"SELECT name FROM accounts WHERE id={self.id}", one_data=True)
        await MaksogramBot.send_system_message(f"SavingMessages v{self.__version__} для {name} запущен")
        asyncio.get_running_loop().create_task(self.new_avatar())
        try:
            await self.client.run_until_disconnected()
        except (AuthKeyInvalidError, AuthKeyUnregisteredError):
            await MaksogramBot.send_message(self.id, "Вы удалили сессию, она была необходима для работы программы!")
            await MaksogramBot.send_system_message(f"Удалена сессия у пользователя {name}")
            phone_number = await db.fetch_one(f"SELECT phone_number FROM accounts WHERE id={self.id}", one_data=True)
            await account_off(self.id, f"+{phone_number}")
