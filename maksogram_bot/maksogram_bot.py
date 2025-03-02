from datetime import timedelta, datetime
from core import (
    db,
    html,
    OWNER,
    channel,
    support,
    time_now,
    security,
)

from aiogram import F
from aiogram.filters.command import Command
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from . core import (
    dp,
    bot,
    Data,
    new_message,
    payment_menu,
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
from . avatars import avatars_initial
avatars_initial()
from . answering_machine import answering_machine_initial
answering_machine_initial()
from . login import login_initial
login_initial()


@dp.message(Command('feedback'))
@security()
async def _start_feedback(message: Message):
    if await new_message(message): return
    registration_date: datetime = await db.fetch_one(f"SELECT registration_date FROM accounts WHERE account_id={message.chat.id}", one_data=True)
    if not await db.fetch_one(f"SELECT true FROM accounts WHERE account_id={message.chat.id}", one_data=True):
        return await message.answer("Вы не подключили бота и не можете оставить отзыв")
    elif (time_now() - registration_date).total_seconds() < 3*24*60*60:  # С даты регистрации прошло менее 3 дней
        return await message.answer("Вы зарегистрировались менее 3 дней назад. Попробуйте все функции, "
                                    "чтобы написать полноценный объективный отзыв")
    markup = IMarkup(inline_keyboard=[[IButton(text="Написать отзыв", url=f"tg://resolve?domain={channel}&post=375&comment=512")]])
    await message.answer(
        "❗️ Внимание! ❗️\nВаш отзыв не должен содержать нецензурных высказываний и оскорблений. Приветствуются фото- и видеоматериалы\n"
        "Вы можете предложить новую функцию или выразить свое мнение по поводу работы Maksogram. За честный отзыв вы получите "
        f"в подарок неделю подписки\n\nВозникшие проблемы просим сразу перенаправлять <a href='t.me/{support}'>тех. поддержке</a>",
        reply_markup=markup, parse_mode=html, disable_web_page_preview=True)


@dp.callback_query(F.data == "send_payment")
@security()
async def _send_payment(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    name = await db.fetch_one(f"SELECT name FROM accounts WHERE account_id={account_id}", one_data=True)  # Имя пользователя
    markup = IMarkup(inline_keyboard=[[
        IButton(text="Подтвердить! ✅", callback_data=f"confirm_sending_payment{account_id}_{callback_query.message.message_id}")]])
    await bot.send_message(OWNER, f"Пользователь {name} отправил оплату, проверь это! Если так, то подтверди, "
                                  "чтобы я продлил подписку на месяц", reply_markup=markup)
    await callback_query.answer("Запрос отправлен. Ожидайте!", True)


@dp.callback_query(F.data.startswith("confirm_sending_payment"))
@security()
async def _confirm_sending_payment(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    if callback_query.from_user.id != OWNER:
        return await callback_query.answer("Ошибка!", True)
    account_id, message_id = map(int, callback_query.data.replace("confirm_sending_payment", "").split("_"))
    await db.execute(f"""UPDATE payment SET next_payment=((CASE WHEN 
                     next_payment > CURRENT_TIMESTAMP THEN 
                     next_payment ELSE CURRENT_TIMESTAMP END) + INTERVAL '30 days'), 
                     is_paid=true WHERE account_id={account_id}""")  # перемещение даты оплаты на 30 дней вперед
    await bot.edit_message_reply_markup(chat_id=account_id, message_id=message_id)
    await bot.send_message(account_id, f"Ваша оплата подтверждена! Следующий платеж через месяц", reply_to_message_id=message_id)
    await callback_query.message.edit_text(callback_query.message.text + '\n\nУспешно!')


@dp.callback_query()
@security()
async def _other_callback_query(callback_query: CallbackQuery):
    await new_callback_query(callback_query)


@dp.message()
@security()
async def _other_message(message: Message):
    if await new_message(message): return


async def check_payment_datetime():
    for account_id in await db.fetch_all("SELECT account_id FROM accounts", one_data=True):
        account_id: int
        payment = await db.fetch_one(f"SELECT \"user\", next_payment FROM payment WHERE account_id={account_id}")
        if payment['user'] != 'user': continue
        if time_now() <= payment['next_payment'] <= (time_now() + timedelta(days=1)):  # За день до конца
            first_notification = await db.fetch_one(f"SELECT first_notification FROM payment WHERE account_id={account_id}", one_data=True)
            if (time_now() - first_notification).total_seconds() < 23*60*60 + 50*60:  # Прошлое уведомление было менее 23 часов 50 минут назад
                return
            await db.execute(f"UPDATE payment SET first_notification=now() WHERE account_id={account_id}")
            await bot.send_message(account_id, "Текущая подписка заканчивается! Произведите следующий "
                                               "платеж до конца завтрашнего дня")
            await bot.send_message(account_id, **await payment_menu(account_id))


async def start_bot():
    await check_payment_datetime()

    Data.banned = await db.fetch_all("SELECT account_id FROM banned", one_data=True)

    await bot.send_message(OWNER, f"<b>Бот запущен!🚀</b>", parse_mode=html)
    print("Запуск бота")
    await dp.start_polling(bot)
