import os
import emoji
import random
import asyncio

from modules.calculator import main as calculator
from modules.qrcode import create as create_qrcode
from modules.audio_transcription import main as audio_transcription
from modules.weather import main as weather
from modules.round_video import main as round_video
from modules.reminder import main as reminder
from modules.randomizer import main as randomizer

from io import BytesIO
from html import escape
from typing import Union
from telethon.tl.patched import Message
from datetime import timedelta, datetime
from telethon import TelegramClient, events
from .admin import reload_server, upload_file
from telethon.events.common import EventCommon
from asyncpg.exceptions import UniqueViolationError
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.account import UpdateStatusRequest
from telethon.tl.functions.messages import GetCustomEmojiDocumentsRequest
from telethon.errors import ChatForwardsRestrictedError, FileReferenceExpiredError
from core import (
    db,
    morning,
    get_bio,
    security,
    time_now,
    www_path,
    Variables,
    get_gifts,
    json_encode,
    account_off,
    human_bytes,
    get_avatars,
    MaksogramBot,
    resources_path,
    get_enabled_auto_answer,
)
from telethon.errors.rpcerrorlist import (
    AuthKeyInvalidError,
    MessageIdInvalidError,
    AuthKeyUnregisteredError,
    BroadcastPublicVotersForbiddenError,
)
from telethon.tl.types import (
    User,
    Birthday,
    PeerUser,
    PeerChat,
    PeerChannel,
    ReactionEmoji,
    MessageMediaDice,
    UserStatusOnline,
    UserStatusOffline,
    MessageMediaPhoto,
    MessageReplyHeader,
    ReactionCustomEmoji,
    MessageMediaWebPage,
    MessageMediaDocument,

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


TTL_MEDIA = Union[MessageMediaPhoto, MessageMediaDocument]
months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "ноября", "декабря"]


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
    __version__ = Variables.version_string

    async def sleep(self):
        difference = (time_now() - self.last_event.get()).total_seconds()
        self.last_event.add(not (difference > LastEvent.seconds))
        if difference < LastEvent.seconds:
            await asyncio.sleep(LastEvent.seconds - difference)

    @property
    def offline(self) -> bool:
        return not bool(self.status)

    def __init__(self, client: TelegramClient, account_id: int, status_users: list[int], morning_notification: datetime):
        self.id = account_id
        self.client = client
        self.last_event = LastEvent()
        self.status = None

        self.my_messages: int = None  # Инициализируется при запуске
        self.message_changes: int = None  # Инициализируется при запуске

        self.status_users: dict[int, bool] = {user: None for user in status_users}  # {id: True} -> id в сети
        self.time_morning_notification: datetime = morning_notification

        @client.on(events.NewMessage(func=self.initial_checking_event))
        @security()
        async def new_message(event: events.newmessage.NewMessage.Event):
            if await self.secondary_checking_event(event):
                await self.sleep()
                await self.new_message(event)
                if self.offline:
                    await self.client(UpdateStatusRequest(offline=True))
                if event.is_private and not event.message.out and self.offline and await get_enabled_auto_answer(self.id) \
                        and not await db.fetch_one(f"SELECT answering_machine_sending @> '{event.chat_id}' "
                                                   f"FROM functions WHERE account_id={self.id}", one_data=True):
                    await self.answering_machine(event)

        @client.on(events.MessageEdited(func=self.initial_checking_event))
        @security()
        async def message_edited(event: events.messageedited.MessageEdited.Event):
            if await self.secondary_checking_event(event):
                await self.sleep()
                await self.message_edited(event)
                if self.offline:
                    await self.client(UpdateStatusRequest(offline=True))

        @client.on(events.MessageDeleted())
        @security()
        async def message_deleted(event: events.messagedeleted.MessageDeleted.Event):
            if event.is_private is False:  # Сообщение удалено в группе, супергруппе или канале
                if not await db.fetch_one(f"SELECT added_chats @> '{event.chat_id}' FROM settings WHERE account_id={self.id}", one_data=True):
                    return
            await self.sleep()
            await self.message_deleted(event)
            if self.offline:
                await self.client(UpdateStatusRequest(offline=True))

        @client.on(events.MessageRead(func=self.initial_checking_event, inbox=False))
        @security()
        async def message_read_outbox(event: events.messageread.MessageRead.Event):
            if await self.secondary_checking_event(event):
                await self.message_read(event)

        @client.on(events.UserUpdate(
            chats=set(list(self.status_users) + [self.id]),
            func=lambda event: isinstance(event.status, (UserStatusOnline, UserStatusOffline)))
        )
        @security()
        async def user_update(event: events.userupdate.UserUpdate.Event):
            if event.chat_id == self.id:
                await self.self_update(event)
            else:
                await self.user_update(event)

        @client.on(events.NewMessage(chats=[MaksogramBot.id], outgoing=True))
        @security()
        async def system_bot(event: events.newmessage.NewMessage.Event):
            await self.system_bot(event)

    async def initial_checking_event(self, event: EventCommon) -> bool:
        return event.is_private and \
            not await db.fetch_one(f"SELECT removed_chats ? '{event.chat_id}' FROM settings WHERE account_id={self.id}", one_data=True) or \
            await db.fetch_one(f"SELECT added_chats ? '{event.chat_id}' FROM settings WHERE account_id={self.id}", one_data=True)

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
        await MaksogramBot.send_system_message(f"⚠️ Ошибка ⚠️\n\nПользователь: {self.id}\nТип peer: {peer.__class__.__name__}")
        raise TypeError("peer isn't instance PeerUser, PeerChat, PeerChannel")

    @staticmethod
    def get_length_message(message: str) -> int:
        return message.__len__() + emoji.emoji_count(message)

    async def is_premium(self) -> bool:
        return (await self.client.get_me()).premium

    async def get_message_by_id(self, chat_id: int, message_id: int) -> Message:
        async for message in self.client.iter_messages(chat_id, ids=message_id):
            return message

    async def modules(self, message: Message) -> bool:
        text = message.text.lower()
        bot = message.chat_id == MaksogramBot.id
        bot_voice, bot_video = bot and message.voice, bot and message.video
        if not (bot or text and "\n" not in text and message.out and (message.media is None or isinstance(message.media, MessageMediaWebPage))):
            return False

        reply_message = await self.get_message_by_id(message.chat_id, message.reply_to.reply_to_msg_id) if \
            isinstance(message.reply_to, MessageReplyHeader) else None
        if reply_message and reply_message.chat_id != message.chat_id:
            return False

        # Калькулятор
        if text and text[-1] == "=" and message.entities is None:
            if await db.fetch_one(f"SELECT calculator FROM modules WHERE account_id={self.id}", one_data=True):
                request = calculator(text[:-1])
                if request:
                    await message.edit(request)
                    return "Калькулятор"
                else:
                    await MaksogramBot.send_message(self.id, "Вы хотели воспользоваться калькулятором? Вы неправильно ввели пример")
            else:
                await MaksogramBot.send_message(self.id, "Вы хотели воспользоваться калькулятором? Данная функция отключена у вас! "
                                                         "Вы можете включить ее в настройках\n/menu_chat (Maksogram в чате)")

        # Генератор QR
        elif text and any([command in text for command in ("создай", "сгенерируй", "qr", "создать", "сгенерировать")]) \
                and len(message.entities or []) == 1 and isinstance(message.entities[0], MessageEntityUrl):
            if await db.fetch_one(f"SELECT qrcode FROM modules WHERE account_id={self.id}", one_data=True):
                link = message.text[message.entities[0].offset:message.entities[0].length + message.entities[0].offset]
                qr = create_qrcode(link)
                await message.edit("🤖 @MaksogramBot в чате\nГенератор QR-кода из ссылки", file=qr,
                                   formatting_entities=[MessageEntityCustomEmoji(0, 2, 5418001570597986649),
                                                        MessageEntityTextUrl(45, 6, link), MessageEntityBold(45, 6)])
                os.remove(qr)
                return "Генератор QR"
            else:
                await MaksogramBot.send_message(self.id, "Вы хотели создать QR-код? Данная функция отключена у вас! "
                                                         "Вы можете включить в настройках\n/menu_chat (Maksogram в чате)")

        # Расшифровка голосовых сообщений
        elif bot_voice or reply_message and reply_message.voice and any([command in text for command in ("расшифруй", "в текст", "расшифровать")]):
            if await db.fetch_one(f"SELECT audio_transcription FROM modules WHERE account_id={self.id}", one_data=True):
                if await self.is_premium():
                    data = {f"{'message' if bot_voice else 'text'}": "🤖 @MaksogramBot в чате\n🗣 Расшифровка голосового ✍️",
                            "formatting_entities": [MessageEntityCustomEmoji(0, 2, 5418001570597986649),
                                                    MessageEntityCustomEmoji(24, 2, 5787303083709041530),
                                                    MessageEntityCustomEmoji(50, 2, 5787196143318339389)]}
                else:
                    data = {f"{'message' if bot_voice else 'text'}": "@MaksogramBot в чате\nРасшифровка голосового..."}
                if bot_voice:
                    reply_message, message = message, await message.reply(**data)
                else:
                    await message.edit(**data)
                buffer = BytesIO()
                await self.client.download_media(reply_message.media, file=buffer)
                answer = await audio_transcription(buffer.getvalue())
                if answer.ok:
                    await message.edit(f"@MaksogramBot в чате\n<blockquote expandable>{answer.text}</blockquote>", parse_mode="HTML")
                else:
                    await MaksogramBot.send_system_message(f"⚠️Ошибка при расшифровке⚠️\n\n"
                                                           f"{answer.error.__class__.__name__}\n{answer.error}")
                    await message.edit("@MaksogramBot в чате\nПроизошла ошибка при расшифровке... Скоро все будет исправлено")
                await db.execute(f"UPDATE statistics SET audio_transcription=now() WHERE account_id={self.id}")
                return "Расшифровка голосового"
            else:
                await MaksogramBot.send_message(self.id, "Вы хотели расшифровать гс? Данная функция отключена у вас! "
                                                         "Вы можете включить в настройках\n/menu_chat (Maksogram в чате)")

        # Погода
        elif text and all([command in text for command in ("какая", "погода")]):
            if await db.fetch_one(f"SELECT weather FROM modules WHERE account_id={self.id}", one_data=True):
                request = await weather(self.id)
                await message.edit(f"@MaksogramBot в чате\n{request}", parse_mode="HTML")
                await db.execute(f"UPDATE statistics SET weather=now() WHERE account_id={self.id}")
                return "Погода"
            else:
                await MaksogramBot.send_message(self.id, "Вы хотели воспользоваться погодой? Данная функция отключена у вас! "
                                                         "Вы можете включить ее в настройках\n/menu_chat (Maksogram в чате)")

        # Конвертер видео в кружок
        elif bot_video or reply_message and reply_message.video and "кружок" in text:
            if await db.fetch_one(f"SELECT round_video FROM modules WHERE account_id={self.id}", one_data=True):
                video = message.video if bot_video else reply_message.video
                if video.attributes[0].duration >= 60:
                    data = {f"{'message' if bot_video else 'text'}": "🤖 @MaksogramBot в чате\nВидео слишком длинное! ⚠️",
                            "formatting_entities": [MessageEntityCustomEmoji(0, 2, 5418001570597986649),
                                                    MessageEntityCustomEmoji(47, 2, 5364241851500997604)]}
                    if bot_video: await message.reply(**data)
                    else: await message.edit(**data)
                else:
                    data = {f"{'message' if bot_video else 'text'}": "🤖 @MaksogramBot в чате\nКонвертация видео в кружок ⏰",
                            "formatting_entities": [MessageEntityCustomEmoji(0, 2, 5418001570597986649),
                                                    MessageEntityCustomEmoji(51, 1, 5371071931833393000)]}
                    if bot_video:
                        reply_message, message = message, await message.reply(**data)
                    else:
                        await message.edit(**data)
                    video_path = resources_path(f"round_video/{reply_message.video.id}.mp4")
                    await self.client.download_media(reply_message.media, file=video_path)
                    answer = round_video(video_path)
                    if answer.ok:
                        await message.edit("🤖 @MaksogramBot в чате\nОтправка кружка ⏰",
                                           formatting_entities=[MessageEntityCustomEmoji(0, 2, 5418001570597986649),
                                                                MessageEntityCustomEmoji(40, 1, 5787399776307776752)])
                        await self.client.send_file(message.chat_id, file=answer.path, reply_to=reply_message.id, video_note=True)
                        await message.delete()
                        os.remove(answer.path)
                    else:
                        await MaksogramBot.send_system_message(f"⚠️Ошибка при конвертации⚠️\n\n"
                                                               f"{answer.error.__class__.__name__}\n{answer.error}")
                        await message.edit("@MaksogramBot в чате\nПроизошла ошибка при конвертации... Скоро все будет исправлено")
                return "Конвертер видео в кружок"
            else:
                await MaksogramBot.send_message(self.id, "Вы хотели конвертировать видео в кружок? Данная функция отключена у вас! "
                                                         "Вы можете включить в настройках\n/menu_chat (Maksogram в чате)")

        # Напоминалка
        # напомни в 12.00, напомни завтра в 12.00, напомни послезавтра в 12.00, напомни 9 декабря в 12.00, напомни через 5 минут
        elif reply_message and (remind_time := await reminder(text, db.fetch_one(f"SELECT time_zone FROM settings "
                                                                                 f"WHERE account_id={self.id}", one_data=True))):
            if await db.fetch_one(f"SELECT reminder FROM modules WHERE account_id={self.id}", one_data=True):
                time_zone = await db.fetch_one(f"SELECT time_zone FROM settings WHERE account_id={self.id}", one_data=True)
                name = await self.chat_name(message.chat_id, my_name="Избранное")
                try:
                    await db.fetch_one(f"INSERT INTO reminds VALUES ({self.id}, {reply_message.chat_id}, {reply_message.id}, $1, $2)",
                                       remind_time - timedelta(hours=time_zone), name)
                except UniqueViolationError:
                    await message.edit("@MaksogramBot в чате\nНапоминание о событии в это время уже есть")
                    return True
                if reply_message.chat_id == self.id:
                    await MaksogramBot.send_message(self.id, "⏰ <b>Напоминалка</b>\nВы можете создавать напоминания здесь, "
                                                             "чтобы не забивать Избранное :)")
                if remind_time.date() == time_now(time_zone).date():  # Сегодня
                    date = "сегодня"
                elif remind_time.date() == (time_now(time_zone) + timedelta(days=1)).date():  # Завтра
                    date = "завтра"
                elif remind_time.date() == (time_now(time_zone) + timedelta(days=2)).date():  # Послезавтра
                    date = "послезавтра"
                else:
                    date = f"{remind_time.day} {months[remind_time.month-1]}"
                    if remind_time.year != time_now(time_zone).year:
                        date += " следующего года"
                await message.edit("🤖 @MaksogramBot в чате\nНапоминание на "
                                   f"{date} в {remind_time.hour:02d}:{remind_time.minute:02d} ⏰",
                                   formatting_entities=[MessageEntityCustomEmoji(0, 2, 5418001570597986649),
                                                        MessageEntityCustomEmoji(48+len(date), 1, 5274055917766202507)])
                return "Напоминалка"
            else:
                await MaksogramBot.send_message(self.id, "Вы хотели воспользоваться напоминалкой? Данная функция отключена у вас! "
                                                         "Вы можете включить в настройках\n/menu_chat (Maksogram в чате)")

        # Рандомайзер
        elif choice := randomizer(text):
            if await db.fetch_one(f"SELECT randomizer FROM modules WHERE account_id={self.id}", one_data=True):
                await self.client.send_message(message.chat_id, file=MessageMediaDice(0, "🎲"))
                await asyncio.sleep(3)
                entity = (await self.client._parse_message_text(f"🤖 @MaksogramBot выбирает <b>{escape(choice)}</b>", "html"))[1][0]
                await message.reply(f"🤖 @MaksogramBot выбирает {choice}",
                                    formatting_entities=[MessageEntityCustomEmoji(0, 2, 5418001570597986649),
                                                         MessageEntitySpoiler(entity.offset, entity.length)])
                return "Рандомайзер"
            else:
                await MaksogramBot.send_message(self.id, "Вы хотели воспользоваться рандомайзером? Данная функция отключена у вас! "
                                                         "Вы можете включить в настройках\n/menu_chat (Maksogram в чате)")

        return False

    async def new_message(self, event: events.newmessage.NewMessage.Event):
        message: Message = event.message

        if message.text == "reload" and message.chat_id == self.id:
            await self.client.send_message(self.id, "Сервер перезапускается")
            await reload_server()
            return

        if message.out:
            # Для функции подсчета статистики времени ответа
            await db.execute(f"UPDATE status_users SET last_message=now() "
                             f"WHERE account_id={self.id} AND user_id={message.chat_id} AND last_message IS NULL")

        if await self.modules(message):
            return  # При срабатывании Maksogram в чате сохранение сообщения не происходит

        if isinstance(message.media, TTL_MEDIA) and message.media.ttl_seconds:  # Самоуничтожающееся медиа
            if message.file.size / 2**20 <= 10 or message.video_note or \
                    message.voice and message.voice.attributes[0].duration <= 480:  # меньше 10 МБ, или кружок, или гс (до 8 минут)
                file_id = message.photo.id if message.photo else message.document.id
                ext = "png" if message.photo else message.file.ext
                path = resources_path(f"ttl_media/{self.id}.{file_id}.{ext}")
                await MaksogramBot.send_message(self.id, "Идет сохранение самоуничтожающегося медиа... "
                                                         "Не смотрите его, пока идет сохранение!")
                try:
                    await self.client.download_media(message, path)
                except FileReferenceExpiredError:  # Уже удалено
                    return await MaksogramBot.send_message(self.id, "Я не успел сохранить самоуничтожающееся медиа, "
                                                                    "потому что вы его быстро посмотрели...")
                saved_message: Message = await self.client.send_file(self.my_messages, path, caption=message.text,
                                                                     video_note=message.video_note, voice_note=message.voice)
                link_to_message = f"t.me/c/{str(self.my_messages)[4:]}/{saved_message.id}"  # Сис. канал
                await MaksogramBot.send_message(self.id, f"Сохранено <a href='{link_to_message}'>самоуничтожающееся медиа</a>",
                                                parse_mode="html")
                return os.remove(path)
            else:
                peer = await self.chat_name(message.chat_id)
                return await MaksogramBot.send_message(self.id, f"В чате с {peer} замечено самоуничтожающееся медиа. Я не смог "
                                                                "его сохранить, т. к. по размеру оно превышает 10 МБ")

        if not await db.fetch_one(f"SELECT saving_messages FROM settings WHERE account_id={self.id}", one_data=True):
            return  # Сохранение сообщений выключено
        try:
            saved_message = await self.client.forward_messages(self.my_messages, message)
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
        if await self.check_for_uploading_document(message):
            return
        saved_message_id: int = await db.fetch_one(f"SELECT saved_message_id FROM \"{self.id}_messages\" "
                                                   f"WHERE chat_id={message.chat_id} AND message_id={message.id}", one_data=True)
        if saved_message_id is None:  # Если сообщение не было обработано ранее функцией new_message
            return
        if not event.is_private:
            return await self.message_edited_in_group(event, saved_message_id)
        if not await self.check_reactions(event):  # Если изменено содержание сообщения (текст или медиа)
            if self.id != event.chat_id and event.is_private \
                    and await db.fetch_one(f"SELECT notify_changes FROM settings WHERE account_id={self.id}", one_data=True):
                link_to_message = f"t.me/c/{str(self.my_messages)[4:]}/{saved_message_id}"  # Сис. канал
                name = await self.chat_name(event.chat_id)
                await MaksogramBot.send_message(
                    self.id, f"В чате с {name} изменено <a href='{link_to_message}'>сообщение</a>", parse_mode="HTML",
                    reply_markup=MaksogramBot.IMarkup(inline_keyboard=[[
                        MaksogramBot.IButton(text="Не уведомлять об изменении", callback_data="notify_changes_off")]]))
            await self.client.send_message(self.my_messages, message, comment_to=saved_message_id)
        else:  # Изменение реакций
            is_premium = await self.is_premium()
            reactions, entities = await self.get_reactions(event, is_premium=is_premium)
            reactions_str, _ = await self.get_reactions(event)
            await db.execute(f"UPDATE \"{self.id}_messages\" SET reactions=$1 "
                             f"WHERE chat_id={message.chat_id} AND message_id={message.id}", reactions_str)
            reactions = reactions if reactions else "Реакции убраны"
            await self.client.send_message(self.my_messages, reactions,
                                           formatting_entities=entities, comment_to=saved_message_id)

    async def check_for_uploading_document(self, message: Message) -> bool:
        if message.document and message.text and message.reactions and message.reactions.recent_reactions and \
                isinstance(message.reactions.recent_reactions[0].reaction, ReactionCustomEmoji) and \
                message.reactions.recent_reactions[0].reaction.document_id == 5899757765743615694:
            progress_message = await MaksogramBot.send_message(self.id, f"Загрузка файла: 0/{human_bytes(message.document.size)}")
            await upload_file(message, progress_message)
            return True
        return False

    async def message_edited_in_group(self, event: events.MessageEdited.Event, saved_message_id: int):
        reactions = await self.get_reactions(event, is_premium=await self.is_premium())
        await self.client.send_message(self.my_messages, event.message, comment_to=saved_message_id)
        if reactions[0]:
            await self.client.send_message(self.my_messages, reactions[0],
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
        deleted_ids = event.deleted_ids
        if len(deleted_ids) > 5:
            message_data = await self.get_deleted_message(chat_id, is_private, min(deleted_ids))
            if message_data is None:
                return
            chat_id, saved_message_id = message_data
            await db.execute(f"DELETE FROM \"{self.id}_messages\" WHERE saved_message_id={saved_message_id}")
            await self.client.send_message(self.my_messages, f"Сообщение (и еще {len(deleted_ids) - 1}) удалено", comment_to=saved_message_id)
            if chat_id != self.id:
                link_to_message = f"t.me/c/{str(self.my_messages)[4:]}/{saved_message_id}"  # Сис. канал
                name = await self.chat_name(chat_id)
                if is_private:
                    await MaksogramBot.send_message(self.id, f"В чате {name} удалены {len(deleted_ids)} сообщений, например, "
                                                             f"<a href='{link_to_message}'>это</a>", parse_mode="HTML")
                else:
                    await MaksogramBot.send_message(self.id, f"Кто-то из {name} удалил(а) {len(deleted_ids)} сообщений, например, "
                                                    f"<a href='{link_to_message}'>это</a>", parse_mode="HTML")
            return
        for id in deleted_ids:
            message_data = await self.get_deleted_message(chat_id, is_private, id)
            if message_data is None: continue
            chat_id, saved_message_id = message_data
            await db.execute(f"DELETE FROM \"{self.id}_messages\" WHERE saved_message_id={saved_message_id}")
            await self.client.send_message(self.my_messages, "Сообщение удалено", comment_to=saved_message_id)
            if chat_id != self.id:
                link_to_message = f"t.me/c/{str(self.my_messages)[4:]}/{saved_message_id}"  # Сис. канал
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
        functions = await db.fetch_one(f"SELECT reading, statistics FROM status_users WHERE account_id={self.id} AND user_id={chat_id}")
        if functions and functions['reading']:
            await db.execute(f"UPDATE status_users SET reading=false WHERE account_id={self.id} AND user_id={chat_id}")
            await MaksogramBot.send_message(self.id, f"🌐 {name} прочитал сообщение", reply_markup=MaksogramBot.IMarkup(
                inline_keyboard=[[MaksogramBot.IButton(text="Настройки", callback_data=f"status_user_menu{self.id}|new")]]))
        if functions and functions['statistics']:
            await db.execute(f"INSERT INTO statistics_time_reading SELECT account_id, user_id, now() - last_message "
                             f"FROM status_users WHERE account_id={self.id} AND user_id={chat_id} AND last_message IS NOT NULL;\n"
                             f"UPDATE status_users SET last_message=NULL WHERE account_id={self.id} AND user_id={chat_id}")

    async def check_awake(self, event: events.userupdate.UserUpdate.Event) -> Union[datetime, None]:
        status = isinstance(event.status, UserStatusOnline)
        if status is False:  # Обработка только статуса в сети
            return
        time_zone: int = await db.fetch_one(f"SELECT time_zone FROM settings WHERE account_id={self.id}", one_data=True)
        time = time_now(time_zone)
        time_last_notification = self.time_morning_notification + timedelta(hours=time_zone)
        if not (morning[0] <= time.hour < morning[1]):  # Сейчас не утро
            return
        if time_last_notification.date() == time.date() and morning[0] <= time_last_notification.hour < morning[1]:
            return  # Сегодня уже отправлено
        return time

    async def self_update(self, event: events.userupdate.UserUpdate.Event):
        status = isinstance(event.status, UserStatusOnline)
        if self.status == status:
            return
        self.status = status

        time = await self.check_awake(event)
        gender = await db.fetch_one(f"SELECT gender FROM settings WHERE account_id={self.id}", one_data=True)

        functions = await db.fetch_all(f"SELECT account_id, name, online, offline, awake, statistics FROM status_users WHERE user_id={self.id}")
        for function in functions:
            statistics = function['statistics']
            awake = status is True and function['awake']
            online = function['online'] and status is True
            offline = function['offline'] and status is False
            if statistics:
                if status is True:  # В сети - нужно добавить новую пару в данных в таблицу и удалить неполные пары
                    await db.execute(f"DELETE FROM statistics_status_users "
                                     f"WHERE account_id={function['account_id']} AND user_id={self.id} AND offline_time IS NULL;\n"
                                     f"INSERT INTO statistics_status_users VALUES ({function['account_id']}, {self.id}, now(), NULL)")
                else:  # Офлайн - закончить пару данных или пропустить
                    await db.execute(f"UPDATE statistics_status_users SET offline_time=now() "
                                     f"WHERE account_id={function['account_id']} AND user_id={self.id} AND offline_time IS NULL")
            if online or offline:
                status_str = "в сети" if status else "вышел(а) из сети"
            elif awake and time:
                if gender is True: status_str = "проснулся"
                elif gender is False: status_str = "проснулась"
                else: status_str = "проснулся(лась)"
            else:
                continue
            name = function['name']
            await MaksogramBot.send_message(function['account_id'], f"🌐 {name} {status_str}", reply_markup=MaksogramBot.IMarkup(
                inline_keyboard=[[MaksogramBot.IButton(text="Настройки", callback_data=f"status_user_menu{self.id}|new")]]))

        if not time:  # Уведомление не требуется
            return

        self.time_morning_notification = time_now()
        await db.execute(f"UPDATE accounts SET morning_notification=now() WHERE account_id={self.id}")
        await db.execute(f"UPDATE status_users SET awake=now() WHERE user_id={event.chat_id} AND awake IS NOT NULL")

        my_birthday: Birthday = (await self.client(GetFullUserRequest(self.id))).full_user.birthday
        if my_birthday.month == time.month and my_birthday.day == time.day:  # Поздравление в днем рождения
            postcard = random.choice(os.listdir(resources_path("holidays/birthday")))
            photo = resources_path(f"holidays/birthday/{postcard}")
            await MaksogramBot.send_message(self.id, "Доброе утро! С днем рождения 🥳\nВсего самого лучшего! 🎊 🎁", photo=photo)
        elif time.date().month == 3 and time.date().day == 1:  # Поздравление с первым днем весны
            postcard = random.choice(os.listdir(resources_path("holidays/1march")))
            photo = resources_path(f"holidays/1march/{postcard}")
            await MaksogramBot.send_message(self.id, "Доброе утро!\nС первым днем весны ☀️", photo=photo)
        elif time.date().month == 2 and time.date().day == 23 and gender is True:  # Поздравление с 23 февраля
            postcard = random.choice(os.listdir(resources_path("holidays/man")))
            photo = resources_path(f"holidays/man/{postcard}")
            await MaksogramBot.send_message(self.id, "С добрым утром! Поздравляю с 23 февраля 😎", photo=photo)
        elif time.date().month == 3 and time.date().day == 8 and gender is False:  # Поздравление с 8 марта
            postcard = random.choice(os.listdir(resources_path("holidays/woman")))
            photo = resources_path(f"holidays/woman/{postcard}")
            await MaksogramBot.send_message(self.id, "С добрым утром! Поздравляю с 8 марта 🥰", photo=photo)
        elif await db.fetch_one(f"SELECT morning_weather FROM modules WHERE account_id={self.id}", one_data=True):  # Погода по утрам
            if gender is True:  # Мужчина
                postcard = random.choice(os.listdir(resources_path("good_morning/man")))
                photo = resources_path(f"good_morning/man/{postcard}")
            elif gender is False:  # Женщина
                postcard = random.choice(os.listdir(resources_path("good_morning/woman")))
                photo = resources_path(f"good_morning/woman/{postcard}")
            else:
                photo = None
            await MaksogramBot.send_message(self.id, f"Доброе утро! Как спалось? 😉\n\n{await weather(self.id)}",
                                            photo=photo, parse_mode="HTML")

    async def user_update(self, event: events.userupdate.UserUpdate.Event):
        status = isinstance(event.status, UserStatusOnline)
        if self.status_users.get(event.chat_id) == status:
            return

        if await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={event.chat_id}", one_data=True):
            return

        self.status_users[event.chat_id] = status

        function = await db.fetch_one(f"SELECT online, offline, awake, statistics FROM status_users "
                                      f"WHERE account_id={self.id} AND user_id={event.chat_id}")
        awake = status is True and function['awake']
        statistics = function['statistics']
        online = function['online'] and status is True
        offline = function['offline'] and status is False
        if statistics:
            if status is True:  # В сети - нужно добавить новую пару в данных в таблицу и удалить неполные пары
                await db.execute(f"DELETE FROM statistics_status_users "
                                 f"WHERE account_id={self.id} AND user_id={event.chat_id} AND offline_time IS NULL;\n"
                                 f"INSERT INTO statistics_status_users VALUES ({self.id}, {event.chat_id}, now(), NULL)")
            else:  # Офлайн - закончить пару данных или пропустить
                await db.execute(f"UPDATE statistics_status_users SET offline_time=now() "
                                 f"WHERE account_id={self.id} AND user_id={event.chat_id} AND offline_time IS NULL")
        if status_str := not (online or offline or awake):
            return
        if online or offline:
            status_str = "в сети" if status else "вышел(а) из сети"
        if awake:
            time_zone: int = await db.fetch_one(f"SELECT time_zone FROM settings WHERE account_id={self.id}", one_data=True)
            time = time_now(time_zone)
            time_last_notification = awake + timedelta(hours=time_zone)
            if morning[0] <= time.hour < morning[1] and not \
                    (time_last_notification.date() == time.date() and morning[0] <= time_last_notification.hour < morning[1]):
                await db.execute(f"UPDATE status_users SET awake=now() WHERE account_id={self.id} AND user_id={event.chat_id}")
                status_str = "проснулся(лась)"
        name = await self.chat_name(event.chat_id)
        await MaksogramBot.send_message(self.id, f"🌐 {name} {status_str}", reply_markup=MaksogramBot.IMarkup(
            inline_keyboard=[[MaksogramBot.IButton(text="Настройки", callback_data=f"status_user_menu{event.chat_id}|new")]]))

    async def system_bot(self, event: events.newmessage.NewMessage.Event):
        await self.modules(event.message)

    async def answering_machine(self, event: events.newmessage.NewMessage.Event):
        message: Message = event.message
        answer_id = await get_enabled_auto_answer(self.id)
        answer = await db.fetch_one(f"SELECT contacts, text, entities, media, triggers FROM answering_machine "
                                    f"WHERE answer_id={answer_id} AND account_id={self.id}")
        if not answer: return
        if answer['contacts'] and not (await self.client.get_entity(message.chat_id)).contact:
            return
        if answer['triggers'] and not any(map(lambda trigger: trigger.lower() in message.text.lower(), answer['triggers'].values())):
            return
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
        if answer['media']:
            access_hash = answer['media'] // 10
            ext = 'png' if answer['media'] % 10 == 1 else 'mp4'
            return await self.client.send_file(message.chat_id, www_path(f"answering_machine/{self.id}.{answer_id}.{access_hash}.{ext}"),
                                               caption=answer['text'], formatting_entities=entities)
        return await self.client.send_message(message.chat_id, answer['text'], formatting_entities=entities)

    async def avatars_center(self, user: dict[str, Union[str, list[int]]]):
        avatars = await get_avatars(self.id, user['user_id'])
        if avatars is None:  # Количество аватарок превышает допустимое
            return await db.execute(f"UPDATE changed_profiles SET avatars=NULL WHERE account_id={self.id} AND user_id={user['user_id']}")
        for avatar in avatars.values():
            if avatar.id not in user['avatars']:  # Новая аватарка
                ext = 'mp4' if avatar.video_sizes else 'png'
                path = resources_path(f"avatars/{self.id}.{avatar.id}.{ext}")
                await self.client.download_media(avatar, path)
                await MaksogramBot.send_message(
                    self.id, f"📸 <b><a href='tg://user?id={user['user_id']}'>{user['name']}</a></b> добавил(а) аватарку",
                    parse_mode="html", **{f"{'video' if avatar.video_sizes else 'photo'}": path})
                os.remove(path)
            else: user['avatars'].remove(avatar.id)
        if count_deleted_avatars := len(user['avatars']):  # Удаленные аватарки
            text = f"{count_deleted_avatars} аватарок" if count_deleted_avatars > 1 else "аватарку"
            await MaksogramBot.send_message(self.id, f"📸 <b><a href='tg://user?id={user['user_id']}'>"
                                                     f"{user['name']}</a></b> удалил(а) {text}", parse_mode="html")
        id_avatars = list(map(lambda x: x.id, avatars.values()))
        await db.execute(f"UPDATE changed_profiles SET avatars='{id_avatars}' WHERE account_id={self.id} AND user_id={user['user_id']}")

    @security()
    async def answering_machine_center(self):
        auto_answer = await get_enabled_auto_answer(self.id)
        while await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={self.id}", one_data=True):
            if auto_answer != (new_auto_answer := await get_enabled_auto_answer(self.id)):  # Сменился работающий автоответ
                auto_answer = new_auto_answer
                await db.execute(f"UPDATE functions SET answering_machine_sending='[]' WHERE account_id={self.id}")
            # Ожидание следующей минуты
            await asyncio.sleep(((time_now() + timedelta(minutes=1)).replace(second=0, microsecond=0) - time_now()).seconds)

    @security()
    async def reminder_center(self):
        while await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={self.id}", one_data=True):
            for remind in await db.fetch_all("SELECT chat_id, message_id, time, chat_name FROM reminds WHERE "
                                             f"account_id={self.id} AND (time - now()) < INTERVAL '0 seconds'"):
                text = {MaksogramBot.id: "", self.id: "в Избранном"}.get(remind['chat_id'], f"в чате с {remind['chat_name']}")
                await MaksogramBot.send_message(self.id, f"⏰ <b>Напоминалка</b>\nНапоминаю о вашем событии {text}", parse_mode="HTML")
                await self.client.send_message(remind['chat_id'], "🤖 @MaksogramBot в чате\nНапоминание о событии! ⏰", reply_to=remind['message_id'],
                                               formatting_entities=[MessageEntityCustomEmoji(0, 2, 5418001570597986649),
                                                                    MessageEntityCustomEmoji(47, 1, 5274055917766202507)])
                await db.execute(f"DELETE FROM reminds WHERE account_id={self.id} AND chat_id={remind['chat_id']} AND "
                                 f"message_id={remind['message_id']} AND time={remind['time']}")
            await asyncio.sleep(((time_now() + timedelta(minutes=1)).replace(second=0, microsecond=0) - time_now()).seconds)

    async def gifts_center(self, user: dict[str, Union[str, dict]]):
        gifts = await get_gifts(self.id, user['user_id'])
        if gifts is None:  # Количество подарков превышает допустимое
            return await db.execute(f"UPDATE changed_profiles SET gifts=NULL WHERE account_id={self.id} AND user_id={user['user_id']}")
        for gift in gifts.values():
            if user['gifts'].get(gift.id):  # Подарок присутствует
                if gift.unique is True and user['gifts'][gift.id]['unique'] is False:  # Подарок стал уникальным
                    link = f"t.me/nft/{gift.slug}"
                    await MaksogramBot.send_message(
                        self.id, f"🎁 <b><a href='tg://user?id={user['user_id']}'>{user['name']}</a></b> улучшил(а) "
                                 f"<a href='{link}'>подарок</a>", parse_mode="html")
                del user['gifts'][gift.id]
            else:  # Подарок появился
                giver = (f"@{gift.giver['username']}" if gift.giver['username'] else
                         f"<a href='tg://user?id={gift.giver['user_id']}'>{gift.giver['name']}</a>") \
                    if gift.giver else "не известно"
                gift_str = "лимитированный подарок" if gift.limited else "подарок"
                if gift.unique is False:  # Неуникальный подарок
                    await MaksogramBot.send_message(
                        self.id, f"🎁 <b><a href='tg://user?id={user['user_id']}'>{user['name']}</a></b> получил(а) {gift_str}\n"
                                 f"От кого: {giver}\nСтоимость: {gift.stars} 🌟", parse_mode="html")
                else:  # Уникальный подарок
                    link = f"t.me/nft/{gift.slug}"
                    await MaksogramBot.send_message(
                        self.id, f"🎁 <b><a href='tg://user?id={user['user_id']}'>{user['name']}</a></b> получил(а) "
                                 f"<a href='{link}'>подарок</a>\nОт кого: {giver}", parse_mode="html")
        if count_hidden_gifts := len(user['gifts']):  # Исчезнувшие подарки (скрытые, переданные)
            gift_str = "подарок" if count_hidden_gifts == 1 else f"{count_hidden_gifts} подарков"
            await MaksogramBot.send_message(
                self.id, f"🎁 <b><a href='tg://user?id={user['user_id']}'>{user['name']}</a></b> скрыл(а) {gift_str}",
                parse_mode="html")
        gifts_json = json_encode({gift.id: gift.__dict__ for gift in gifts.values()})
        await db.execute(f"UPDATE changed_profiles SET gifts=$1 WHERE account_id={self.id} AND user_id={user['user_id']}", gifts_json)

    async def bio_center(self, user: dict[str, str]):
        bio = await get_bio(self.id, user['user_id'])
        if user['bio'] != bio:
            await MaksogramBot.send_message(self.id, f"🖼️ <b><a href='tg://user?id={user['user_id']}'>{user['name']}</a></b> "
                                                     f"«О себе»\n<blockquote>{bio}</blockquote>", parse_mode="html")
            await db.execute(f"UPDATE changed_profiles SET bio=$1 WHERE account_id={self.id} AND user_id={user['user_id']}", bio)

    @security()
    async def changed_profile_center(self):
        while await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={self.id}", one_data=True):
            for user in await db.fetch_all(f"SELECT user_id, name, avatars, gifts, bio FROM changed_profiles WHERE account_id={self.id}"):
                if user['avatars'] is not None:
                    await self.avatars_center(user)
                if user['gifts'] is not None:
                    await self.gifts_center(user)
                if user['bio'] is not None:
                    await self.bio_center(user)
            await asyncio.sleep(5*60)

    async def run_until_disconnected(self):
        await db.execute(f"CREATE TABLE IF NOT EXISTS \"{self.id}_messages\" (chat_id BIGINT NOT NULL, "
                         "message_id INTEGER NOT NULL, saved_message_id INTEGER NOT NULL, reactions TEXT NOT NULL)")
        account = await db.fetch_one(f"SELECT my_messages, message_changes FROM accounts WHERE account_id={self.id}")
        self.my_messages, self.message_changes = account['my_messages'], account['message_changes']
        await MaksogramBot.send_system_message(f"Maksogram {self.__version__} для меня запущен")
        asyncio.get_running_loop().create_task(self.changed_profile_center())
        asyncio.get_running_loop().create_task(self.answering_machine_center())
        asyncio.get_running_loop().create_task(self.reminder_center())
        try:
            await self.client.run_until_disconnected()
        except (AuthKeyInvalidError, AuthKeyUnregisteredError):
            await MaksogramBot.send_system_message(f"Удалена сессия у программы!")
            await account_off(self.id)
