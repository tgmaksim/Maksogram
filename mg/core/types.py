from mg.config import (
    OWNER,
    release,
    sessions_path,
    TELEGRAM_DC_IP,
    TELEGRAM_DC_ID,
    TELEGRAM_API_ID,
    TELEGRAM_DC_PORT,
    TELEGRAM_API_HASH,
    TELEGRAM_BOT_API_TOKEN,
)

from enum import IntEnum
from typing import Optional
from datetime import datetime

from telethon import TelegramClient


morning = 5, 13


class CustomEmoji(IntEnum):
    maksogram = 5418001570597986649 if release else 5409102613109014529  # Логотип Maksogram
    sound = 5787303083709041530 if release else 5438098134892806145  # Значок звука в виде волн
    loading = 5787196143318339389 if release else 5438248712151236609  # Значок загрузки в виде трех точек
    round_loading = 5371071931833393000 if release else 5440655684838359041  # Значок загрузки в видео вращающегося круга с точками
    warning = 5364241851500997604 if release else 5440871373800996865  # Желтый треугольник
    clock = 5274055917766202507 if release else 5440761358213709825  # Часы


class AccountSettings:
    def __init__(self, is_started: bool, added_chats: dict[int, str], removed_chats: dict[int, str],
                 time_zone: int, city: str, gender: Optional[bool], saving_messages: bool, notify_changes: bool):
        self.is_started = is_started
        self.added_chats = added_chats
        self.removed_chats = removed_chats
        self.time_zone = time_zone
        self.city = city
        self.gender = gender
        self.saving_messages = saving_messages
        self.notify_changes = notify_changes

    @classmethod
    def from_json(cls, json_data: dict) -> 'AccountSettings':
        return cls(
            is_started=json_data['is_started'],
            added_chats={int(chat_id): chat_name for chat_id, chat_name in json_data['added_chats'].items()},
            removed_chats={int(chat_id): chat_name for chat_id, chat_name in json_data['removed_chats'].items()},
            time_zone=json_data['time_zone'],
            city=json_data['city'],
            gender=json_data['gender'],
            saving_messages=json_data['saving_messages'],
            notify_changes=json_data['notify_changes']
        )

    @property
    def str_gender(self) -> Optional[str]:
        if self.gender is True:
            return "мужчина"
        if self.gender is False:
            return "женщина"
        return None

    @property
    def str_time_zone(self) -> str:
        if self.time_zone >= 0:
            return f"+{self.time_zone:02d}"
        return str(self.time_zone)


class PaymentData:
    def __init__(self, subscription: Optional[str], fee: int, ending: Optional[datetime], first_notification: datetime, second_notification: datetime):
        self.subscription = subscription
        self.fee = fee
        self.ending = ending
        self.first_notification = first_notification
        self.second_notification = second_notification

    @classmethod
    def from_json(cls, json_data: dict) -> 'PaymentData':
        return cls(
            subscription=json_data['subscription'],
            fee=json_data['fee'],
            ending=json_data['ending'],
            first_notification=json_data['first_notification'],
            second_notification=json_data['second_notification']
        )

    @property
    def str_ending(self) -> Optional[str]:
        if not self.ending:
            return
        return self.ending.strftime('%Y-%m-%d')


class MaksogramBot:
    id = int(TELEGRAM_BOT_API_TOKEN.split(':')[0])
    username = "MaksogramBot"
    client: TelegramClient = None

    @classmethod
    async def init(cls):
        cls.client = TelegramClient(
            f"{sessions_path}/bot.session",
            TELEGRAM_API_ID,
            TELEGRAM_API_HASH,
            device_model="Maksogram in Chat",
            system_version="Maksogram platform v3",
            app_version="3",
            lang_code="ru",
            system_lang_code="ru"
        )
        cls.client.session.set_dc(TELEGRAM_DC_ID, TELEGRAM_DC_IP, TELEGRAM_DC_PORT)
        await cls.client.connect()
        await cls.client.sign_in(bot_token=TELEGRAM_BOT_API_TOKEN)

    @classmethod
    async def send_message(cls, chat_id: int, message: str, parse_mode: Optional[str] = "html", **kwargs):
        """Отправляет сообщение через TelegramClient"""

        if kwargs.get('reply_markup'):
            kwargs['buttons'] = kwargs['reply_markup']
            kwargs.pop('reply_markup')

        if kwargs.get('formatting_entities'):
            parse_mode = None

        await cls.client.send_message(chat_id, message, parse_mode=parse_mode, **kwargs)

    @classmethod
    async def send_file(cls, chat_id: int, file, message: str, parse_mode: Optional[str] = "html", **kwargs):
        """Отправляет сообщение через TelegramClient"""

        if kwargs.get('reply_markup'):
            kwargs['buttons'] = kwargs['reply_markup']
            kwargs.pop('reply_markup')

        if kwargs.get('formatting_entities'):
            parse_mode = None

        await cls.client.send_file(chat_id, file, caption=message, parse_mode=parse_mode, **kwargs)

    @classmethod
    async def send_system_message(cls, message: str, parse_mode: Optional[str] = "html", **kwargs):
        """Отправляет сообщение админу через TelegramClient"""

        await cls.send_message(OWNER, message, parse_mode, **kwargs)
