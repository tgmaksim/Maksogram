import os

from mg.config import OWNER, WEB_APP

from aiogram import F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import Message, CallbackQuery, WebAppInfo
from mg.bot.types import dp, bot, UserState, CallbackData, Sleep
from mg.bot.functions import developer_command, new_callback_query, new_message

from aiogram.types import KeyboardButton as KButton
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import ReplyKeyboardRemove as KRemove
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton

from mg.client.functions import get_accounts
from mg.core.functions import error_notify, unzip_int_data, human_timedelta

from . functions import (
    block_user,
    count_users,
    stop_maksogram,
    count_accounts,
    reload_maksogram,
    get_working_time,
    count_working_accounts,
)


cb = CallbackData()


@dp.message(Command('reload'))
@error_notify()
async def _reload(message: Message):
    if await developer_command(message): return
    await message.answer("<b>Перезапуск Maksogram</b>")

    Sleep.reload = True
    await reload_maksogram()


@dp.message(Command('stop'))
@error_notify()
async def _stop(message: Message):
    if await developer_command(message): return
    await message.answer("<b>Остановка Maksogram</b>")

    Sleep.reload = True
    await stop_maksogram()


@dp.message(Command('critical_stop'))
@error_notify()
async def _critical_stop(message: Message):
    if await developer_command(message): return
    await message.answer("<b>Критическая остановка Maksogram</b>")

    os._exit(0)  # Немедленная остановка


@dp.message(F.reply_to_message.__and__(F.chat.id == OWNER).__and__(F.reply_to_message.text.startswith("User: ")))
@error_notify()
async def _sender(message: Message):
    user_id = int(message.reply_to_message.text.split('\n', 1)[0].removeprefix("User: "))

    if message.text.lower() in ("блок", "бан", "блокировать", "забанить"):
        await block_user(user_id)
        await message.answer("Пользователь заблокирован!")
        return

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
@error_notify()
async def _admin(message: Message):
    if await developer_command(message): return

    markup = IMarkup(inline_keyboard=[[IButton(text="📊 Статистика", callback_data=cb('admin_statistics'))]])
    await message.answer("Команды разработчика:\n"
                         "/reload - перезапустить Maksogram\n"
                         "/stop - остановить Maksogram\n"
                         "/critical_stop - экстренная остановка\n"
                         "/mailing - рассылка\n"
                         "/login - Web App ввода кода", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('admin_statistics')))
@error_notify()
async def _admin_statistics(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    users = await count_users()
    accounts = await count_accounts()
    working_accounts = await count_working_accounts()
    working_time = human_timedelta(await get_working_time())

    info = ("📊 <b>Статистика Maksogram</b>",
            f"Пользователей: {users}",
            f"Клиентов: {accounts}",
            f"Активных клиентов: {working_accounts}",
            f"В работе: {working_time}")
    await callback_query.message.edit_text('\n'.join(info))


@dp.message(Command('login'))
@error_notify('state')
async def _login(message: Message, state: FSMContext):
    if await developer_command(message): return
    await state.set_state(UserState.Admin.login)

    markup = KMarkup(keyboard=[[KButton(text="Открыть", web_app=WebAppInfo(url=f"{WEB_APP}/code"))],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    await message.answer("Страница ввода кода", reply_markup=markup)


@dp.message(UserState.Admin.login)
@error_notify('state')
async def _login_code(message: Message, state: FSMContext):
    await state.clear()

    if message.web_app_data:
        await message.answer(f"Получено: {message.web_app_data.data}\nКод: {unzip_int_data(message.web_app_data.data)}", reply_markup=KRemove())
    else:
        await message.answer("Отмена", reply_markup=KRemove())


@dp.message(Command('mailing'))
@error_notify('state')
async def _mailing_start(message: Message, state: FSMContext):
    if await developer_command(message): return
    await state.set_state(UserState.Admin.mailing)
    await message.answer("Отправь сообщение, которое будет разослано всем активным клиентам")


@dp.message(UserState.Admin.mailing)
@error_notify('state')
async def _mailing_variant(message: Message, state: FSMContext):
    if await new_message(message): return
    await state.update_data(message_id=message.message_id)

    markup = IMarkup(inline_keyboard=[[IButton(text="Переслать 💬", callback_data=cb('mailing', 'forward')),
                                       IButton(text="Отправить 🔐", callback_data=cb('mailing', 'send'))],
                                      [IButton(text="❌ Отмена ❌", callback_data=cb('mailing', 'cancel'))]])
    await message.answer("Выбери способ рассылки сообщения 👇", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('mailing')))
@error_notify('state')
async def _mailing(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    param = cb.deserialize(callback_query.data)[0]

    if param == "cancel":
        await state.clear()
        await callback_query.message.edit_text("Операция отменена")
        return

    result = [await count_accounts(), 0, 0, 0]  # Все клиентов, активных клиентов, доставленных сообщений, ошибок
    if param == "forward":
        text = "Пересылка"
        mailing_message = bot.forward_message
    else:
        text = "Отправка"
        mailing_message = bot.copy_message
    await callback_query.message.edit_text(f"{callback_query.message.text}\n{text}")

    for account_id, is_started in await get_accounts():
        if not is_started:
            continue

        result[1] += 1

        try:
            await mailing_message(account_id, callback_query.from_user.id, message_id)
        except TelegramForbiddenError:
            result[3] += 1
        else:
            result[2] += 1

    await callback_query.message.edit_text(f"Рассылка завершена!\nКлиентов: {result[0]}\nАктивных клиентов: {result[1]}\n"
                                           f"Доставлено сообщений: {result[2]}\nВозникло ошибок: {result[3]}")


def admin_initial():
    pass  # Чтобы PyCharm не ругался
