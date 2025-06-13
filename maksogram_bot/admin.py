import os
import aiohttp
import asyncio

from sys_keys import release
from core import (
    db,
    html,
    OWNER,
    security,
    time_now,
    Variables,
    human_time,
    unzip_int_data,
)

from aiogram import F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton as KButton
from aiogram.types import ReplyKeyboardRemove as KRemove
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from aiogram.types import Message, CallbackQuery, WebAppInfo
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from . core import (
    dp,
    bot,
    Data,
    UserState,
    new_message,
    payment_menu,
    developer_command,
    new_callback_query,
)


# Метод для отправки сообщения от имени бота
@dp.message(F.reply_to_message.__and__(F.chat.id == OWNER).__and__(F.reply_to_message.text.startswith("ID")))
@security()
async def _sender(message: Message):
    user_id = int(message.reply_to_message.text.split('\n', 1)[0].replace("ID: ", ""))
    if message.text.lower() == "бан":
        await db.execute(f"INSERT INTO banned VALUES ({user_id}, now())")
        Data.banned.append(user_id)
        return await message.answer("Пользователь заблокирован!")
    try:
        copy_message = await bot.copy_message(user_id, OWNER, message.message_id)
    except TelegramForbiddenError:
        await message.answer("Пользователь заблокировал бота...")
    except Exception as e:
        await message.answer(f"Сообщение не отправлено из-за ошибки {e.__class__.__name__}: {e}")
    else:
        await message.answer("Сообщение отправлено")
        await bot.forward_message(OWNER, user_id, copy_message.message_id)


@dp.message(Command('admin'))
@security()
async def _admin(message: Message):
    if await developer_command(message): return
    markup = IMarkup(inline_keyboard=[[IButton(text="📊 Статистика", callback_data="admin_statistics")]])
    await message.answer("Команды разработчика:\n"
                         "/reload - перезапустить программу\n"
                         "/stop - остановить программу\n"
                         "/critical_stop - экстренная остановка\n"
                         "/mailing - рассылка\n"
                         "/login - Web App ввода кода\n"
                         "/payment - меню оплаты подписки", reply_markup=markup)


@dp.callback_query(F.data == "admin_statistics")
@security()
async def _admin_statistics(callback_query: CallbackQuery):
    count_all = await db.fetch_one("SELECT COUNT(*) FROM users", one_data=True)
    count_accounts = await db.fetch_one("SELECT COUNT(*) FROM accounts", one_data=True)
    count_active = await db.fetch_one("SELECT COUNT(*) FROM settings WHERE is_started=true", one_data=True)
    work_time = time_now() - await db.fetch_one(f"SELECT registration_date FROM accounts WHERE account_id={OWNER}", one_data=True)
    info = f"📊 <b>Статистика Maksogram</b>\n" \
           f"Запустили бота: {count_all}\n" \
           f"Зарегистрировались: {count_accounts}\n" \
           f"Пользуются: {count_active}\n" \
           f"\n" \
           f"В работе: {human_time(work_time.total_seconds())}\n"
    await callback_query.message.edit_text(info, parse_mode=html)


@dp.message(Command('reload'))
@security()
async def _reload(message: Message):
    if await developer_command(message): return
    if release:
        await message.answer("<b>Перезапуск бота</b>", parse_mode=html)
        print("Перезапуск бота")
        async with aiohttp.ClientSession() as session:
            async with session.post("https://panel.netangels.ru/api/gateway/token/",
                                    data={"api_key": Variables.ApiKey}) as response:
                token = (await response.json())['token']
                await session.post(f"https://api-ms.netangels.ru/api/v1/hosting/background-processes/{Variables.ProcessId}/restart",
                                   headers={"Authorization": f"Bearer {token}"})
    else:
        await message.answer("В тестовом режиме перезапуск бота программно не предусмотрен!")
        print("В тестовом режиме перезапуск бота программно не предусмотрен!")


@dp.message(Command('stop'))
@security()
async def _stop(message: Message):
    if await developer_command(message): return
    await message.answer("<b>Остановка бота и программы</b>", parse_mode=html)
    print("Остановка бота и программы")
    if release:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://panel.netangels.ru/api/gateway/token/",
                                    data={"api_key": Variables.ApiKey}) as response:
                token = (await response.json())['token']
                await session.post(f"https://api-ms.netangels.ru/api/v1/hosting/background-processes/{Variables.ProcessId}/stop",
                                   headers={"Authorization": f"Bearer {token}"})
    await dp.stop_polling()
    asyncio.get_event_loop().stop()


@dp.message(Command('critical_stop'))
@security()
async def _critical_stop(message: Message):
    if await developer_command(message): return
    await message.answer("<b>Критическая остановка</b>", parse_mode=html)
    print("Критическая остановка")
    os._exit(0)


@dp.message(Command('mailing'))
@security('state')
async def _start_mailing(message: Message, state: FSMContext):
    if await developer_command(message): return
    await state.set_state(UserState.Admin.mailing)
    await message.answer("Отправь сообщение, которое я разошлю все активным пользователям бота")


@dp.message(UserState.Admin.mailing)
@security('state')
async def _mailing(message: Message, state: FSMContext):
    if await developer_command(message): return
    await state.update_data(message_id=message.message_id)
    markup = IMarkup(inline_keyboard=[[IButton(text="Переслать 💬", callback_data="mailing_forward"),
                                       IButton(text="Отправить 🔐", callback_data="mailing_send")],
                                      [IButton(text="❌ Отмена ❌", callback_data="stop_mailing")]])
    await message.answer("Выбери способ рассылки сообщения 👇", reply_markup=markup)


@dp.callback_query(F.data.in_(["mailing_forward", "mailing_send", "stop_mailing"]))
@security('state')
async def _confirm_mailing(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    match callback_query.data:
        case "mailing_forward":
            await callback_query.message.edit_text(f"{callback_query.message.text}\nПересылка")
            message_id = (await state.get_data())['message_id']
            await state.clear()
            fun = lambda user_id: bot.forward_message(user_id, callback_query.from_user.id, message_id)
        case "mailing_send":
            await callback_query.message.edit_text(f"{callback_query.message.text}\nОтправка")
            message_id = (await state.get_data())['message_id']
            await state.clear()
            fun = lambda user_id: bot.copy_message(user_id, callback_query.from_user.id, message_id)
        case _:
            await state.clear()
            return await callback_query.message.edit_text("Операция отменена!")
    # Получение количества активным зарегистрированных и активных пользователей
    result = [await db.fetch_one("SELECT COUNT(*) FROM accounts", one_data=True), 0, 0, 0]
    for account in await db.fetch_all("SELECT account_id, is_started FROM settings"):
        if account['is_started']:
            result[1] += 1  # Количество активных пользователей
            try:
                await fun(account['account_id'])
            except (TelegramBadRequest, TelegramForbiddenError):
                result[2] += 1  # Количество ошибок
            else:
                result[3] += 1  # Количество доставленных сообщений
            await asyncio.sleep(1)
    await callback_query.message.answer(f"Рассылка завершена!\nВсего пользователей: {result[0]}\n"
                                        f"Активные пользователи: {result[1]}\nДоставлено сообщений: {result[3]}\n"
                                        f"Произошло ошибок: {result[2]}")


@dp.message(Command('login'))
@security('state')
async def _login(message: Message, state: FSMContext):
    if await developer_command(message): return
    await state.set_state(UserState.Admin.login)
    markup = KMarkup(keyboard=[[KButton(text="Открыть", web_app=WebAppInfo(url=f"{Data.web_app}/code"))],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    await message.answer("Страница входа", reply_markup=markup)


@dp.message(UserState.Admin.login)
@security('state')
async def _login_code(message: Message, state: FSMContext):
    if await new_message(message): return
    await state.clear()
    if message.content_type == "web_app_data":
        await message.answer(f"Получено: {message.web_app_data.data}\n"
                             f"Расшифровано: {unzip_int_data(message.web_app_data.data)}", reply_markup=KRemove())
    else:
        await message.answer("Отмена", reply_markup=KRemove())


@dp.message(Command('payment'))
@security()
async def _payment(message: Message):
    if await developer_command(message): return
    await message.answer_photo(**await payment_menu())


def admin_initial():
    pass  # Чтобы PyCharm не ругался
