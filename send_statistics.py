import asyncio

from datetime import timedelta
from core import db, time_now, MaksogramBot, SITE


async def main():
    for statistics in await db.fetch_all("SELECT account_id, answering_machine, audio_transcription, weather FROM statistics"):
        if time_now() - statistics['answering_machine'] >= timedelta(days=7):
            await MaksogramBot.send_message(
                statistics['account_id'],
                "🤖 Автоответчик\nВы давно не пользовались автоответчиком. Это прекрасная функция с гибкими настройками!\n",
                reply_markup=MaksogramBot.IMarkup(inline_keyboard=[[MaksogramBot.IButton(
                    text="Обзор автоответчика", url=f"{SITE}#автоответчик")]]))
            await db.execute(f"UPDATE statistics SET answering_machine=now() WHERE account_id={statistics['account_id']}")
        elif time_now() - statistics['audio_transcription'] >= timedelta(days=7):
            await MaksogramBot.send_message(
                statistics['account_id'],
                "🗣 Расшифровка ГС\nВы давно не пользовались расшифровкой гс. Это прекрасная функция с быстрым ответом!",
                reply_markup=MaksogramBot.IMarkup(inline_keyboard=[[MaksogramBot.IButton(
                    text="Обзор расшифровки ГС", url=f"{SITE}#расшифровка-гс")]]))
            await db.execute(f"UPDATE statistics SET audio_transcription=now() WHERE account_id={statistics['account_id']}")
        elif time_now() - statistics['weather'] >= timedelta(days=7):
            await MaksogramBot.send_message(
                statistics['account_id'],
                "🌤 Погода\nВы давно не пользовались погодой. Это прекрасная функция, которая работает по команде или утром!",
                reply_markup=MaksogramBot.IMarkup(inline_keyboard=[[MaksogramBot.IButton(
                    text="Обзор функции погода", url=f"{SITE}#погода")]]))
            await db.execute(f"UPDATE statistics SET weather=now() WHERE account_id={statistics['account_id']}")


if __name__ == '__main__':
    asyncio.run(main())
