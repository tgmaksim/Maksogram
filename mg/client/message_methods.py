from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . maksogram_client import MaksogramClient


import os

from datetime import timedelta
from mg.core.types import MaksogramBot
from mg.bot.types import CallbackData, support
from mg.admin.functions import reload_maksogram
from mg.client.functions import check_edited_message
from mg.core.functions import resources_path, deserialize_tl_entities, send_email_message, format_error, time_now

from telethon.errors.rpcerrorlist import (
    FileReferenceExpiredError,
    ChatForwardsRestrictedError,
)
from telethon.tl.patched import Message
from telethon.tl.types import KeyboardButtonRow as BRow
from telethon.tl.types import ReplyInlineMarkup as IMarkup
from telethon.tl.types import KeyboardButtonCallback as IButton
from telethon.tl.types import (
    UpdateNewAuthorization,

    MessageService,
    StarGiftUnique,
    MessageReplyHeader,
    MessageActionStarGift,
    MessageActionStarGiftUnique,

    MessageMediaPhoto,
    MessageMediaDocument,
    MessageMediaUnsupported,
)
from telethon.events import (
    NewMessage,
    MessageRead,
    MessageEdited,
    MessageDeleted,
)

from . functions import (
    media_id,
    is_storable_message,
)

from mg.security.functions import enabled_security_hack, get_security_settings, stop_recovery
from mg.speed_answers.functions import get_speed_answer_by_text, get_path_speed_answer_media
from mg.status_users.functions import update_last_message, get_user_settings, update_status_user, update_reading_statistics
from mg.answering_machine.functions import get_enabled_auto_answer, get_path_auto_answer_media, update_auto_answer_triggering


cb = CallbackData()

MAX_DURATION_VOICE = 600  # 10 минут
MAX_SIZE_FILE = 20 * 2**20  # 20 МБ


class MessageMethods:
    async def new_message(self: 'MaksogramClient', event: NewMessage.Event):
        message: Message = event.message

        if self.is_owner and message.message == "reload" and message.chat_id == self.id:
            await self.client.send_message(self.id, "Сервер перезапускается")
            self.logger.info("перезапуск сервера")
            await reload_maksogram()
            return

        if isinstance(message.media, MessageMediaUnsupported):
            await MaksogramBot.send_system_message(f"Неопознанный объект MessageMediaUnsupported у {self.id}")
            self.logger.warning(f"MessageMediaUnsupported: {message.chat_id}, {message.id}")
            return  # Медиа с MessageMediaUnsupported не обрабатывается

        if not is_storable_message(message):
            self.logger.info(f"сообщение с {message.media.__class__.__name__} не является сохраняемым")
            return  # Сообщение содержит медиа, которое не сохраняется

        if await self.speed_answers(event):
            return  # При отправке сокращения быстрого ответа сообщение удаляется

        await self.answering_machine(event)

        if module := await self.modules(message):
            if not self.is_owner:
                await MaksogramBot.send_system_message(
                    f"💬 <b>Maksogram в чате</b>\n<b>{self.name}</b> воспользовал(а)ся Maksogram в чате ({module})")
            return  # При срабатывании Maksogram в чате сохранение сообщения не происходит

        if message.out and event.is_private:  # Сообщение отправлено клиентом в личном чате
            await update_last_message(self.id, message.chat_id)  # Для будущего подсчета статистики времени прочтения

        if not await self.enabled_saving_messages():
            return  # "Сохранение сообщений" выключено в настройках

        if await self.save_self_destructing_message(message):
            return  # Самоуничтожающиеся сообщения обрабатываются только отдельно

        try:
            saved_message: Message = await message.forward_to(self.my_messages)
        except ChatForwardsRestrictedError as e:
            self.logger.info(f"сообщение не удалось переслать из-за ошибки {e.__class__.__name__} ({e})")
            return

        if saved_message.button_count:  # Сообщение содержит кнопку, поэтому комментарии под постом останутся недоступными
            saved_message: Message = await saved_message.reply("Сообщение выше")  # Исправляем это

        await self.add_saved_message(message, saved_message.id)

    async def save_self_destructing_message(self: 'MaksogramClient', message: Message) -> bool:
        """
        Сохраняет самоуничтожающееся сообщение, которое нельзя переслать в системный канал.
        Сохраняет все видеосообщения (кружки), голосовые сообщения с длительностью
            до `MAX_DURATION_VOICE` и другие медиа до `MAX_SIZE_FILE`

        :param message: самоуничтожающееся сообщение
        :return: `True`, если сообщение является самоуничтожающимся, иначе `False`
        """

        if isinstance(message.media, (MessageMediaPhoto, MessageMediaDocument)) and message.media.ttl_seconds:
            if message.video_note or (message.voice and message.file.duration < MAX_DURATION_VOICE) or message.file.size <= MAX_SIZE_FILE:

                await MaksogramBot.send_message(
                    self.id, "‼️ Сохраняется одноразовое медиа... Не смотрите его, пока процесс не завершится")

                path = resources_path(f"self-destructing_media/{self.id}.{media_id(message)}.{message.file.ext}")

                try:
                    await self.client.download_media(message, path)
                except FileReferenceExpiredError:  # Доступ потерян
                    await MaksogramBot.send_message(self.id, "⚠️ Не удалось сохранить одноразовое медиа, так как Вы его посмотрели")
                    self.logger.info("не удалось сохранить самоуничтожающееся сообщение из-за потери доступа")
                    return True  # Сообщение является самоуничтожающимся

                saved_message: Message = await self.client.send_file(
                    self.my_messages, path, caption=message.message, video_note=bool(message.video_note), voice_note=bool(message.voice))
                link = self.link_to_saved_message(saved_message.id)
                await MaksogramBot.send_message(self.id, f"Сохранено <a href='{link}'>одноразовое медиа</a>")

                os.remove(path)
                self.logger.info("успешно сохранено самоуничтожающееся сообщение")

            else:  # Сообщение превысило лимиты
                user_name = self.chat_name(message.chat_id)
                await MaksogramBot.send_message(self.id, f"В чате с {user_name} замечено одноразовое медиа, "
                                                         f"но его размер превысил лимит, поэтому оно не было сохранено")

                self.logger.info("самоуничтожающееся сообщение не сохранено из-за размеров")

            return True  # Сообщение является самоуничтожающимся

        return False  # Сообщение не является самоуничтожающимся

    async def speed_answers(self: 'MaksogramClient', event: NewMessage.Event) -> bool:
        message: Message = event.message

        if not message.out:
            return False  # Быстрый ответы работают только у клиента

        answer = await get_speed_answer_by_text(self.id, message.message.lower())
        if not answer:
            return False

        entities = deserialize_tl_entities(answer.entities)
        file = get_path_speed_answer_media(self.id, answer.id, answer.media.access_hash, answer.media.ext) if answer.media else None

        if answer.send:
            if isinstance(message.reply_to, MessageReplyHeader) and (reply := await self.get_message_by_id(message.chat_id, message.reply_to_msg_id)):
                await reply.reply(answer.text, formatting_entities=entities, file=file)
            else:
                await message.respond(answer.text, formatting_entities=entities, file=file)
            await message.delete()
        else:
            await message.edit(answer.text, formatting_entities=entities, file=file)

        return True

    async def answering_machine(self: 'MaksogramClient', event: NewMessage.Event) -> bool:
        message: Message = event.message
        text = message.message.lower()

        if not message.is_private or message.out or message.chat_id == self.id:
            return False  # Автоответчик не работает в групповых чатах, Избранном и не реагирует на сообщение клиента

        answer = await get_enabled_auto_answer(self, text)
        if not answer:
            return False

        if answer.offline and not self.offline:
            return False  # Автоответ не работает, когда клиент в сети

        contact: bool = (await message.get_chat()).contact

        if answer.blacklist_chats is True:  # Всем кроме
            if answer.contacts == contact or message.chat_id in answer.chats:
                return False  # Чат попадает под исключения
        else:  # answer.blacklist_chats is False:  # Только
            if answer.contacts != contact and message.chat_id not in answer.chats:
                return False  # Чат не попадает под исключения

        if answer.triggering.get(message.chat_id) and time_now() - answer.triggering[message.chat_id] < timedelta(hours=1):
            return False  # Автоответ для этого чата недавно срабатывал

        await update_auto_answer_triggering(self.id, answer.id, message.chat_id)

        entities = deserialize_tl_entities(answer.entities)
        file = get_path_auto_answer_media(self.id, answer.id, answer.media.access_hash, answer.media.ext) if answer.media else None

        await message.respond(answer.text, formatting_entities=entities, file=file)
        return True

    async def new_message_service(self: 'MaksogramClient', event: NewMessage.Event):
        message: MessageService = event.message

        if event.is_private and not message.out and isinstance(message.action, (MessageActionStarGift, MessageActionStarGiftUnique)):  # Новый подарок
            if isinstance(message.action.gift, StarGiftUnique):  # Уникальный подарок
                stars = ""
                gift_type = "уникальный подарок"
                text = "ℹ️ Этот подарок является уникальным. Его можно свободно передавать между пользователями Telegram или " \
                       "продать на рынке. Пока что подарок будет красоваться в профиле 😎"
            elif message.action.gift.limited:  # Лимитированный подарок
                stars = f"за {message.action.gift.stars} звезд"
                gift_type = "лимитированный подарок"
                text = "ℹ️ Этот подарок можно конвертировать в уникальный, чтобы получить особый узор, цвет и макет. После " \
                       "улучшения можно передавать этот подарок другим пользователям или продать на рынке"
            else:  # Обычный подарок
                stars = f"за {message.action.gift.stars} звезд"
                gift_type = "подарок"
                text = "ℹ️ Этот подарок не входит в коллекцию лимитированных, значит его нельзя улучшить до уникального и " \
                       "<b>через 7 дней продать его за звезды также не получится!</b>"

            user_name = await self.chat_name(event.chat_id, my_name="себя")
            await MaksogramBot.send_message(
                self.id, f"🎉 🥳 <b>Поздравляю с подарком!</b>\nВы получили {gift_type} от {user_name} {stars}\n"
                         f"<blockquote>{text}</blockquote>")

    async def official(self: 'MaksogramClient', event: NewMessage.Event):
        message: Message = event.message

        settings = await get_security_settings(self.id)
        if not settings.security_no_access:
            return

        if settings.email:
            try:
                await send_email_message(settings.email, "Восстановление доступа", message.message)
            except Exception as e:
                await MaksogramBot.send_system_message(format_error(e))
                self.logger.error(f"ошибка {e.__class__.__name__} при отправке сообщения на почту {settings.email} ({e})")

        for agent in settings.agents:
            try:
                await MaksogramBot.send_message(agent.id, f"🌐 <b>Восстановление доступа</b>\n{message.message}")
            except Exception as e:
                await MaksogramBot.send_system_message(format_error(e))
                self.logger.error(f"не удалось отправить сообщение от официального аккаунта из-за ошибки {e.__class__.__name__} ({e})")

        if settings.agents:
            names = ', '.join([agent.name for agent in settings.agents])
            await MaksogramBot.send_message(self.id, "🌐 <b>Восстановление доступа</b>\nСообщение от официального аккаунта Telegram было "
                                                     f"отправлено {names}, потому что они включили восстановление аккаунта")

        await stop_recovery(self.id)

    async def maksogram_bot(self: 'MaksogramClient', event: NewMessage.Event):
        if (module := await self.modules(event.message)) and not self.is_owner:
            await MaksogramBot.send_system_message(
                f"💬 <b>Maksogram в чате</b>\n<b>{self.name}</b> воспользовал(а)ся Maksogram в чате ({module})")

    async def new_authorization(self: 'MaksogramClient', update: UpdateNewAuthorization):
        if not update.unconfirmed:
            return  # Подтвержденный вход не обрабатывается

        if not await self.get_authorization(update.hash):
            return  # Авторизация удалена

        if await enabled_security_hack(self.id):
            markup = IMarkup(rows=[BRow([IButton("🚫 Удалить вход", cb('reset_authorization', update.hash))]),
                                   BRow([IButton("✔️ Подтвердить", cb('confirm_authorization'))])])
            await MaksogramBot.send_message(
                self.id, "💀 <b>Защита аккаунта</b>\nОбнаружен новый вход в аккаунт! Доверять можно можно только приложениям "
                         "из Google Play и официального сайта telegram.org. Остальное потенциально представляет угрозу\n"
                         f"Для консультации можно написать @{support}", reply_markup=markup)

    async def message_edited(self: 'MaksogramClient', event: MessageEdited.Event):
        message: Message = event.message

        saved_message = await self.get_saved_message(message.chat_id, message.id)
        if saved_message is None:
            self.logger.warning(f"измененное сообщение не найдено в базе ({message.chat_id}, {message.id})")
            return  # Сообщение не было сохранено ранее

        if check_edited_message(message, saved_message):
            if not message.out and await self.enabled_notify_changes():  # Включены уведомления об изменении сообщений
                link = self.link_to_saved_message(saved_message.id)
                chat_name = await self.chat_name(message.chat_id)

                markup = IMarkup([BRow([IButton("Выключить такие уведомления", cb('saving_messages', 'new').encode())])])
                await MaksogramBot.send_message(
                    self.id, f"✍️ В чате с {chat_name} изменено <a href='{link}'>сообщение</a>", reply_markup=markup)

            await self.update_saved_message(saved_message.id, message)

            await self.client.send_message(self.my_messages, message, comment_to=saved_message.id)

        else:
            pass  # С обновления 3.0.0 изменения реакций больше не обрабатываются

    async def message_read(self: 'MaksogramClient', event: MessageRead.Event):
        if not event.is_private:
            return  # Чтение не в личных чатах не обрабатывается

        user = await get_user_settings(self.id, event.chat_id)
        if user is None:
            return

        if user.reading:
            await update_status_user(self.id, user.id, 'reading', False)

            name = await self.chat_name(user.id)
            markup = IMarkup(rows=[BRow([IButton(text="Настройки", data=cb('status_user', user.id))])])
            await MaksogramBot.send_message(self.id, f"🌐 {name} прочитал(а) сообщение", reply_markup=markup)

        if user.statistics:
            await update_reading_statistics(self.id, user.id)

    async def channel_read(self: 'MaksogramClient'):
        if not self.is_owner:
            await MaksogramBot.send_system_message(f"👀 <b>{self.name}</b> прочитал(а) пост на канале")

    async def message_deleted(self: 'MaksogramClient', event: MessageDeleted.Event):
        # Когда сообщение удаляется в личном чате, is_private=None и chat_id=None, иначе is_private=True и chat_id известен
        is_private = event.is_private is None
        chat_id = event.chat_id
        deleted_ids = event.deleted_ids
        if not deleted_ids:
            return

        chat_id, saved_message_id = await self.get_saved_deleted_message(is_private, chat_id, max(deleted_ids))

        await self.delete_saved_messages(deleted_ids)  # Удаляем сохраненные сообщения из базы данных

        if not saved_message_id:
            return  # Удаленное сообщение ранее не было сохранено

        await self.notify_deleted_messages(is_private, chat_id, saved_message_id, len(deleted_ids))  # Уведомляем клиента

    async def notify_deleted_messages(self: 'MaksogramClient', is_private: bool, chat_id: int, saved_message_id: int, len_messages: int):
        """
        Уведомляет клиента об удалении сообщения(-ий) и отправляет информацию в комментарии под сохраненным сообщением

        :param is_private: `True`, если сообщение(я) удалено в личном чате, иначе `False`
        :param chat_id: ат с удаленным сообщением
        :param saved_message_id: идентификатор сохраненного сообщения в системном канале
        :param len_messages: количество удаленных сообщений
        """

        if len_messages == 1:
            await self.client.send_message(self.my_messages, "Сообщение удалено", comment_to=saved_message_id)
        else:
            await self.client.send_message(self.my_messages, f"Сообщение (и еще {len_messages - 1}) удалены", comment_to=saved_message_id)

        if chat_id == self.id:  # Избранное
            return  # Любые изменения в Избранном не уведомляются

        link = self.link_to_saved_message(saved_message_id)
        chat_name = await self.chat_name(chat_id)
        place = f"В чате с {chat_name}" if is_private else f"Кто-то из {chat_name}"

        if len_messages == 1:
            await MaksogramBot.send_message(self.id, f"{place} удалено <a href='{link}'>сообщение</a>")
        else:
            await MaksogramBot.send_message(self.id, f"{place} удалено {len_messages} сообщений, <a href='{link}'>например</a>")
