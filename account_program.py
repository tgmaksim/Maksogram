import datetime
import accounts
import aiosqlite

from accounts import Action
from telethon.tl.patched import Message
from telethon.sync import TelegramClient, events
from telethon.errors import ChatForwardsRestrictedError
from telethon.errors.rpcerrorlist import MessageNotModifiedError
from telethon.tl.functions.messages import GetCustomEmojiDocumentsRequest
from telethon.tl.types import (
    User,
    PeerUser,
    PeerChat,
    PhotoSize,
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


class account_start:
    def __init__(self, account: TelegramClient, my_account: accounts.account, status_users: list[int], action: Action):
        self.account_id = my_account.id
        self.account = account
        self.my_account = my_account

        self.name = action.name
        self.action = action

        self.status_users = {user: None for user in status_users}  # {id: True} -> id в сети

        self.db_path = accounts.path("resources/db.sqlite3")

        @self.account.on(events.NewMessage(func=lambda event: event.is_private or event.chat_id in self.my_account.chats_for_answer))
        async def new_message(event: events.newmessage.NewMessage.Event):
            if await self.check_chat(event):
                if self.action.number_new_message.get(event.chat_id):
                    self.action.number_new_message[event.chat_id] += 1
                else:
                    self.action.number_new_message[event.chat_id] = 1
                await self.new_message(event)

        @self.account.on(events.MessageEdited(func=lambda event: event.is_private or event.chat_id in self.my_account.chats_for_answer))
        async def message_edited(event: events.messageedited.MessageEdited.Event):
            if await self.check_chat(event):
                if self.action.number_edit_message.get(event.chat_id):
                    self.action.number_edit_message[event.chat_id] += 1
                else:
                    self.action.number_edit_message[event.chat_id] = 1
                await self.message_edited(event)

        @self.account.on(events.MessageDeleted())
        async def message_delete(event: events.messagedeleted.MessageDeleted.Event):
            if event.is_private is False:
                if event.chat_id not in self.my_account.chats_for_answer:
                    return
            if self.action.number_delete_message.get(event.chat_id):
                self.action.number_delete_message[event.chat_id] += 1
            else:
                self.action.number_delete_message[event.chat_id] = 1
            await self.message_delete(event)

        @self.account.on(events.MessageRead(func=lambda event: event.is_private or event.chat_id in self.my_account.chats_for_answer, inbox=False))
        async def message_read_outbox(event: events.messageread.MessageRead.Event):
            if await self.check_chat(event):
                if self.action.number_read_message.get(event.chat_id):
                    self.action.number_read_message[event.chat_id] += 1
                else:
                    self.action.number_read_message[event.chat_id] = 1
                await self.message_read(event, me=False)

        @self.account.on(events.MessageRead(func=lambda event: event.is_private or event.chat_id in self.my_account.chats_for_answer, inbox=True))
        async def message_read_inbox(event: events.messageread.MessageRead.Event):
            if await self.check_chat(event):
                if self.action.number_read_message.get(event.chat_id):
                    self.action.number_read_message[event.chat_id] += 1
                else:
                    self.action.number_read_message[event.chat_id] = 1
                await self.message_read(event, me=True)

        @self.account.on(events.UserUpdate(
            chats=list(self.status_users),
            func=lambda event: isinstance(event.status, (UserStatusOnline, UserStatusOffline)))
        )
        async def user_update(event: events.userupdate.UserUpdate.Event):
            if self.action.number_update_message.get(event.chat_id):
                self.action.number_update_message[event.chat_id] += 1
            else:
                self.action.number_update_message[event.chat_id] = 1
            await self.user_update(event)

    async def execute(self, sql: str, params: tuple = tuple()):
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(sql, params) as cur:
                result = await cur.fetchall()
            await conn.commit()
        return result

    # Проверяет: нужно ли взаимодействовать с действием (сообщение, изменение...) данного чата
    async def check_chat(self, event) -> bool:
        if event.is_private:
            user = await self.account.get_entity(event.chat_id)
            return not user.bot
        return event.chat_id in self.my_account.chats_for_answer

    # Получает название чата (имя контакта или название группы)
    async def chat_name(self, chat_id: int, /, my_name: str = "Избранное", unknown: str = "Неизвестный пользователь") -> str:
        if chat_id == self.account_id:
            name = my_name
        else:
            try:
                chat = await self.account.get_entity(chat_id)
            except ValueError:
                return unknown
            if isinstance(chat, User):
                name = chat.first_name + " " + (chat.last_name or "")
            else:
                name = chat.title
        return name

    # Получает id пользователя или группы
    def get_id(self, peer):
        if isinstance(peer, PeerUser):
            return peer.user_id
        if isinstance(peer, PeerChat):
            return peer.chat_id
        if isinstance(peer, PeerChannel):
            return peer.channel_id
        return self.my_account.id

    async def new_message(self, event: events.newmessage.NewMessage.Event):
        message: Message = event.message
        if message.text == f"exit()":
            await self.account.send_message(event.chat_id, "Команда разработчика активирована")
            await self.account.disconnect()
            return

        if message.text == "1" and message.chat_id == self.my_account.id:
            await self.account.send_message(event.chat_id, "Работает!")
            return

        _name = await self.chat_name(event.chat_id)

        message_id = f"#message{str(abs(message.chat_id))} "
        chat_id = f"#chat{str(abs(message.chat_id))} "
        name = f"#{_name} "
        type_message = "#Исходящее " if self.get_id(message.from_id) == self.my_account.id else "#Входящее "
        media = ""
        if message.message:
            media += "#Текст "
        if message.media:
            media += "#Медиа "
            if isinstance(message.media, MessageMediaPhoto):
                media += "#Фото "
            elif isinstance(message.media, MessageMediaDocument):
                type_media = list(map(type, message.media.document.attributes))
                if type_media == [DocumentAttributeFilename]:
                    media += "#Файл "
                    type_audio = "#Звук "
                    type_photo = "#Картинка "
                    type_word = "#Word "
                    type_program_windows = "#Программа "
                    type_program_android = "#Android_приложение "
                    type_video = "#Видео "
                    type_pdf = "#PDF "
                    type_pres = "#Презентация "
                    type_archive = "#Архив "
                    type_text = "#Текстовый_документ"
                    type_python = "#Python "
                    extensions = {
                        "wav": type_audio, "avi": type_audio, "mp3": type_audio, "m4a": type_audio,
                        "jpg": type_photo, "png": type_photo, "jpeg": type_photo, "bmp": type_photo,
                        "doc": type_word, "docx": type_word, "docm": type_word, "dot": type_word, "dotx": type_word,
                        "exe": type_program_windows,
                        "apk": type_program_android,
                        "flv": type_video, "gif": type_video, "mov": type_video, "mpeg": type_video, "mp4": type_video,
                        "pdf": type_pdf,
                        "pptx": type_pres, "pptm": type_pres, "ppt": type_pres, "ppsx": type_pres,
                        "rar": type_archive, "zip": type_archive, "7z": type_archive,
                        "txt": type_text, "rtf": type_text,
                        "py": type_python
                    }
                    type_file = message.media.document.attributes[0].file_name.split('.')
                    if type_file:
                        type_file = type_file[-1]
                        media += extensions.get(type_file, "")
                    else:
                        media += "#Бинарный "
                if DocumentAttributeVideo in type_media:
                    media += "#Видео "
                    if type_media == [DocumentAttributeVideo, DocumentAttributeAudio, PhotoSize]:
                        media += "#Кружочек "
                    elif type_media == [DocumentAttributeVideo, PhotoSize]:
                        media += "#Прямоугольное_видео "
                if DocumentAttributeSticker in type_media:
                    media += "#Стикер "
                    if DocumentAttributeFilename in type_media:
                        file_name = message.media.document.attributes[type_media.index(DocumentAttributeFilename)]
                        if file_name.file_name.split('.')[-1] == 'webp':
                            media += "#Статический_стикер "
                        elif file_name.file_name.split('.')[-1] == 'tgs':
                            media += "#Анимационный_стикер "
                elif DocumentAttributeAudio in type_media:
                    media += "#Аудио "
                    if type_media == [DocumentAttributeAudio, DocumentAttributeFilename]:
                        media += "#Аудиофайл "
                    elif type_media == [DocumentAttributeAudio]:
                        media += "#ГС "
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
        try:
            send_message = await self.account.forward_messages(self.my_account.my_messages, message)
        except ChatForwardsRestrictedError:
            return
        await self.execute(f"INSERT INTO '{self.account_id}_messages' VALUES(?, ?, ?, ?, ?)",
                           (message.chat_id, message.id, send_message.id, 0, ""))
        await self.account.send_message(self.my_account.my_messages,
                                        f"{message_id}{chat_id}{name}{media}{type_message}#Сообщение",
                                        reply_to=send_message.id)

    # Проверка на изменение
    async def check_reactions(self, event: events.messageedited.MessageEdited.Event) -> bool:
        message: Message = event.message
        reactions = await self.execute(f"SELECT reactions FROM '{self.account_id}_messages' WHERE "
                                       f"chat_id=? AND message_id=?", (message.chat_id, message.id))
        if not reactions:
            return False
        reactions = reactions[0][0]
        if not reactions:
            return bool(await self.get_reactions(event))
        if reactions != await self.get_reactions(event):
            return True
        return False

    # Получение реакций сообщения в формате str
    async def get_reactions(self, event: events.messageedited.MessageEdited.Event) -> str:
        message: Message = event.message
        if not message.reactions:
            return ""
        reactions = "Изменены реакции:\n"
        if message.reactions.recent_reactions:  # Реакции и их "владельцы" (например, в личном чате)
            for reaction in message.reactions.recent_reactions:
                user_id = self.get_id(reaction.peer_id)
                peer = await self.chat_name(user_id, 'Я')
                if isinstance(reaction.reaction, ReactionEmoji):
                    reactions += f"{peer}: {reaction.reaction.emoticon}\n"
                elif isinstance(reaction.reaction, ReactionCustomEmoji):
                    document_id = reaction.reaction.document_id
                    document = (await self.account(GetCustomEmojiDocumentsRequest([document_id])))[0].to_dict()
                    emoticon = document['attributes'][1]['alt']
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
                    document = (await self.account(GetCustomEmojiDocumentsRequest([document_id])))[0].to_dict()
                    emoticon = document['attributes'][1]['alt']
                    reactions += f"premium'{emoticon}': {count} {word_reactions}\n"
        else:
            return ""
        return reactions

    # Взаимодействие с изменением сообщения
    async def message_edited(self, event: events.messageedited.MessageEdited.Event):
        message: Message = event.message
        id = await self.execute(f"SELECT forward_message_id FROM '{self.account_id}_messages' "
                                f"WHERE chat_id=? AND message_id=?", (message.chat_id, message.id))
        if not id:  # Если сообщение не было обработано функцией new_message
            return
        id = int(id[0][0])
        if not await self.check_reactions(event):  # Если изменено содержание сообщения (текст или медиа)
            await self.account.send_message(self.my_account.my_messages, message, comment_to=id)
        else:  # Изменение реакций
            reactions = await self.get_reactions(event)
            await self.execute(
                f"UPDATE '{self.account_id}_messages' SET reactions=? WHERE chat_id=? AND message_id=?",
                (reactions, message.chat_id, message.id))

            reactions = reactions if reactions else "Реакции убраны"
            await self.account.send_message(self.my_account.my_messages, reactions, comment_to=id)

    # Взаимодействие с удалением сообщения
    async def message_delete(self, event: events.messagedeleted.MessageDeleted.Event):
        is_private = event.is_private is None
        chat_id = event.chat_id
        delete_ids = event.deleted_ids
        for id in delete_ids:
            if is_private:
                message = await self.execute("SELECT chat_id, forward_message_id "
                                             f"FROM '{self.account_id}_messages' WHERE message_id=?", (id,))
            else:
                message = await self.execute(f"SELECT forward_message_id FROM '{self.account_id}_messages' "
                                             "WHERE chat_id=? AND message_id=?", (chat_id, id))
            if not message:
                continue
            if is_private:
                chat_id, forward_message_id = message[0]
            else:
                forward_message_id = message[0][0]
            await self.execute(f"DELETE FROM '{self.account_id}_messages' WHERE message_id=?", (id,))
            await self.account.send_message(self.my_account.my_messages, "Сообщение удалено",
                                            comment_to=forward_message_id)
            if chat_id != self.account_id:
                link_to_message = f"t.me/c/{str(self.my_account.my_messages)[4:]}/{forward_message_id}"  # Сис. канал
                chat_name = await self.chat_name(chat_id, "Я")
                await accounts.bot_send_message(self.account_id,
                                                f"{chat_name} удалил(а) <a href='{link_to_message}'>сообщение</a>",
                                                parse_mode="HTML")
                await self.account.pin_message(self.my_account.my_messages, forward_message_id)

    # Взаимодействие с прочтением сообщений
    async def message_read(self, event: events.messageread.MessageRead.Event, /, me: bool):
        if me:  # Прочитано аккаунтом
            read_user = "Я"
        else:  # Прочитано другим пользователем
            read_user = await self.chat_name(self.get_id(event.original_update.peer))
        message_id = event.max_id
        await self.execute(f"UPDATE '{self.account_id}_messages' SET read=? WHERE message_id=?", (1, message_id))
        forward_message_id = await self.execute(f"SELECT forward_message_id FROM '{self.account_id}_messages' "
                                                f"WHERE message_id=?", (message_id,))
        if not forward_message_id:
            return
        forward_message_id = int(forward_message_id[0][0])
        await self.account.send_message(self.my_account.my_messages, f"{read_user} прочитал(а) сообщение",
                                        comment_to=forward_message_id)

    async def user_update(self, event: events.userupdate.UserUpdate.Event):
        status = isinstance(event.status, UserStatusOnline)
        if self.status_users.get(event.chat_id) == status:
            return

        if event.chat_id == self.account_id:
            if status:
                status_str = "в сети"
            else:
                was_online: datetime.datetime = event.status.was_online + datetime.timedelta(hours=6)
                day = was_online.day
                days = f"{day} числа"
                hour = was_online.hour
                minute = was_online.minute
                status_str = f"был(а) {days} в {hour}:{minute}"
            try:
                await self.account.edit_message(self.my_account.chanel_status,
                                                self.my_account.message_id_chanel_status, status_str)
            except MessageNotModifiedError:
                pass

        id = f"#user{event.chat_id} #chat{event.chat_id} "
        name = await self.chat_name(event.chat_id, my_name="Я")
        type_status = ["Офлайн", "Онлайн"][status]
        self.status_users[event.chat_id] = status
        await self.account.send_message(self.my_account.my_messages,
                                        f"{name} {type_status}\n{id}#{name} #{type_status} #Статус")

    async def run_until_disconnected(self):
        await self.execute(
            f"CREATE TABLE IF NOT EXISTS '{self.account_id}_messages' "
            f"(chat_id INTEGER, message_id INTEGER, forward_message_id INTEGER, read INTEGER, reactions TEXT)")
        await accounts.bot_send_message(5128609241, f"SavingAllMessages ({self.name}) запущен")
        await self.account.run_until_disconnected()
