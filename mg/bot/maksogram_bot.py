from mg.config import OWNER, SITE, VERSION, VERSION_ID

from typing import Any

from aiogram import F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, FSInputFile
from . types import dp, bot, Blocked, CallbackData, support_link, feedback
from . functions import (
    new_message,
    payment_menu,
    referral_link,
    preview_options,
    get_subscription,
    get_blocked_users,
    subscription_menu,
    new_callback_query,
)

from aiogram.types import ReplyKeyboardRemove as KRemove
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton

from mg.core.types import MaksogramBot
from mg.core.functions import error_notify, resources_path, get_account_status, renew_subscription


# Инициализация обработчиков сообщений и нажатий кнопок
from mg.admin.bot import admin_initial
admin_initial()
from mg.menu.bot import menu_initial
menu_initial()
from . login import login_initial
login_initial()
from mg.changed_profile.bot import changed_profile_initial
changed_profile_initial()
from mg.speed_answers.bot import speed_answers_initial
speed_answers_initial()
from mg.security.bot import security_initial
security_initial()
from mg.ghost_mode.bot import ghost_mode_initial
ghost_mode_initial()
from mg.status_users.bot import status_users_initial
status_users_initial()
from mg.modules.bot import modules_initial
modules_initial()
from mg.answering_machine.bot import answering_machine_initial
answering_machine_initial()
from mg.bot.inline_mode import inline_mode_initial
inline_mode_initial()


cb = CallbackData()


@dp.message(Command('version'))
@error_notify()
async def _version(message: Message):
    if await new_message(message): return
    await message.answer(f"Версия: {VERSION}\n<a href='{SITE}/{VERSION_ID}'>Обновление 👇</a>",
                         link_preview_options=preview_options(VERSION_ID))


@dp.callback_query(F.data.startswith(cb.command('friends')))
@error_notify()
async def _friends_button(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**friends())


def friends() -> dict[str, Any]:
    markup = IMarkup(inline_keyboard=[[IButton(text="Поделиться ссылкой", callback_data=cb('friends_link'))]])
    return dict(text="🎁 <b>Реферальная программа</b>\nПриглашайте своих знакомых и "
                     "получайте в подарок <b>месяц подписки</b> за каждого друга", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('friends_link')))
@error_notify()
async def _friends_link(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.answer_photo(**friends_link(callback_query.from_user.id))
    await callback_query.message.delete()


def friends_link(account_id: int) -> dict[str, Any]:
    start_url = f"tg://resolve?domain={MaksogramBot.username}&start={referral_link(account_id)}"
    markup = IMarkup(inline_keyboard=[[IButton(text="Попробовать бесплатно", url=start_url)]])
    return dict(
        photo=FSInputFile(resources_path("logo.jpg")), disable_web_page_preview=True, reply_markup=markup,
        caption=f"Привет! Я хочу тебе посоветовать отличного <a href='{start_url}'>бота</a>\n"
                "• Можно <b>смотреть удаленные</b> и измененные сообщения\n"
                "• Всегда узнавать о новой аватарке, подарке и описании друга\n"
                "• Сможешь расшифровывать ГС и кружки без Telegram Premium\n"
                "• Включать автоответчик, когда очень занят или спишь\n"
                "• Быстро узнаешь, когда друг в сети, проснулся или прочитал сообщение\n"
                f"Также в нем есть множество других <b><a href='{SITE}'>полезных функций</a></b>")


@dp.message(Command('feedback'))
@error_notify()
async def _feedback(message: Message):
    if await new_message(message): return
    account_id = message.chat.id

    if not await get_account_status(account_id):
        button_text = "Посмотреть отзывы"
        message_text = "Хотите узнать, что думаю о Maksogram его пользователи?"
    else:
        button_text = "Написать отзыв"
        message_text = \
            "❗️ Внимание! ❗️\nВаш отзыв не должен содержать нецензурных высказываний и оскорблений. Приветствуются фото и видео\n" \
            "Вы можете предложить новую функцию или выразить свое мнение по поводу работы Maksogram. За честный отзыв вы получите " \
            f"в подарок неделю подписки\n\nВозникшие проблемы просим сразу перенаправлять {support_link}"

    markup = IMarkup(inline_keyboard=[[IButton(text=button_text, url=feedback)]])
    await message.answer(message_text, reply_markup=markup, disable_web_page_preview=True)


@dp.message(Command('help'))
@error_notify()
async def _help(message: Message):
    if await new_message(message): return
    rules = ("<blockquote expandable><b>Пользовательское соглашение</b>\n"
             "1. <b>Определения</b>\n"
             "1.1. «<b>Системные чаты</b>» — личные чаты, каналы, супергруппы, гигагруппы, базовые группы "
             "(<a href='https://core.telegram.org/api/channel'>термины Telegram API</a>) и другие объекты, автоматически созданные сервисом "
             "Maksogram для обеспечения функциональности, включая, но не ограничиваясь, канал «Мои сообщения», супергруппу «Изменение сообщения» и "
             "личный чат с ботом Maksogram.\n"
             
             "1.2. «<b>Системная папка</b>» — папка (<a href='https://core.telegram.org/api/folders'>термин Telegram API</a>), "
             "содержащая <i>Системные чаты</i>, созданные сервисом Maksogram.\n"
             
             "1.3. «<b>Пользователь</b>» — физическое лицо, использующее функционал сервиса Maksogram.\n\n"
             
             "2. <b>Запреты пользователю</b>\n"
             
             "2.1. <i>Пользователю</i> <b>запрещается</b> удалять <i>Системные чаты</i> или изменять их настройки, а также иным образом их модифицировать\n"
             
             "2.2. <i>Пользователю</i> <b>запрещается</b> удалять <i>Системную папку</i> или изменять ее настройки и содержимое, а также иным образом "
             "модифицировать\n"
             
             "2.3. <i>Пользователю</i> <b>запрещается</b> изменять, удалять или иным образом модифицировать сообщения, находящиеся в <i>Системных чатах</i>.\n\n"
             
             "3. <b>Ответственность пользователя</b>\n"
             
             "3.1. Любые действия, направленные на обход или нарушение запретов, указанных в разделах 2 и 3, рассматриваются как <b>нарушение</b> "
             "условий пользовательского соглашения.\n"
             
             "3.2. Любое нарушение настоящего соглашения может привести к сбою сервиса Maksogram в том числе для других <i>Пользователей</i>. "
             "В таком случае <i>Пользователь</i> <b>признается виновным</b> и обязан возместить ущерб, нанесенный сервису Maksogram.\n"
             
             "3.3. Любое нарушение настоящего соглашения <b>приостанавливает ответственность</b> сервиса Maksogram за сохранность данных "
             "<i>Пользователя</i>, включая сохраненные сообщения, а также за работоспособность и безопасность аккаунта Telegram <i>Пользователя</i>\n\n"
             
             "4. <b>Обязанности сервиса Maksogram</b>\n"
             
             "4.1. Сервис Maksogram обязуется принимать все разумные технические и организационные меры для <b>защиты персональных данных</b> "
             "<i>Пользователя</i>, предоставленных при использовании сервиса Maksogram. Данные <i>Пользователя</i> обрабатываются исключительно "
             "для предоставления услуг сервиса Maksogram\n"
             
             "4.2. Сервис Maksogram обязуется обеспечивать <b>безопасность взаимодействия</b> с аккаунтом Telegram <i>Пользователя</i> в рамках "
             "предоставляемых функций. Однако сервис <b>не несет ответственности</b> за безопасность аккаунта Telegram в случае, если пользователь "
             "предоставил доступ третьим лицам или нарушил правила использования сервиса Maksogram, а также в случае технических сбоев, "
             "действий третьих лиц и ограничений Telegram API или иных обстоятельств вне контроля сервиса Maksogram\n"
             
             "4.3. Сервис Maksogram обязуется предоставлять техническую поддержку <i>Пользователям</i> по вопросам, связанным с использованием "
             f"сервиса Maksogram и личным аккаунтом Telegram в разумные сроки через обращение к {support_link}\n\n"
             
             "5. Цель правил\n"
             
             "5.1. Настоящие правила введены для обеспечения корректной работы сервиса Maksogram, сохранности пользовательских данных и "
             "целостности функционала.</blockquote>")

    await message.answer("Добро пожаловать в Maksogram! Чтобы начать, откройте /menu и нажмите на кнопку включения, далее следуйте инструкции. "
                         f"По любым вопросам обращайтесь к {support_link}\n\n{rules}", disable_web_page_preview=True)


@dp.callback_query(F.data.startswith(cb.command('subscription')))
@error_notify()
async def _subscription(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    subscription_id = cb.deserialize(callback_query.data)[0]
    await callback_query.message.edit_caption(**await subscription_menu(callback_query.from_user.id, subscription_id))


@dp.callback_query(F.data.startswith(cb.command('payment')))  # Кнопка назад в меню варианта подписки
@error_notify()
async def _payment(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    (message := await payment_menu()).pop('photo')
    await callback_query.message.edit_caption(**message)


@dp.callback_query(F.data.startswith(cb.command('send_payment')))
@error_notify()
async def _send_payment(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    subscription_id = cb.deserialize(callback_query.data)[0]

    subscription = await get_subscription(subscription_id)

    # Какому клиенту продлить подписку, какая подписка куплена, сообщение с меню подписки
    markup = IMarkup(inline_keyboard=[[
        IButton(text="Подтвердить! ✅", callback_data=cb('confirm_payment', account_id, subscription_id, callback_query.message.message_id))]])

    await bot.send_message(OWNER, f"Пользователь {account_id} отправил оплату, проверь это! Если так, то подтверди, "
                                  f"чтобы я продлил подписку на {subscription.about.lower()}", reply_markup=markup)
    await callback_query.answer("Оплата проверяется. Ожидайте!", True)


@dp.callback_query(F.data.startswith(cb.command('confirm_payment')))
@error_notify()
async def _confirm_sending_payment(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id, subscription_id, message_id = cb.deserialize(callback_query.data)
    subscription = await get_subscription(subscription_id)
    await renew_subscription(account_id, subscription.duration)

    await bot.edit_message_reply_markup(chat_id=account_id, message_id=message_id)
    await bot.send_message(account_id, f"Ваша оплата подтверждена! Подписка Maksogram продлена на {subscription.about.lower()}", reply_to_message_id=message_id)
    await callback_query.message.edit_text(callback_query.message.text + '\n\nУспешно!')


@dp.message()
@error_notify()
async def _other_messages(message: Message):
    if await new_message(message, params={"Обработка": "Не распознано"}): return
    # await message.answer("Привет! Откройте /menu", reply_markup=KRemove())


@dp.callback_query()
@error_notify()
async def _other_callback_queries(callback_query: CallbackQuery):
    if await new_callback_query(callback_query, params={"Обработка": "Не распознано"}): return
    await callback_query.answer("Не распознано!")


async def start_bot():
    Blocked.users = await get_blocked_users()

    await bot.send_message(OWNER, f"<b>Бот запущен!🚀</b>")
    print("Бот запущен")

    await dp.start_polling(bot)
