from typing import Any
from enum import StrEnum
from datetime import datetime


class NameModule(StrEnum):
    calculator = "Калькулятор"
    weather = "Погода"
    qr_code = "Генератор QR"
    audio_transcription = "Расшифровка голосового"
    round_video = "Видео в кружок"
    reminder = "Напоминалка"
    randomizer = "Рандомайзер"
    currencies = "Конвертер валют"


class Remind:
    def __init__(self, chat_id: int, message_id: int, time: datetime, chat_name: str):
        self.chat_id = chat_id
        self.message_id = message_id
        self.time = time
        self.chat_name = chat_name

    @classmethod
    def from_json(cls, json_data: dict[str, Any]) -> 'Remind':
        return cls(
            chat_id=json_data['chat_id'],
            message_id=json_data['message_id'],
            time=json_data['time'],
            chat_name=json_data['chat_name']
        )

    @classmethod
    def list_from_json(cls, json_data: list[dict[str, Any]]) -> list['Remind']:
        return [cls.from_json(data) for data in json_data]
