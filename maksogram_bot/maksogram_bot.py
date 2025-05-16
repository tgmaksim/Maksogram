from typing import Any
from core import (
    db,
    html,
    SITE,
    OWNER,
    security,
    Variables,
    support_link,
    MaksogramBot,
    resources_path,
    feedback_button,
    preview_options,
)

from aiogram import F
from aiogram.filters.command import Command
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from aiogram.types import ReplyKeyboardRemove as KRemove
from aiogram.types import Message, CallbackQuery, FSInputFile
from . core import (
    dp,
    bot,
    Data,
    new_message,
    payment_menu,
    referal_link,
    subscription_menu,
    new_callback_query,
)

# Инициализация обработчиков событий aiogram
from . inline_mode import inline_mode_initial
inline_mode_initial()
from . admin import admin_initial
admin_initial()
from . menu import menu_initial
menu_initial()
from . modules import modules_initial
modules_initial()
from . status_users import status_users_initial
status_users_initial()
from . answering_machine import answering_machine_initial
answering_machine_initial()
from . login import login_initial
login_initial()
from . security import security_initial
security_initial()
from . ghost_mode import ghost_mode_initial
ghost_mode_initial()
from . changed_profile import changed_profile_initial
changed_profile_initial()


@dp.message(Command('version'))
@security()
async def _version(message: Message):
    if await new_message(message): return
    await message.answer(f"Версия: {Variables.version_string}\n<a href='{SITE}/{Variables.version}'>Обновление</a> 👇",
                         parse_mode=html, link_preview_options=preview_options(Variables.version))


@dp.message(Command('friends'))
@security()
async def _friends(message: Message):
    if await new_message(message): return
    await message.answer(**friends())


@dp.callback_query(F.data == "friends")
@security()
async def _friends_button(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.answer(**friends())
    await callback_query.message.delete()


def friends() -> dict[str, Any]:
    markup = IMarkup(inline_keyboard=[[IButton(text="Поделиться ссылкой", callback_data="friends_link")]])
    return dict(text="🎁 <b>Реферальная программа</b>\nПриглашайте своих знакомых и "
                     "получайте в подарок <b>месяц подписки</b> за каждого друга", parse_mode=html, reply_markup=markup)


@dp.callback_query(F.data == "friends_link")
@security()
async def _friends_link(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.answer_photo(**friends_link(callback_query.from_user.id))
    await callback_query.message.delete()


def friends_link(account_id: int) -> dict[str, Any]:
    url = f"tg://resolve?domain={MaksogramBot.username}&start={referal_link(account_id)}"
    markup = IMarkup(inline_keyboard=[[IButton(text="Попробовать бесплатно", url=url)]])
    return dict(
        photo=FSInputFile(resources_path("logo.jpg")), disable_web_page_preview=True,
        caption=f"Привет! Я хочу тебе посоветовать отличного <a href='{url}'>бота</a>\n"
                "• Можно <b>смотреть удаленные</b> и измененные сообщения\n"
                "• Всегда узнавать о новой аватарке, подарке и описании друга\n"
                "• Сможешь расшифровывать ГС и кружки без Telegram Premium\n"
                "• Включать автоответчик, когда очень занят или спишь\n"
                "• Быстро узнаешь, когда друг в сети, проснулся или прочитал сообщение\n"
                f"Также в нем есть множество других <b><a href='{SITE}'>полезных функций</a></b>", parse_mode=html, reply_markup=markup)


@dp.message(Command('feedback'))
@security()
async def _feedback(message: Message):
    if await new_message(message): return
    if not await db.fetch_one(f"SELECT true FROM accounts WHERE account_id={message.chat.id}", one_data=True):
        button_text = "Посмотреть отзывы"
        message_text = "Хотите узнать, что думаю о Maksogram его пользователи?"
    else:
        button_text = "Написать отзыв"
        message_text = \
            "❗️ Внимание! ❗️\nВаш отзыв не должен содержать нецензурных высказываний и оскорблений. Приветствуются фото и видео\n"\
            "Вы можете предложить новую функцию или выразить свое мнение по поводу работы Maksogram. За честный отзыв вы получите "\
            f"в подарок неделю подписки\n\nВозникшие проблемы просим сразу перенаправлять {support_link}"
    markup = IMarkup(inline_keyboard=[[IButton(text=button_text, url=feedback_button)]])
    await message.answer(message_text, reply_markup=markup, parse_mode=html, disable_web_page_preview=True)


@dp.message(Command('inline_mode'))
@security()
async def _inline_mode(message: Message):
    if await new_message(message): return
    markup = IMarkup(inline_keyboard=[[IButton(text="Открыть", switch_inline_query_current_chat="")]])
    await message.answer("<b>Встроенный режим</b>", parse_mode=html, reply_markup=markup)


@dp.message(Command('help'))
@security()
async def _help(message: Message):
    if await new_message(message): return
    await help(message)


@dp.callback_query(F.data == "help")
@security()
async def _help_button(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_reply_markup()
    await help(callback_query.message)


async def help(message: Message):
    await message.answer("/menu - меню функций\n"
                         "/settings - настройки\n"
                         "/feedback - отзывы о Maksogram\n"
                         "/friends - реферальная программа\n"
                         "/version - обзор прошлого обновления", parse_mode=html, reply_markup=KRemove())


@dp.callback_query(F.data.startswith("subscription"))
@security()
async def _subscription(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    subscription_id = int(callback_query.data.replace("subscription", ""))
    await callback_query.message.edit_caption(**await subscription_menu(account_id, subscription_id))


@dp.callback_query(F.data == "payment")
@security()
async def _payment(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    (message := await payment_menu()).pop("photo")
    await callback_query.message.edit_caption(**message)


@dp.callback_query(F.data.startswith("send_payment"))
@security()
async def _send_payment(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    subscription_id = int(callback_query.data.replace("send_payment", ""))
    name = await db.fetch_one(f"SELECT name FROM accounts WHERE account_id={account_id}", one_data=True)  # Имя пользователя
    subscription = await db.fetch_one(f"SELECT about FROM subscriptions WHERE subscription_id={subscription_id}")
    markup = IMarkup(inline_keyboard=[[
        IButton(text="Подтвердить! ✅", callback_data=f"confirm_sending_payment{account_id}_{subscription_id}_{callback_query.message.message_id}")]])
    await bot.send_message(OWNER, f"Пользователь {name} отправил оплату, проверь это! Если так, то подтверди, "
                                  f"чтобы я продлил подписку на {subscription['about'].lower()}", reply_markup=markup)
    await callback_query.answer("Запрос отправлен. Ожидайте!", True)


@dp.callback_query(F.data.startswith("confirm_sending_payment"))
@security()
async def _confirm_sending_payment(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    if callback_query.from_user.id != OWNER:
        return await callback_query.answer("Ошибка!", True)
    account_id, subscription_id, message_id = map(int, callback_query.data.replace("confirm_sending_payment", "").split("_"))
    subscription = await db.fetch_one(f"SELECT duration, about FROM subscriptions WHERE subscription_id={subscription_id}")
    await db.execute(f"""UPDATE payment SET next_payment=((CASE WHEN 
                     next_payment > CURRENT_TIMESTAMP THEN 
                     next_payment ELSE CURRENT_TIMESTAMP END) + INTERVAL '{subscription['duration']} days'), 
                     is_paid=true WHERE account_id={account_id}""")  # перемещение даты оплаты на несколько дней вперед
    await bot.edit_message_reply_markup(chat_id=account_id, message_id=message_id)
    await bot.send_message(account_id, f"Ваша оплата подтверждена! Следующий платеж через {subscription['about'].lower()}",
                           reply_to_message_id=message_id)
    await callback_query.message.edit_text(callback_query.message.text + '\n\nУспешно!')


@dp.callback_query()
@security()
async def _other_callback_query(callback_query: CallbackQuery):
    await new_callback_query(callback_query, params={"Обработано": "не обработано"})
    await callback_query.answer("Не распознано!")


@dp.message()
@security()
async def _other_message(message: Message):
    if await new_message(message, params={"Обработка": "не обработано"}): return
    if message.text == "Отмена":
        return await message.answer("Привет! /menu", reply_markup=KRemove())


async def start_bot():
    Data.banned = await db.fetch_all("SELECT account_id FROM banned", one_data=True)

    await bot.send_message(OWNER, f"<b>Бот запущен!🚀</b>", parse_mode=html)
    print("Запуск бота")
    await dp.start_polling(bot)
