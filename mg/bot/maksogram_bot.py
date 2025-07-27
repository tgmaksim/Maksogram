from mg.config import testing, OWNER, SITE, VERSION, VERSION_ID

from typing import Any

from aiogram import F
from aiogram.filters import Command
from . types import dp, bot, Blocked, CallbackData, support_link, feedback
from aiogram.types import Message, CallbackQuery, FSInputFile, WebAppInfo, BotCommand, BotCommandScopeChat
from . functions import (
    new_message,
    referral_link,
    preview_options,
    get_subscription,
    get_blocked_users,
    get_subscriptions,
    new_callback_query,
)

# from aiogram.types import ReplyKeyboardRemove as KRemove
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton

from mg.core.types import MaksogramBot
from mg.core.yoomoney import create_payment, check_payment, delete_payment
from mg.core.functions import error_notify, resources_path, get_account_status, get_payment_data, renew_subscription


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
from mg.fire.bot import fire_initial
fire_initial()

from mg.bot.inline_mode import inline_mode_initial
inline_mode_initial()


cb = CallbackData()


@dp.message(Command('version'))
@error_notify()
async def _version(message: Message):
    if await new_message(message): return
    await message.answer(f"Версия: {VERSION}\n<a href='{SITE}/{VERSION_ID}'>Обновление 👇</a>",
                         link_preview_options=preview_options(VERSION_ID))


@dp.message(Command('friends'))
@error_notify()
async def _friends(message: Message):
    if await new_message(message): return
    await message.answer(**friends())


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
    markup = IMarkup(inline_keyboard=[[IButton(text="🚀 Запустить бота", url=start_url)]])
    return dict(
        photo=FSInputFile(resources_path("logo.jpg")), disable_web_page_preview=True, reply_markup=markup,
        caption=f"Лучший <b><a href='{start_url}'>бот</a></b> в Telegram, чтобы...\n\n"
                "• Видеть <b>удаленные</b> сообщения\n"
                "• Создать огонек🔥 в чате с другом\n"
                "• Следить за статусом и профилем друга (аватарки, описание, подарки)\n"
                "• Анонимно смотреть истории\n"
                "• Защитить аккаунт от взлома\n"
                "• Включать автоответчик на ночь или когда не можешь ответить\n\n"
                f"А также другие <b><a href='{SITE}'>полезные функции</a></b>")


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


@dp.callback_query(F.data.startswith(cb.command('premium')))
@error_notify()
async def _premium(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    params = cb.deserialize(callback_query.data)
    prev = params.get(0) is True
    if prev:
        await callback_query.answer("Запустите Maksogram кнопкой в меню", True)
        return

    edit = params.get(0) == 'edit'
    if edit:
        (message := await premium_menu(account_id)).pop('photo')
        await callback_query.message.edit_caption(**message)
    else:
        await callback_query.message.answer_photo(**await premium_menu(account_id))
        await callback_query.message.delete()


async def premium_menu(account_id: int) -> dict[str, Any]:
    payment = await get_payment_data(account_id)
    markup = IMarkup(inline_keyboard=[[IButton(text="◀️  Назад", callback_data=cb('menu', 'new'))]])

    if payment.subscription == 'admin':
        payment_info = "Maksogram Premium навсегда 😎\nСтоимость: бесплатно"
    elif payment.subscription == 'premium':
        payment_info = f"Maksogram Premium до {payment.str_ending}\nСтоимость: {payment.fee} рублей"
    else:
        payment_info = "Подписка дает расширенные лимиты во всех функциях, сохранение любого количества сообщений и высокую скорость работы Maksogram"
        markup = IMarkup(inline_keyboard=[[IButton(text="🌟 Maksogram Premium", callback_data=cb('payment'))],
                                          [IButton(text="◀️  Назад", callback_data=cb('menu', 'new'))]])

    return dict(caption=f"🌟 <b>Maksogram Premium</b>\n{payment_info}", reply_markup=markup, photo=FSInputFile(resources_path("premium.jpg")))


@dp.callback_query(F.data.startswith(cb.command('payment')))  # Кнопка назад в меню варианта подписки
@error_notify()
async def _payment(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    (message := await payment_menu()).pop('photo')
    await callback_query.message.edit_caption(**message)


async def payment_menu() -> dict[str, Any]:
    subscriptions = await get_subscriptions()

    i, buttons = 0, []
    while i < len(subscriptions):
        if i + 1 < len(subscriptions):
            buttons.append([IButton(text=subscriptions[i].about, callback_data=cb('subscription', subscriptions[i].id)),
                            IButton(text=subscriptions[i+1].about, callback_data=cb('subscription', subscriptions[i+1].id))])
            i += 1
        else:
            buttons.append([IButton(text=subscriptions[i].about, callback_data=cb('subscription', subscriptions[i].id))])
        i += 1
    buttons.append([IButton(text="◀️  Назад", callback_data=cb('premium', 'edit'))])

    return dict(caption="Подписка Maksogram Premium с полным набором всех функций", reply_markup=IMarkup(inline_keyboard=buttons),
                photo=FSInputFile(resources_path("premium.jpg")))


@dp.callback_query(F.data.startswith(cb.command('subscription')))
@error_notify()
async def _subscription(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    subscription_id = cb.deserialize(callback_query.data)[0]
    await callback_query.message.edit_caption(**await subscription_menu(callback_query.from_user.id, subscription_id))


async def subscription_menu(account_id: int, subscription_id: int) -> dict[str, Any]:
    subscription = await get_subscription(subscription_id)
    fee = (await get_payment_data(account_id)).fee  # Цена базовой подписки в месяц в рублях для клиента

    without_discount = int(fee * (subscription.duration / 30))
    amount = int(without_discount * (1 - subscription.discount / 100))  # Цена со скидкой
    discount = f"-{subscription.discount}%"
    discount_about = f" (вместо {without_discount} руб)" if subscription.discount else " (без скидки)"  # Информация о скидке

    link = await create_payment(account_id, amount, subscription.about, subscription_id)

    markup = IMarkup(inline_keyboard=[[IButton(text=f"💳 Оплатить {amount} руб", web_app=WebAppInfo(url=link))],
                                      [IButton(text="✅ Проверить оплату", callback_data=cb('check_payment', subscription_id))],
                                      [IButton(text="◀️  Назад", callback_data=cb('payment'))]])

    return dict(caption=f"🌟 <b>MG Premium на {subscription.about.lower()} {discount}</b>\n\n"
                        f"Цена: {amount} руб{discount_about}", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('check_payment')))
@error_notify()
async def _check_payment(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    subscription_id = cb.deserialize(callback_query.data)[0]
    subscription = await get_subscription(subscription_id)

    if (status := await check_payment(account_id)) == 'succeeded':
        await delete_payment(account_id)
        await renew_subscription(account_id, subscription.duration)

        await callback_query.message.edit_caption(
            caption=f"🌟 <b>Maksogram Premium</b>\nСпасибо за проведенную оплату: Maksogram Premium продлен на {subscription.about.lower()}",
            reply_markup=IMarkup(inline_keyboard=[[IButton(text="◀️  Назад", callback_data=cb('premium', 'edit'))]]))
        await bot.send_message(OWNER, f"Пользовать отправил оплату. Подписка продлена на {subscription.about.lower()}")

    elif status == 'canceled':
        await delete_payment(account_id)

        await callback_query.message.edit_caption(
            caption="🌟 <b>Maksogram Premium</b>\nТранзакция была прервана или ее время истекло",
            reply_markup=IMarkup(inline_keyboard=[[IButton(text="◀️  Назад", callback_data=cb('premium', 'edit'))]]))
        await bot.send_message(OWNER, f"Пользователь {account_id} попытался подтвердить платеж, но его статус {status}")

    elif status == 'pending':
        await callback_query.answer("Завершите оплату, чтобы получить Maksogram Premium", True)
        await bot.send_message(OWNER, "Платеж находится в состоянии ожидания оплаты от пользователя")

    else:
        await callback_query.answer("Транзакция проверяется...", True)
        await bot.send_message(OWNER, f"Неизвестный статус оплаты: {status}")


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


async def initialization_bot_profile():
    admin_commands = [
        # Главные команды
        BotCommand(command='menu', description="меню функций"),
        BotCommand(command='settings', description="настройки"),

        # Отдельные команды админа
        BotCommand(command='admin', description="панель админа"),
        BotCommand(command='reload', description="перезапуск"),
        BotCommand(command='stop', description="остановка"),
        BotCommand(command='critical_stop', description="экстренная остановка"),
        BotCommand(command='mailing', description="рассылка сообщений"),
        BotCommand(command='login', description="ввод кода аутентификации"),

        # Остальные команды
        BotCommand(command='help', description="помощь"),
        BotCommand(command='feedback', description="отзывы и предложения"),
        BotCommand(command='friends', description="реферальная программа"),
        BotCommand(command='inline_mode', description="inline-режим"),
        BotCommand(command='version', description="обзор обновления"),
        BotCommand(command='start', description="приветствие")
    ]

    if await bot.get_my_commands(scope=BotCommandScopeChat(chat_id=OWNER)) != admin_commands:
        await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=OWNER))


async def start_bot():
    Blocked.users = await get_blocked_users()

    await initialization_bot_profile()

    await bot.send_message(OWNER, f"<b>Бот запущен!🚀</b>")
    print("Бот запущен")

    if testing:
        await bot.send_message(OWNER, "Режим тестирования")
        print("Режим тестирования")

    await dp.start_polling(bot)
