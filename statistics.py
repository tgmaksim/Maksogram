import asyncio

from mg.bot.types import CallbackData

from telethon.tl.types import KeyboardButtonRow as KRow
from telethon.tl.types import ReplyInlineMarkup as IMarkup
from telethon.tl.types import KeyboardButtonCallback as IButton

from typing import Any
from mg.core.database import Database
from mg.core.types import MaksogramBot
from datetime import timedelta, datetime
from mg.core.functions import time_now, get_account_status


cb = CallbackData()


class AccountStatistics:
    def __init__(self, account_id: int, answering_machine: datetime, audio_transcription: datetime, weather: datetime, morning_weather: bool):
        self.account_id = account_id
        self.answering_machine = answering_machine
        self.audio_transcription = audio_transcription
        self.weather = weather
        self.morning_weather = morning_weather

    @classmethod
    def from_json(cls, json_data: dict[str, Any]) -> 'AccountStatistics':
        return cls(
            account_id=json_data['account_id'],
            answering_machine=json_data['answering_machine'],
            audio_transcription=json_data['audio_transcription'],
            weather=json_data['weather'],
            morning_weather=json_data['morning_weather']
        )

    @classmethod
    def list_from_json(cls, json_data: list[dict[str, Any]]) -> list['AccountStatistics']:
        return [cls.from_json(data) for data in json_data]


async def get_statistics() -> list[AccountStatistics]:
    sql = ("SELECT statistics.account_id, statistics.answering_machine, statistics.audio_transcription, statistics.weather, modules.morning_weather "
           "FROM statistics LEFT JOIN modules ON statistics.account_id = modules.account_id")
    data: list[dict] = await Database.fetch_all(sql)

    return AccountStatistics.list_from_json(data)


async def update_statistics(account_id: int, name: str):
    sql = f"UPDATE statistics SET {name}=now() WHERE account_id={account_id}"
    await Database.execute(sql)


async def main():
    await Database.init()
    await MaksogramBot.init()

    for statistics in await get_statistics():
        if not await get_account_status(statistics.account_id):
            continue

        if statistics.answering_machine and time_now() - statistics.answering_machine >= timedelta(days=7):
            await MaksogramBot.send_message(
                statistics.account_id,
                "🤖 <b>Автоответчик</b>\nВы давно не пользовались автоответчиком. Это прекрасная функция с гибкими настройками!\n",
                reply_markup=IMarkup(rows=[KRow([IButton(text="Попробовать", data=cb('answering_machine').encode())])]))
            await update_statistics(statistics.account_id, 'answering_machine')

        elif time_now() - statistics.audio_transcription >= timedelta(days=14):
            await MaksogramBot.send_message(
                statistics.account_id,
                "🗣 </b>Расшифровка голосовых</b>\nВы очень давно не пользовались расшифровкой голосовых. Это отличная функция с быстрым ответом\n",
                reply_markup=IMarkup(rows=[KRow([IButton(text="Попробовать", data=cb('module', 'audio_transcription', False).encode())])]))
            await update_statistics(statistics.account_id, 'audio_transcription')

        elif time_now() - statistics.weather >= timedelta(days=7) and not statistics.morning_weather:
            await MaksogramBot.send_message(
                statistics.account_id,
                "🌤 </b>Прогноз погоды</b>\nВы давно не пользовались прогнозом погоды в чате. Ее можно включить по утрам\n",
                reply_markup=IMarkup(rows=[KRow([IButton(text="Попробовать", data=cb('module', 'weather', False).encode())])]))
            await update_statistics(statistics.account_id, 'weather')


if __name__ == '__main__':
    asyncio.run(main())
