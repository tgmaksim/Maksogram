from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . maksogram_client import MaksogramClient


import os
import random

from typing import Optional
from mg.bot.types import CallbackData
from datetime import timedelta, datetime
from mg.client.functions import len_text
from mg.core.types import morning, MaksogramBot
from mg.core.functions import time_now, get_account_status, resources_path, format_error

from telethon.events import UserUpdate
from telethon.tl.types import UserStatusOnline, MessageEntityBlockquote, MessageEntityBold

from telethon.tl.types import KeyboardButtonRow as BRow
from telethon.tl.types import ReplyInlineMarkup as IMarkup
from telethon.tl.types import KeyboardButtonCallback as IButton

from mg.modules.weather import weather
from . functions import get_morning_functions
from mg.modules.functions import get_my_currencies
from mg.modules.currencies import currency_rate, currencies
from mg.status_users.functions import get_user_settings, update_statistics, update_status_user, get_my_users_settings


cb = CallbackData()


class UserUpdatesMethods:
    async def user_update(self: 'MaksogramClient', event: UserUpdate.Event):
        status = isinstance(event.status, UserStatusOnline)
        user_id = event.chat_id

        if await get_account_status(user_id):
            return  # Для клиентов обработка происходит в self_update

        if self.status_users[user_id] == status:
            return  # Статус не изменился
        self.status_users[user_id] = status

        user = await get_user_settings(self.id, user_id)
        status_str = None

        if user.statistics:
            await update_statistics(self.id, user_id, status)

        if status and user.online:
            status_str = "в сети"
        elif not status and user.offline:
            status_str = "вышел(а) из сети"

        if user.awake and status:
            time_zone = await self.get_time_zone()
            time = time_now(time_zone)
            last_notification = user.awake + timedelta(hours=time_zone)

            if morning[0] <= time.hour < morning[1] and not \
                    (last_notification.date() == time.date() and morning[0] <= last_notification.hour < morning[1]):
                await update_status_user(self.id, user_id, 'awake', time_now())
                status_str = "проснул(а)ся"

        if status_str:
            name = await self.chat_name(user_id)
            markup = IMarkup(rows=[BRow([IButton(text="Настройки", data=cb('status_user', user_id, 'new').encode())])])
            await MaksogramBot.send_message(self.id, f"🌐 {name} {status_str}", reply_markup=markup)

    async def self_update(self: 'MaksogramClient', event: UserUpdate.Event):
        status = isinstance(event.status, UserStatusOnline)
        real_status = isinstance((await self.client.get_me()).status, UserStatusOnline)

        if status != real_status or self.status == status:
            return  # Статус не соответствует действительности или не изменился
        self.set_status(status)

        awake_time = status and await self.check_awake()
        gender = await self.get_gender()

        my_users_settings = await get_my_users_settings(self.id)
        for user_settings in my_users_settings:
            if user_settings.statistics:
                await update_statistics(user_settings.id, self.id, status)

            if awake_time and user_settings.awake:
                status_str = "проснулся" if gender is True else "проснулась" if gender is False else "проснул(а)ся"
            elif status and user_settings.online:
                status_str = "в сети"
            elif not status and user_settings.offline:
                status_str = "вышел из сети" if gender is True else "вышла из сети" if gender is False else "вышел(а) из сети"
            else:
                continue  # Не нужно оповещать о статусе

            markup = IMarkup(rows=[BRow([IButton(text="Настройки", data=cb('status_user', self.id, 'new').encode())])])
            await MaksogramBot.send_message(user_settings.id, f"🌐 {user_settings.name} {status_str}", reply_markup=markup)

        if not awake_time:
            return  # Уведомление утром не требуется

        await self.update_awake_time()  # Обновляем время пробуждения

        await self.good_morning(awake_time, gender)  # Поздравляем с праздниками или просто отправляем утреннее сообщение

    async def good_morning(self: 'MaksogramClient', time: datetime, gender: Optional[bool]):
        birthday = await self.get_my_birthday()
        if birthday and birthday.month == time.month and birthday.day == time.day:
            await self.send_postcard("holidays/birthday", "Доброе утро! С днем рождения 🥳\nВсего самого лучшего! 🎊 🎁")

        elif time.date().month == 1 and time.date().day == 1:  # Поздравление с Новым годом
            await self.send_postcard("holidays/new_year", f"Доброе утро!\nС Новым {time.date().year} годом! 🎄")

        elif time.date().month == 2 and time.date().day == 23 and gender is True:  # Поздравление с 23 февраля
            await self.send_postcard("holidays/man", "С добрым утром! Поздравляю с 23 февраля 😎")

        elif time.date().month == 3 and time.date().day == 1:  # Поздравление с первым днем весны
            await self.send_postcard("holidays/1march", "Доброе утро!\nС первым днем весны ☀️")

        elif time.date().month == 3 and time.date().day == 8 and gender is False:  # Поздравление с 8 марта
            await self.send_postcard("holidays/woman", "С добрым утром! Поздравляю с 8 марта 🥰")

        elif time.date().month == 4 and time.date().day == 1:  # Поздравление с первым апреля
            await self.send_postcard("holidays/1april", "С добрым утром! Поздравляю с днем веселья! 🤡")

        elif time.date().month == 5 and time.date().day == 1:  # Поздравление с днем весны и труда
            await self.send_postcard("holidays/1may", "С добрым утром!\nПоздравляю с днем весны и труда! ☀️")

        elif time.date().month == 5 and time.date().day == 9:  # Поздравление с днем Великой Победы
            await self.send_postcard("holidays/victory_day", "С добрым утром! Поздравляю с Днем Победы! ⭐️")

        elif time.date().month == 6 and time.date().day == 1:  # Поздравление с первым днем лета
            await self.send_postcard("holidays/1june", "С добрым утром! Поздравляю с первым днем лета! 🌤")

        elif time.date().month == 9 and time.date().day == 1:  # Поздравление с днем знаний
            await self.send_postcard("holidays/1september", "С добрым утром! Поздравляю с днем знаний! 🤓")

        elif time.date().month == 12 and time.date().day == 9:  # Информация о дне рождении
            await self.send_postcard("holidays/owner_birthday", "С добрым утром! Сегодня у создателя Maksogram день рождения! Поздравь его "
                                                                "лично или в комментариях канала. Ему будет очень приятно")

        else:  # Обычное утро
            morning_weather, morning_currencies = await get_morning_functions(self.id)
            if not (morning_weather or morning_weather):
                return

            text = "Доброе утро! Как спалось? 😉\n\n"
            entities = []

            if gender is True:  # Мужчина
                postcard = random.choice(os.listdir(resources_path("good_morning/man")))
                photo = resources_path(f"good_morning/man/{postcard}")
            elif gender is False:  # Женщина
                postcard = random.choice(os.listdir(resources_path("good_morning/woman")))
                photo = resources_path(f"good_morning/woman/{postcard}")
            else:
                photo = None

            if morning_weather:
                response = await weather(self.id)
                if response.ok:
                    entities.append(MessageEntityBlockquote(len_text(text), 16 + len(response.city) + 2 + len_text(response.weather), collapsed=True))
                    entities.append(MessageEntityBold(len_text(text) + 16, len(response.city)))
                    text += f"Погода в городе {response.city}\n\n{response.weather}\n"
                else:
                    await MaksogramBot.send_system_message(format_error(response.error))

            if morning_currencies:
                results = []
                my_currencies = await get_my_currencies(self.id) or list(currencies.keys())

                for amount in currency_rate(my_currencies=my_currencies):
                    results.append(await amount(self.id))
                result = '\n'.join(results)

                entities.append(MessageEntityBlockquote(len_text(text), 13 + len(result), collapsed=True))
                entities.append(MessageEntityBold(len_text(text), 11))
                text += f"Курсы валют\n\n{result}"

            await MaksogramBot.send_message(self.id, text, file=photo, formatting_entities=entities)

    async def send_postcard(self: 'MaksogramClient', postcard_dir: str, text: str):
        """Выбирает случайную картинку в папке и отправляет ее клиенту с текстом"""

        postcard = random.choice(os.listdir(resources_path(postcard_dir)))
        photo = resources_path(f"{postcard_dir}/{postcard}")

        await MaksogramBot.send_message(self.id, text, file=photo)

    async def check_awake(self: 'MaksogramClient') -> Optional[datetime]:
        """Проверяет время на утро с учетом часового пояса, пробуждение и возвращает это время, если утро"""

        time_zone = await self.get_time_zone()
        time = time_now(time_zone)
        awake_time = self.awake_time + timedelta(hours=time_zone)

        if not (morning[0] <= time.hour < morning[1]):
            return  # Не утро
        if time.date() == awake_time.date() and morning[0] <= awake_time.hour < morning[1]:
            return  # Сегодня уже отправлено

        return time
