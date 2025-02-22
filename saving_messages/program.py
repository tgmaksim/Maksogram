import os
import emoji
import asyncio

from modules.calculator import main as calculator
from modules.qrcode import create as create_qrcode
from modules.audio_transcription import main as audio_transcription

from io import BytesIO
from typing import Union
from telethon.tl.patched import Message
from datetime import timedelta, datetime
from telethon import TelegramClient, events
from telethon.events.common import EventCommon
from telethon.errors import ChatForwardsRestrictedError
from telethon.tl.functions.account import UpdateStatusRequest
from telethon.tl.functions.messages import GetCustomEmojiDocumentsRequest
from core import db, MaksogramBot, Variables, security, time_now, count_avatars, account_off
from telethon.errors.rpcerrorlist import (
    AuthKeyInvalidError,
    MessageIdInvalidError,
    AuthKeyUnregisteredError,
    BroadcastPublicVotersForbiddenError,
)
from telethon.tl.types import (
    User,
    PeerUser,
    PeerChat,
    PeerChannel,
    ReactionEmoji,
    UserStatusOnline,
    UserStatusOffline,
    ReactionCustomEmoji,

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
                if event.is_private and not event.message.out \
                        and await db.fetch_one(f"SELECT answering_machine_main FROM functions WHERE account_id={self.id}", one_data=True) \
                        and not await db.fetch_one(f"SELECT answering_machine_sending @> '{event.chat_id}' "
                                                   f"FROM functions WHERE account_id={self.id}", one_data=True):
                    auto_message = await self.answering_machine(event)
                    new_event = events.newmessage.NewMessage.Event(auto_message)
                    await self.new_message(new_event)

        @client.on(events.MessageEdited(func=self.initial_checking_event))
        @security()
        async def message_edited(event: events.messageedited.MessageEdited.Event):
            if await self.secondary_checking_event(event):
                await self.sleep()
                await self.message_edited(event)
                await self.client(UpdateStatusRequest(offline=True))

        @client.on(events.MessageDeleted())
        @security()
        async def message_deleted(event: events.messagedeleted.MessageDeleted.Event):
            if event.is_private is False:  # Сообщение удалено в группе, супергруппе или канале
                if not await db.fetch_one(f"SELECT added_chats @> '{event.chat_id}' FROM settings WHERE account_id={self.id}", one_data=True):
                    return
            await self.sleep()
            await self.message_deleted(event)
            await self.client(UpdateStatusRequest(offline=True))

        @client.on(events.MessageRead(func=self.initial_checking_event, inbox=False))
        @security()
        async def message_read_outbox(event: events.messageread.MessageRead.Event):
            if await self.secondary_checking_event(event):
                await self.message_read(event)
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
        return event.is_private and \
            not await db.fetch_one(f"SELECT removed_chats @> '{event.chat_id}' FROM settings WHERE account_id={self.id}", one_data=True) or \
            await db.fetch_one(f"SELECT added_chats @> '{event.chat_id}' FROM settings WHERE account_id={self.id}", one_data=True)

    async def secondary_checking_event(self, event: EventCommon) -> bool:
        if event.is_private:
            try:
                entity = await self.client.get_entity(event.chat_id)
            except ValueError:
                return False
            else:
                return not entity.bot and not entity.support
        return True

    async def chat_name(self, chat_id: int, *, my_name: str = "Избранное", unknown: str = "Неизвестный пользователь") -> str:
        def get_name(first_name: str, last_name: str = ""):
            return f"{first_name} {last_name}" if last_name else first_name

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

    async def get_id(self, peer: Union[PeerUser, PeerChat, PeerChannel]):
        if isinstance(peer, PeerUser):
            return peer.user_id
        if isinstance(peer, PeerChat):
            return peer.chat_id
        if isinstance(peer, PeerChannel):
            return peer.channel_id
        name = await db.fetch_one(f"SELECT name FROM accounts WHERE account_id={self.id}", one_data=True)
        await MaksogramBot.send_system_message(f"⚠️ Ошибка ⚠️\n\nТип peer - {peer.__class__.__name__} ({name})")
        raise TypeError("peer isn't instance PeerUser, PeerChat, PeerChannel")

    @staticmethod
    def get_length_message(message: str) -> int:
        return message.__len__() + emoji.emoji_count(message)

    async def is_premium(self) -> bool:
        return (await self.client.get_me()).premium

    @property
    def my_messages(self):
        return db.fetch_one(f"SELECT my_messages FROM accounts WHERE account_id={self.id}", one_data=True)

    async def get_message_by_id(self, chat_id: int, message_id: int) -> Message:
        async for message in self.client.iter_messages(chat_id, ids=message_id):
            return message

    async def new_message(self, event: events.newmessage.NewMessage.Event):
        message: Message = event.message
        text = message.text.lower()

        # Генератор QR
        if ("создай" in text or "сгенерируй" in text or "qr" in text or "создать" in text or "сгенерировать" in text) \
                and message.out and len(message.entities or []) == 1 and isinstance(message.entities[0], MessageEntityUrl):
            if await db.fetch_one(f"SELECT qrcode FROM modules WHERE account_id={self.id}", one_data=True):
                link = message.text[message.entities[0].offset:message.entities[0].length + message.entities[0].offset]
                qr = create_qrcode(link)
                await message.edit("@MaksogramBot в чате", file=qr)
                os.remove(qr)
                return  # При срабатывании Maksogram в чате сохранение сообщения не происходит
            else:
                await MaksogramBot.send_message(self.id, "Вы хотели создать QR-код? Данная функция отключена у вас! "
                                                         "Вы можете включить в настройках /settings (Maksogram в чате)")

        # Расшифровка голосовых сообщений
        if text and ("расшифруй" in text or "в текст" in text) and message.out and message.reply_to \
                and (reply_message := await self.get_message_by_id(message.chat_id, message.reply_to.reply_to_msg_id)).voice:
            if await db.fetch_one(f"SELECT audio_transcription FROM modules WHERE account_id={self.id}", one_data=True):
                await message.edit("@MaksogramBot в чате\nРасшифровка голосового сообщения...")
                buffer = BytesIO()
                await self.client.download_media(reply_message.media, file=buffer)
                answer = await audio_transcription(buffer.getvalue())
                if answer.ok:
                    await message.edit(f"@MaksogramBot в чате\n<blockquote expandable>{answer.text}</blockquote>", parse_mode="HTML")
                else:
                    await MaksogramBot.send_system_message(f"⚠️Ошибка при расшифровке⚠️\n\n{answer.error}")
                    await message.edit("@MaksogramBot в чате\nПроизошла ошибка при расшифровке... Скоро все будет исправлено")
                return  # При срабатывании Maksogram в чате сохранение сообщения не происходит
            else:
                await MaksogramBot.send_message(self.id, "Вы хотели расшифровать гс? Данная функция отключена у вас! "
                                                         "Вы можете включить в настройках /settings (Maksogram в чате)")

        # Калькулятор
        if text and text[-1] == "=" and "\n" not in text and message.out:
            if await db.fetch_one(f"SELECT calculator FROM modules WHERE account_id={self.id}", one_data=True):
                request = calculator(text[:-1])
                if request:
                    await message.edit(request)
                    return  # При срабатывании Maksogram в чате сохранение сообщения не происходит
                else:
                    await MaksogramBot.send_message(self.id, "Вы хотели воспользоваться калькулятором? Вы неправильно ввели пример")
            else:
                await MaksogramBot.send_message(self.id, "Вы хотели воспользоваться калькулятором? Данная функция отключена у вас! "
                                                         "Вы можете включить ее в настройках /settings (Maksogram в чате)")

        try:
            saved_message = await self.client.forward_messages(await self.my_messages, message)
        except (MessageIdInvalidError, ChatForwardsRestrictedError, BroadcastPublicVotersForbiddenError):
            return

        await db.execute(f"INSERT INTO \"{self.id}_messages\" VALUES "
                         f"({message.chat_id}, {message.id}, {saved_message.id}, '')")

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
    async def get_reactions(self, event: events.messageedited.MessageEdited.Event, *, is_premium: bool = False) -> tuple[str, list]:
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

    async def message_edited(self, event: events.messageedited.MessageEdited.Event):
        message: Message = event.message
        saved_message_id: int = await db.fetch_one(f"SELECT saved_message_id FROM \"{self.id}_messages\" "
                                                   f"WHERE chat_id={message.chat_id} AND message_id={message.id}", one_data=True)
        if saved_message_id is None:  # Если сообщение не было обработано ранее функцией new_message
            return
        if not event.is_private:
            return await self.message_edited_in_group(event, saved_message_id)
        if not await self.check_reactions(event):  # Если изменено содержание сообщения (текст или медиа)
            await self.client.send_message(await self.my_messages, message, comment_to=saved_message_id)
        else:  # Изменение реакций
            is_premium = await self.is_premium()
            reactions, entities = await self.get_reactions(event, is_premium=is_premium)
            reactions_str, _ = await self.get_reactions(event)
            await db.execute(f"UPDATE \"{self.id}_messages\" SET reactions='{reactions_str}' "
                             f"WHERE chat_id={message.chat_id} AND message_id={message.id}")
            reactions = reactions if reactions else "Реакции убраны"
            await self.client.send_message(await self.my_messages, reactions,
                                           formatting_entities=entities, comment_to=saved_message_id)

    async def message_edited_in_group(self, event: events.MessageEdited.Event, saved_message_id: int):
        reactions = await self.get_reactions(event, is_premium=await self.is_premium())
        await self.client.send_message(await self.my_messages, event.message, comment_to=saved_message_id)
        if reactions[0]:
            await self.client.send_message(await self.my_messages, reactions[0],
                                           formatting_entities=reactions[1], comment_to=saved_message_id)

    async def get_deleted_message(self, chat_id: int, is_private: bool, message_id: int):
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

    async def message_deleted(self, event: events.messagedeleted.MessageDeleted.Event):
        is_private = event.is_private is None
        chat_id = event.chat_id
        delete_ids = event.deleted_ids
        if len(delete_ids) > 5:
            message_data = await self.get_deleted_message(chat_id, is_private, min(delete_ids))
            if message_data is None:
                return
            chat_id, saved_message_id = message_data
            await db.execute(f"DELETE FROM \"{self.id}_messages\" WHERE saved_message_id={saved_message_id}")
            await self.client.send_message(await self.my_messages, f"Сообщение (и еще {len(delete_ids)-1}) удалено", comment_to=saved_message_id)
            if chat_id != self.id:
                link_to_message = f"t.me/c/{str(await self.my_messages)[4:]}/{saved_message_id}"  # Сис. канал
                name = await self.chat_name(chat_id)
                if is_private:
                    await MaksogramBot.send_message(self.id, f"В чате {name} удалены {len(delete_ids)} сообщений, например, "
                                                             f"<a href='{link_to_message}'>это</a>", parse_mode="HTML")
                else:
                    await MaksogramBot.send_message(self.id, f"Кто-то из {name} удалил(а) {len(delete_ids)} сообщений, например, "
                                                             f"<a href='{link_to_message}'>это</a>", parse_mode="HTML")
            return
        for id in delete_ids:
            message_data = await self.get_deleted_message(chat_id, is_private, id)
            if message_data is None: continue
            chat_id, saved_message_id = message_data
            await db.execute(f"DELETE FROM \"{self.id}_messages\" WHERE saved_message_id={saved_message_id}")
            await self.client.send_message(await self.my_messages, "Сообщение удалено", comment_to=saved_message_id)
            if chat_id != self.id:
                link_to_message = f"t.me/c/{str(await self.my_messages)[4:]}/{saved_message_id}"  # Сис. канал
                name = await self.chat_name(chat_id)
                if is_private:
                    await MaksogramBot.send_message(
                        self.id, f"В чате с {name} удалено <a href='{link_to_message}'>сообщение</a>", parse_mode="HTML")
                else:
                    await MaksogramBot.send_message(
                        self.id, f"Кто-то из {name} удалил(а) <a href='{link_to_message}'>сообщение</a>", parse_mode="HTML")

    async def message_read(self, event: events.messageread.MessageRead.Event):
        if not event.is_private:
            return
        chat_id = (await event.get_chat()).id
        name = await self.chat_name(chat_id)
        if await db.fetch_one(f"SELECT reading FROM status_users WHERE account_id={self.id} AND user_id={chat_id}", one_data=True):
            await db.execute(f"UPDATE status_users SET reading=false WHERE account_id={self.id} AND user_id={chat_id}")
            await MaksogramBot.send_message(self.id, f"🌐 {name} прочитал сообщение")

    async def user_update(self, event: events.userupdate.UserUpdate.Event):
        status = isinstance(event.status, UserStatusOnline)
        if self.status_users.get(event.chat_id) == status:
            return
        self.status_users[event.chat_id] = status
        function = await db.fetch_one(f"SELECT online, offline FROM status_users WHERE account_id={self.id} AND user_id={event.chat_id}")
        online = function['online'] and status is True
        offline = function['offline'] and status is False
        if online or offline:
            name = await self.chat_name(event.chat_id)
            status_str = "в сети" if status else "вышел(а) из сети"
            await MaksogramBot.send_message(self.id, f"🌐 {name} {status_str}", reply_markup=MaksogramBot.IMarkup(
                inline_keyboard=[[MaksogramBot.IButton(text="Настройки", callback_data=f"status_user_menu{event.chat_id}")]]))

    async def system_bot(self, event: events.newmessage.NewMessage.Event):
        message: Message = event.message
        text = message.text.lower()

        # Генератор QR
        if ("создай" in text or "сгенерируй" in text or "qr" in text or "создать" in text or "сгенерировать" in text) \
                and message.out and len(message.entities or []) == 1 and isinstance(message.entities[0], MessageEntityUrl):
            if await db.fetch_one(f"SELECT qrcode FROM modules WHERE account_id={self.id}", one_data=True):
                link = message.text[message.entities[0].offset:message.entities[0].length + message.entities[0].offset]
                qr = create_qrcode(link)
                await message.edit("@MaksogramBot в чате", file=qr)
                os.remove(qr)
            else:
                await MaksogramBot.send_message(self.id, "Вы хотели создать QR-код? Данная функция отключена у вас! "
                                                         "Вы можете включить в настройках /settings (Maksogram в чате)")

        # Расшифровка голосовых сообщений
        elif text and ("расшифруй" in text or "в текст" in text) and message.out and message.reply_to \
                and (reply_message := await self.get_message_by_id(message.chat_id, message.reply_to.reply_to_msg_id)).voice:
            if await db.fetch_one(f"SELECT audio_transcription FROM modules WHERE account_id={self.id}", one_data=True):
                await message.edit("@MaksogramBot в чате\nРасшифровка голосового сообщения...")
                buffer = BytesIO()
                await self.client.download_media(reply_message.media, file=buffer)
                answer = await audio_transcription(buffer.getvalue())
                if answer.ok:
                    await message.edit(f"@MaksogramBot в чате\n<blockquote expandable>{answer.text}</blockquote>", parse_mode="HTML")
                else:
                    await MaksogramBot.send_system_message(f"⚠️Ошибка при расшифровке⚠️\n\n{answer.error}")
                    await message.edit("@MaksogramBot в чате\nПроизошла ошибка при расшифровке... Скоро все будет исправлено")
            else:
                await MaksogramBot.send_message(self.id, "Вы хотели расшифровать гс? Данная функция отключена у вас! "
                                                         "Вы можете включить в настройках /settings (Maksogram в чате)")

        # Калькулятор
        elif text and text[-1] == "=" and "\n" not in text and message.out:
            if await db.fetch_one(f"SELECT calculator FROM modules WHERE account_id={self.id}", one_data=True):
                request = calculator(text[:-1])
                if request:
                    await message.edit(request)
                else:
                    await MaksogramBot.send_message(self.id, "Вы хотели воспользоваться калькулятором? Вы неправильно ввели пример")
            else:
                await MaksogramBot.send_message(self.id, "Вы хотели воспользоваться калькулятором? Данная функция отключена у вас! "
                                                         "Вы можете включить ее в настройках /settings (Maksogram в чате)")

    async def answering_machine(self, event: events.newmessage.NewMessage.Event):
        message: Message = event.message
        answer = await db.fetch_one("SELECT text, entities FROM answering_machine WHERE answer_id=(SELECT answering_machine_main "
                                    f"FROM functions WHERE account_id={self.id}) AND account_id={self.id}")
        if not answer: return
        await db.execute(f"UPDATE functions SET answering_machine_sending=answering_machine_sending || '{message.chat_id}' "
                         f"WHERE account_id={self.id}")
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
        while await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={self.id}", one_data=True):
            for user in await db.fetch_all(f"SELECT user_id, name, count FROM avatars WHERE account_id={self.id}"):
                count = await count_avatars(self.id, user['user_id'])
                if user['count'] > count:
                    await MaksogramBot.send_message(
                        self.id, f"📸 <b><a href='tg://user?id={user['user_id']}'>{user['name']}</a></b> удалил(а) аватарку",
                        reply_markup=MaksogramBot.IMarkup(
                            inline_keyboard=[[MaksogramBot.IButton(text="🔴 Выключить", callback_data=f"avatar_del{user['user_id']}")]]),
                        parse_mode="html")
                elif user['count'] < count:
                    await MaksogramBot.send_message(
                        self.id, f"📸 <b><a href='tg://user?id={user['user_id']}'>{user['name']}</a></b> добавил(а) аватарку",
                        reply_markup=MaksogramBot.IMarkup(
                            inline_keyboard=[[MaksogramBot.IButton(text="🔴 Выключить", callback_data=f"avatar_del{user['user_id']}")]]),
                        parse_mode="html")
                else: continue
                await db.execute(f"UPDATE avatars SET count={count} WHERE account_id={self.id} AND user_id={user['user_id']}")
            await asyncio.sleep(5*60)

    async def run_until_disconnected(self):
        await db.execute(f"CREATE TABLE IF NOT EXISTS \"{self.id}_messages\" (chat_id BIGINT NOT NULL, "
                         "message_id INTEGER NOT NULL, saved_message_id INTEGER NOT NULL, reactions TEXT NOT NULL)")
        name = await db.fetch_one(f"SELECT name FROM accounts WHERE account_id={self.id}", one_data=True)
        await MaksogramBot.send_system_message(f"SavingMessages v{self.__version__} для {name} запущен")
        asyncio.get_running_loop().create_task(self.new_avatar())
        try:
            await self.client.run_until_disconnected()
        except (AuthKeyInvalidError, AuthKeyUnregisteredError):
            await MaksogramBot.send_message(self.id, "Вы удалили сессию, она была необходима для работы программы!")
            await MaksogramBot.send_system_message(f"Удалена сессия у пользователя {name}")
            phone_number = await db.fetch_one(f"SELECT phone_number FROM accounts WHERE account_id={self.id}", one_data=True)
            await account_off(self.id, f"+{phone_number}")
