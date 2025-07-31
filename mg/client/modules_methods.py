from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . maksogram_client import MaksogramClient

import os
import re
import asyncio

from typing import Optional, Literal
from datetime import datetime, timedelta
from mg.core.types import MaksogramBot, CustomEmoji
from mg.core.functions import www_path, format_error, time_now, get_subscription

from telethon.tl.patched import Message

from telethon.tl.types import (
    Document,
    MessageMediaDice,
    MessageMediaWebPage,

    MessageEntityUrl,
    MessageEntityBold,
    MessageEntityTextUrl,
    MessageEntitySpoiler,
    MessageEntityBlockquote,
    MessageEntityCustomEmoji,
)

from mg.modules.qr_code import qr_code
from mg.modules.weather import weather
from mg.modules.reminder import reminder
from mg.modules.calcualtor import calculator
from mg.modules.randomizer import randomizer
from mg.modules.round_video import round_video
from mg.modules.audio_transcription import audio_transcription
from mg.modules.currencies import currency_rate, ResultConvertionCurrencies

from mg.modules.types import NameModule
from mg.modules.functions import enabled_module, add_remind
from . functions import (
    len_text,
    is_one_line,
    download_voice,
    download_video,
    update_statistics_by_module,
)


months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "ноября", "декабря"]


class ModulesMethods:
    async def modules(self: 'MaksogramClient', message: Message) -> Optional[NameModule]:
        """
        Проверяет сообщение на наличие команды Maksogram в чате и осуществляет работу функции, если необходимо

        :param message: объект нового сообщения для проверки и обработки
        :return: `None`, если команда не распознана или модуль выключен, иначе название модуля
        """

        if not message.out and (message.voice or message.video_note) and message.file.duration >= 30:
            if await enabled_module(self.id, 'auto_audio_transcription'):
                message = await message.forward_to(MaksogramBot.id)
                await self.audio_transcription_module(message, None, message.voice or message.video_note)
                await MaksogramBot.send_message(self.id, "Автоматическая расшифровка голосового завершена")
                return

        text = (message.message or '').lower()
        bot = message.chat_id == MaksogramBot.id
        bot_audio, bot_voice, bot_video, bot_video_note, reply_audio, reply_voice, reply_video, reply_video_note = (None,) * 8

        if bot and not message.web_preview:  # Медиа в чате с ботом обрабатываются сразу, без команды
            bot_audio = message.audio
            bot_voice = message.voice
            bot_video = message.video
            bot_video_note = message.video_note

        # Сообщение в чате с ботом (сразу видео, кружок или гс) или в другом чате и содержит текст в одну строку,
        # отправлено от клиента, не имеет медиа (исключение - предпросмотр ссылок) ...
        if not (bot or is_one_line(text) and message.out and (message.media is None or isinstance(message.media, MessageMediaWebPage))):
            return  # ... иначе сообщение точно не является командой Maksogram в чате

        reply_message = await self.get_message_by_id(message.chat_id, message.reply_to_msg_id)  # Аргумент (медиа, текст...) команды
        if reply_message:
            reply_audio = reply_message.audio
            reply_voice = reply_message.voice
            reply_video = reply_message.video
            reply_video_note = reply_message.video_note

        entities = message.get_entities_text()

        # Калькулятор: одна строка без форматирования со знаком равенства в конце
        if is_one_line(text) and text.endswith('=') and message.entities is None:
            return await self.calculator_module(message)

        # Генератор QR: команда со ссылкой для генерации
        elif len(entities) == 1 and isinstance(entities[0][0], MessageEntityUrl) and \
                re.fullmatch(rf'(создай|создать|сгенерируй|сгенерировать|qr) *{entities[0][1]}', text):
            return await self.qr_code_module(message)

        # Расшифровка голосовых: кружок или голосовое в чате с ботом или команда с ответом на кружок или голосовое
        elif (bot_audio or bot_voice or bot_video_note) or \
                ((reply_audio or reply_voice or reply_video_note) and re.fullmatch(f'(в *текст|расшифруй|расшифровать)', text)):
            return await self.audio_transcription_module(message, reply_message, bot_audio or bot_voice or bot_video_note)

        # Погода: команда "Какая погода" или "Какая погода?"
        elif re.fullmatch(r'какая *погода\??', text):
            return await self.weather_module(message)

        # Видео в кружок: видео в чате с ботом или команда с ответом на видео
        elif bot_video or (reply_video and re.fullmatch('в *кружок', text)):
            return await self.round_video_module(message, reply_message, bot_video)

        # Напоминалка: команда с ответом на текст напоминания (или без)
        elif remind_time := await reminder(self.id, text):
            return await self.reminder_module(message, reply_message, remind_time)

        # Рандомайзер: команда для выбора числа, да/нет или элемента из списка
        elif choice := randomizer(text):
            return await self.randomizer_module(message, choice)

        # Конвертер валют: команда
        elif amount := currency_rate(text):
            return await self.currencies_module(message, amount)

    async def calculator_module(self: 'MaksogramClient', message: Message) -> Optional[Literal[NameModule.calculator]]:
        if await enabled_module(self.id, NameModule.calculator.name):
            response = calculator(message.message[:-1])
            if response:
                await message.edit(response)

                return NameModule.calculator

            await MaksogramBot.send_message(
                self.id, "🔢 <b>Калькулятор в чате</b>\nНеправильно введен пример для калькулятора")

        else:
            await MaksogramBot.send_message(
                self.id, "🔢 <b>Калькулятор в чате</b>\nЧтобы воспользоваться калькулятором, нужно его включить в /menu_chat")

    async def qr_code_module(self: 'MaksogramClient', message: Message) -> Optional[Literal[NameModule.qr_code]]:
        if await enabled_module(self.id, NameModule.qr_code.name):
            entity = message.entities[0]
            link = message.message[entity.offset: entity.offset + entity.length]
            file = qr_code(link)

            await message.edit("🤖 @MaksogramBot в чате\nГенератор QR-кода из ссылки", file=file,
                               formatting_entities=[MessageEntityCustomEmoji(0, 2, CustomEmoji.maksogram),
                                                    MessageEntityTextUrl(45, 6, link), MessageEntityBold(45, 6)])
            os.remove(file)

            return NameModule.qr_code

        else:
            await MaksogramBot.send_message(
                self.id, "🔗 <b>Генератор QR-кодов</b>Чтобы сгенерировать QR, нужно включить функцию в /menu_chat")

    async def audio_transcription_module(self: 'MaksogramClient', message: Message, reply_message: Optional[Message], bot_media: Document) -> Optional[Literal[NameModule.audio_transcription]]:
        if await enabled_module(self.id, NameModule.audio_transcription.name):
            if not await self.check_count_usage_module(NameModule.audio_transcription.name):
                if await get_subscription(self.id) is None:
                    await MaksogramBot.send_message(self.id, "🗣 <b>Расшифровка голосового</b>\nДостигнут лимит использования функции в день, "
                                                             "подключите Maksogram Premium!")
                else:
                    await MaksogramBot.send_message(self.id, "🗣 <b>Расшифровка голосового</b>\nДостигнут лимит количества использования функции в день")
                await MaksogramBot.send_system_message(f"Достигнут лимит лимит использования функции в день у {self.id}")

                return NameModule.audio_transcription

            if self.is_premium:
                text = "🤖 @MaksogramBot в чате\n🗣 Расшифровка голосового ✍️"
                formatting_entities = [MessageEntityCustomEmoji(0, 2, CustomEmoji.maksogram),
                                       MessageEntityCustomEmoji(24, 2, CustomEmoji.sound),
                                       MessageEntityCustomEmoji(50, 2, CustomEmoji.loading)]
            else:  # Не используем обычные эмодзи
                text = "@MaksogramBot в чате\nРасшифровка голосового..."
                formatting_entities = None

            if bot_media:  # Автоматически отправляем команду
                reply_message, message = message, await message.reply(text, formatting_entities=formatting_entities)
            else:
                await message.edit(text, formatting_entities=formatting_entities)

            path = await download_voice(self.id, reply_message)
            response = await audio_transcription(path)
            os.remove(www_path(path))

            if response.ok:
                text = f"🤖 @MaksogramBot в чате\n{response.text}"
                formatting_entities = [MessageEntityCustomEmoji(0, 2, CustomEmoji.maksogram),
                                       MessageEntityBlockquote(24, len(response.text), collapsed=True)]

                await self.update_limit(NameModule.audio_transcription.name)  # Обновляем количество использований, только если успешно
            else:
                text = f"🤖 @MaksogramBot в чате\nПроизошла ошибка при расшифровке..."
                formatting_entities = [MessageEntityCustomEmoji(0, 2, CustomEmoji.maksogram)]
                await MaksogramBot.send_system_message(format_error(response.error))

            await message.edit(text, formatting_entities=formatting_entities)
            await update_statistics_by_module(self.id, NameModule.audio_transcription.name)

            return NameModule.audio_transcription

        else:
            await MaksogramBot.send_message(
                self.id, "🗣 <b>Расшифровка голосового</b>\nЧтобы расшифровать голосовое, нужно включить функцию в /menu_chat")

    async def weather_module(self: 'MaksogramClient', message: Message) -> Optional[Literal[NameModule.weather]]:
        if await enabled_module(self.id, NameModule.weather.name):
            response = await weather(self.id)

            if response.ok:
                text = f"🤖 @MaksogramBot в чате\n\nПогода в городе {response.city}\n{response.weather}"
                formatting_entities = [MessageEntityCustomEmoji(0, 2, CustomEmoji.maksogram),
                                       MessageEntityBold(25, len(f"Погода в городе {response.city}")),
                                       MessageEntityBlockquote(25 + len(f"Погода в городе {response.city}\n"), len_text(response.weather), collapsed=True)]
            else:
                text = "🤖 @MaksogramBot в чате\nВозникла ошибка при запросе"
                formatting_entities = [MessageEntityCustomEmoji(0, 2, CustomEmoji.maksogram)]
                await MaksogramBot.send_system_message(format_error(response.error))

            await message.edit(text, formatting_entities=formatting_entities)

            return NameModule.weather

        else:
            await MaksogramBot.send_message(
                self.id, "<b>Погода в чате</b>\nЧтобы получить прогноз погоды, нужно включить функцию в /menu_chat")

    async def round_video_module(self: 'MaksogramClient', message: Message, reply_message: Message, bot_media: bool) -> Optional[Literal[NameModule.round_video]]:
        if await enabled_module(self.id, NameModule.round_video.name):
            if not await self.check_count_usage_module(NameModule.round_video.name):
                if await get_subscription(self.id) is None:
                    await MaksogramBot.send_message(self.id, "🔄 <b>Видео в кружок</b>\nДостигнут лимит использования функции в день, "
                                                    "подключите Maksogram Premium!")
                else:
                    await MaksogramBot.send_message(self.id, "🔄 <b>Видео в кружок</b>\nДостигнут лимит количества использования функции в день")
                await MaksogramBot.send_system_message(f"Достигнут лимит лимит использования функции в день у {self.id}")

                return NameModule.round_video

            text = "🤖 @MaksogramBot в чате\nКонвертация видео в кружок ⏰"
            formatting_entities = [MessageEntityCustomEmoji(0, 2, CustomEmoji.maksogram),
                                   MessageEntityCustomEmoji(51, 1, CustomEmoji.round_loading)]

            if bot_media:  # Автоматически отправляем команду
                reply_message, message = message, await message.reply(text, formatting_entities=formatting_entities)
            else:
                await message.edit(text, formatting_entities=formatting_entities)

            if reply_message.file.duration >= 60:
                await message.edit("🤖 @MaksogramBot в чате\nВидео слишком длинное! ⚠️",
                                   formatting_entities=[MessageEntityCustomEmoji(0, 2, CustomEmoji.maksogram),
                                                        MessageEntityCustomEmoji(47, 2, CustomEmoji.warning)])
            else:
                response = round_video(await download_video(self.id, reply_message))

                if response.ok:
                    await message.edit("🤖 @MaksogramBot в чате\nОтправка кружка ⏰",
                                       formatting_entities=[MessageEntityCustomEmoji(0, 2, CustomEmoji.maksogram),
                                                            MessageEntityCustomEmoji(40, 1, CustomEmoji.round_loading)])

                    await self.client.send_file(message.chat_id, file=response.path, video_note=True)
                    await message.delete()
                    os.remove(response.path)

                    await self.update_limit(NameModule.round_video.name)  # Обновляем количество использований, только если успешно

                else:
                    await MaksogramBot.send_system_message(format_error(response.error))
                    await message.edit("🤖 @MaksogramBot в чате\nПроизошла ошибка... ⚠️",
                                       formatting_entities=[MessageEntityCustomEmoji(0, 2, CustomEmoji.maksogram),
                                                            MessageEntityCustomEmoji(44, 2, CustomEmoji.warning)])

            return NameModule.round_video

        else:
            await MaksogramBot.send_message(
                self.id, "🔄 <b>Видео в кружок</b>\nЧтобы конвертировать видео в кружок, нужно включить функцию в /menu_chat")

    async def reminder_module(self: 'MaksogramClient', message: Message, reply_message: Optional[Message], remind_time: datetime) -> Optional[Literal[NameModule.reminder]]:
        if await enabled_module(self.id, NameModule.reminder.name):
            if not await self.check_count_usage_module(NameModule.reminder.name):
                if await get_subscription(self.id) is None:
                    await MaksogramBot.send_message(self.id, "⏰ <b>Напоминалка в чате</b>\nДостигнут лимит использования функции в день, "
                                                             "подключите Maksogram Premium!")
                else:
                    await MaksogramBot.send_message(self.id, "⏰ <b>Напоминалка в чате</b>\nДостигнут лимит количества использования функции в день")
                await MaksogramBot.send_system_message(f"Достигнут лимит лимит использования функции в день у {self.id}")

                return NameModule.reminder

            time_zone = await self.get_time_zone()
            time = remind_time - timedelta(hours=time_zone)
            chat_name = await self.chat_name(message.chat_id, my_name="Избранное")

            response = await add_remind(self.id, reply_message or message, time, chat_name)
            if not response:  # Напоминание с такими параметрами уже существует
                await message.edit("🤖 @MaksogramBot в чате\nНапоминание уже существует ⚠️",
                                   formatting_entities=[MessageEntityCustomEmoji(0, 2, CustomEmoji.maksogram),
                                                        MessageEntityCustomEmoji(51, 2, CustomEmoji.warning)])
                return NameModule.reminder

            self.logger.info(f"создано напоминание в {time} на сообщение (chat_id={message.chat_id}, id={message.id})")

            if message.chat_id == self.id:  # Избранное
                await MaksogramBot.send_message(self.id, "Создавать напоминания можно в чате со мной, чтобы не забивать Избранное")

            # Определяем дату и время человекочитаемого формата
            human_time = f"{remind_time.hour:02d}:{remind_time.minute:02d}"
            if remind_time.date() == time_now(time_zone).date():  # Сегодня
                human_date = "сегодня"
            elif remind_time.date() == (time_now(time_zone) + timedelta(days=1)).date():  # Завтра
                human_date = "завтра"
            elif remind_time.date() == (time_now(time_zone) + timedelta(days=2)).date():  # Послезавтра
                human_date = "послезавтра"
            else:
                human_date = f"{remind_time.day} {months[remind_time.month-1]}"  # 1 января
                if remind_time.year == time_now(time_zone).year + 1:  # Следующий год
                    human_date += " следующего года"
                elif remind_time.year != time_now(time_zone).year:  # Следующих годов
                    human_date += f" {remind_time.year} года"

            await message.edit(f"🤖 @MaksogramBot в чате\nНапоминание на {human_date} в {human_time} ⏰",
                               formatting_entities=[MessageEntityCustomEmoji(0, 2, CustomEmoji.maksogram),
                                                    MessageEntityCustomEmoji(48 + len(human_date), 1, CustomEmoji.clock)])

            await self.update_limit(NameModule.reminder.name)
            return NameModule.reminder

        else:
            await MaksogramBot.send_message(
                self.id, "⏰ <b>Напоминалка в чате</b>\nЧтобы создать напоминание, нужно включить функцию в /menu_chat")

    async def randomizer_module(self: 'MaksogramClient', message: Message, choice: str) -> Optional[Literal[NameModule.randomizer]]:
        if await enabled_module(self.id, NameModule.randomizer.name):
            await message.respond(file=MessageMediaDice(0, "🎲"))
            await asyncio.sleep(3)  # Ждем окончания анимации кубика

            await message.reply(f"🤖 @MaksogramBot выбирает {choice}",
                                formatting_entities=[MessageEntityCustomEmoji(0, 2, CustomEmoji.maksogram),
                                                     MessageEntitySpoiler(26, len_text(choice))])

            return NameModule.randomizer

        else:
            await MaksogramBot.send_message(
                self.id, "🎲 <b>Рандомайзер в чате</b>\nЧтобы воспользоваться рандомайзером, включите функцию в /menu_chat")

    async def currencies_module(self: 'MaksogramClient', message: Message, amount: ResultConvertionCurrencies) -> Optional[Literal[NameModule.currencies]]:
        if await enabled_module(self.id, NameModule.currencies.name):
            response = await amount(self.id)
            await message.edit(f"🤖 @MaksogramBot в чате\n{response}",
                               formatting_entities=[MessageEntityCustomEmoji(0, 2, CustomEmoji.maksogram)])

            return NameModule.currencies

        else:
            await MaksogramBot.send_message(
                self.id, "💱 <b>Конвертер валют в чате</b>\nЧтобы получить курсы валют, включите функцию в /menu_chat")
