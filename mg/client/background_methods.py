from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . maksogram_client import MaksogramClient


import os
import asyncio

from mg.config import CHANNEL_ID

from datetime import timedelta
from mg.core.database import Database
from mg.core.types import MaksogramBot, CustomEmoji
from mg.core.functions import (
    time_now,
    www_path,
    error_notify,
)

from telethon.utils import get_input_channel
from aiogram.exceptions import TelegramBadRequest
from telethon.tl.functions.channels import GetAdminLogRequest
from telethon.tl.types import MessageEntityCustomEmoji, PeerChannel

from telethon.tl.types import KeyboardButtonRow as BRow
from telethon.tl.types import ReplyInlineMarkup as IMarkup
from telethon.tl.types import KeyboardButtonSwitchInline as IButton

from mg.changed_profile.types import ChangedProfileSettings
from mg.changed_profile.functions import (
    get_bio,
    get_gifts,
    get_avatars,
    download_gift,
    delete_avatars,
    download_avatars,
    update_changed_profile,
    get_changed_profiles_settings,
)

from mg.modules.functions import get_reminds, delete_remind
from . functions import get_min_admin_log_id, set_min_admin_log_id
from mg.fire.functions import get_fires, update_fire_status, edit_fire_message, reset_fire, clear_fire


class BackgroundMethods:
    @error_notify()
    async def changed_profile_center(self: 'MaksogramClient'):
        while True:  # Остановка через account_off (async_processes)
            for user in await get_changed_profiles_settings(self.id):
                if user.avatars is not None:
                    await self.avatars_center(user)

                if user.gifts is not None:
                    await self.gifts_center(user)

                if user.bio is not None:
                    await self.bio_center(user)

            await asyncio.sleep(5*60)

    async def avatars_center(self: 'MaksogramClient', user: ChangedProfileSettings):
        avatars = await get_avatars(self.id, user.user_id)
        if avatars is None:  # Количество аватарок превышает допустимое
            delete_avatars(self.id, user.user_id)
            await update_changed_profile(self.id, user.user_id, "avatars")
            return

        user_link = f"<a href='tg://openmessage?user_id={user.user_id}'>{user.name}</a>"

        for avatar in avatars.values():
            if avatar.avatar_id not in user.avatars:  # Новая аватарка
                path = (await download_avatars(self.id, user.user_id, avatars={avatar.avatar_id: avatar}))[0]
                await MaksogramBot.send_message(
                    self.id, f"📸 <b>{user_link}</b> добавил(а) аватарку", file=path,
                    reply_markup=IMarkup(rows=[BRow([IButton(text="Поделиться аватаркой", query=f"avatar {path.split('/')[-1]}")])]))

            else:
                user.avatars.pop(avatar.avatar_id)

        for avatar_id, saved_avatar in user.avatars.items():  # Удаленные аватарки
            path = www_path(f"avatars/{self.id}.{user.user_id}.{avatar_id}.{saved_avatar.ext}")
            await MaksogramBot.send_message(self.id, f"📸 <b>{user_link}</b> удалил(а) аватарку", file=path)
            os.remove(path)

        new_avatars = Database.serialize({str(avatar_id): avatar.to_dict() for avatar_id, avatar in avatars.items()})
        await update_changed_profile(self.id, user.user_id, "avatars", new_avatars)

    async def gifts_center(self: 'MaksogramClient', user: ChangedProfileSettings):
        gifts = await get_gifts(self.id, user.user_id)
        if gifts is None:  # Количество подарков превышает допустимое
            await update_changed_profile(self.id, user.user_id, "gifts")
            return

        user_link = f"<a href='tg://openmessage?user_id={user.user_id}'>{user.name}</a>"

        for gift in gifts.values():
            if gift.gift_id not in user.gifts:  # Новый подарок
                giver = gift.giver.link if gift.giver else "неизвестного пользователя"

                if gift.unique:  # Уникальный подарок
                    link = f"t.me/nft/{gift.slug}"
                    await MaksogramBot.send_message(
                        self.id, f"🎁 <b>{user_link}</b> получил(а) <a href='{link}'>{gift.type}</a> от {giver}")

                else:  # Неуникальный подарок
                    path = await download_gift(self.id, user.user_id, gift)
                    await MaksogramBot.send_file(self.id, path, None)
                    os.remove(path)

                    await MaksogramBot.send_message(self.id, f"🎁 <b>{user_link}</b> получил(а) {gift.type} от {giver}")

                self.logger.info(f"Новый подарок у {user.user_id}: {gift.stringify()}")

            else:  # Подарок мог стать уникальным
                if gift.unique and not user.gifts[gift.gift_id].unique:  # Подарок стал уникальным
                    link = f"t.me/nft/{gift.slug}"
                    await MaksogramBot.send_message(
                        self.id, f"🎁 <b>{user_link}</b> улучшил(а) <a href='{link}'>лимитированный подарок</a>")

                    self.logger.info(f"Подарок у {user.user_id} стал уникальным: {gift.stringify()}")

                user.gifts.pop(gift.gift_id)

        if count_hidden_gifts := len(user.gifts):  # Исчезнувшие подарки (скрытые, проданные, переданные)
            gift_str = "подарок" if count_hidden_gifts == 1 else f"{count_hidden_gifts} подарков"
            await MaksogramBot.send_message(
                self.id, f"🎁 <b>{user_link}</b> скрыл(а) (возможно, продал(а)) {gift_str}")

            self.logger.info(f"{gift_str.capitalize()} у {user.user_id} скрыт(ы): {', '.join(gift.stringify() for gift in user.gifts.values())}")

        new_gifts = Database.serialize({str(gift_id): gift.to_dict() for gift_id, gift in gifts.items()})
        await update_changed_profile(self.id, user.user_id, "gifts", new_gifts)

    async def bio_center(self: 'MaksogramClient', user: ChangedProfileSettings):
        bio = await get_bio(self.id, user.user_id)

        if user.bio != bio:
            user_link = f"<a href='tg://user?id={user.user_id}'>{user.name}</a>"

            await MaksogramBot.send_message(self.id, f"🖼️ <b>{user_link}</b> изменил(а) «О себе»\n"
                                                     f"<blockquote>{user.bio}</blockquote>\n"
                                                     "👇👇👇👇👇👇👇\n"
                                                     f"<blockquote>{bio}</blockquote>")

            await update_changed_profile(self.id, user.user_id, "bio", bio)
            self.logger.info(f"Обновлено описание {user.user_id}: {repr(user.bio)} => {bio}")

    @error_notify()
    async def reminder_center(self: 'MaksogramClient'):
        """Центр напоминалки для клиента"""

        while True:  # Остановка через account_off (async_processes)
            for remind in await get_reminds(self.id):
                if remind.chat_id == MaksogramBot.id:
                    place = ""
                elif remind.chat_id == self.id:  # Избранное
                    place = "в Избранном"
                else:
                    place = f"в чате с {remind.chat_name}"

                await self.client.send_message(
                    remind.chat_id, "🤖 @MaksogramBot в чате\nНапоминание о событии! ⏰", reply_to=remind.message_id,
                    formatting_entities=[MessageEntityCustomEmoji(0, 2, CustomEmoji.maksogram),
                                         MessageEntityCustomEmoji(47, 1, CustomEmoji.clock)])
                await MaksogramBot.send_message(
                    self.id, f"⏰ <b>Напоминалка</b>\nНапоминаю о вашем событии {place}")

                await delete_remind(self.id, remind.chat_id, remind.message_id, remind.time)
                self.logger.info(f"Сработало напоминание {remind.stringify()}")

            await wait_minute()

    @error_notify()
    async def admin_logger(self: 'MaksogramClient'):
        if not self.is_owner:
            return

        while True:  # Остановка через account_off (async_processes)
            min_id = await get_min_admin_log_id()

            request = GetAdminLogRequest(
                channel=get_input_channel(await self.client.get_input_entity(PeerChannel(channel_id=CHANNEL_ID))),
                q='',
                max_id=0,
                min_id=min_id,
                limit=100,
            )
            admin_events = (await self.client(request)).events

            if admin_events:
                events = ""
                for event in admin_events:
                    events += event.action.__class__.__name__.replace("ChannelAdminLogEventAction", "") + '\n'

                new_min_id = max(map(lambda x: x.id, admin_events))
                await set_min_admin_log_id(new_min_id)

                await MaksogramBot.send_system_message(f"<b>Недавние действия</b>\n{events}")

            await asyncio.sleep(60*60)

    @error_notify()
    async def fire_center(self: 'MaksogramClient'):
        while True:  # Остановка через account_off (async_processes)
            if time_now(await self.get_time_zone()).hour != 0:
                await asyncio.sleep(55 * 60)  # Ждем 55 минут
                continue

            for fire in await get_fires(self.id):
                if time_now() - fire.updating_time < timedelta(hours=1):
                    continue  # Создание огонька или его сброс был недавно

                if fire.reset:
                    await clear_fire(fire.account_id, fire.user_id)
                    fire.account_status = False; fire.user_status = False; fire.reset = False; fire.days = 0; fire.score = 0
                    self.logger.info(f"Огонек с {fire.user_id} был потерян")

                elif fire.active:
                    await update_fire_status(fire.account_id, fire.user_id, 'reset')
                    fire.account_status = False; fire.user_status = False
                    self.logger.info(f"Огонек с {fire.user_id} встречает новый день")

                else:  # Огонек продлить не успели
                    await reset_fire(fire.account_id, fire.user_id)
                    fire.account_status = False; fire.user_status = False; fire.reset = True
                    self.logger.info(f"Огонек с {fire.user_id} продлить не успели")

                try:
                    await edit_fire_message(fire)  # Обновляем сообщение огонька в чате
                except TelegramBadRequest:
                    await MaksogramBot.send_message(self.id, "Сообщение огонька в чате с другом удалено. Чтобы восстановить его, "
                                                             "создайте его заново. При этом все данные с серией и счетом НЕ будут потеряны")

            await asyncio.sleep(55 * 60)  # Ждем 55 минут


async def wait_minute():
    """Ожидание следующей минуты"""

    await asyncio.sleep(((time_now() + timedelta(minutes=1, seconds=5)).replace(second=0, microsecond=0) - time_now()).seconds)
