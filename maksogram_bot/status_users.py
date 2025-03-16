from typing import Any
from core import (
    db,
    html,
    security,
    telegram_clients,
)

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.types import KeyboardButton as KButton
from aiogram.types import KeyboardButtonRequestUsers
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from .core import (
    dp,
    bot,
    UserState,
    new_message,
    new_callback_query,
)


@dp.callback_query(F.data == "status_users")
@security()
async def _status_users(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await status_users_menu(callback_query.message.chat.id))


async def status_users_menu(account_id: int) -> dict[str, Any]:
    buttons = []
    users = await db.fetch_all(f"SELECT user_id, name FROM status_users WHERE account_id={account_id}")  # Список друзей в сети
    for user in users:
        buttons.append([IButton(text=f"🌐 {user['name']}", callback_data=f"status_user_menu{user['user_id']}")])
    buttons.append([IButton(text="➕ Добавить нового пользователя", callback_data="new_status_user")])
    buttons.append([IButton(text="◀️  Назад", callback_data="menu")])
    return {"text": "🌐 <b>Друг в сети</b>\nЯ уведомлю вас, если пользователь будет онлайн/офлайн. Не работает, если собеседник "
                    "скрыл время последнего захода...", "reply_markup": IMarkup(inline_keyboard=buttons), "parse_mode": html}


@dp.callback_query(F.data.startswith("status_user_menu"))
@security()
async def _status_user_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    user_id = int(callback_query.data.replace("status_user_menu", ""))
    await callback_query.message.edit_text(**await status_user_menu(callback_query.message.chat.id, user_id))


async def status_user_menu(account_id: int, user_id: int) -> dict[str, Any]:
    def status(parameter: bool):
        return "🟢" if parameter else "🔴"

    def command(parameter: bool):
        return "off" if parameter else "on"

    user = await db.fetch_one(f"SELECT name, online, offline, reading, awake FROM status_users WHERE account_id={account_id} AND "
                              f"user_id={user_id}")  # Данные о друге в сети
    if user is None:
        return await status_users_menu(account_id)
    markup = IMarkup(inline_keyboard=[
        [IButton(text=f"{status(user['online'])} Онлайн", callback_data=f"status_user_online_{command(user['online'])}_{user_id}"),
         IButton(text=f"{status(user['offline'])} Оффлайн", callback_data=f"status_user_offline_{command(user['offline'])}_{user_id}")],
        [IButton(text=f"{status(user['awake'])} Проснется 💤", callback_data=f"status_user_awake_{command(user['awake'])}_{user_id}")],
        [IButton(text=f"{status(user['reading'])} Чтение моего сообщения", callback_data=f"status_user_reading_{command(user['reading'])}_{user_id}")],
        [IButton(text="🚫 Удалить пользователя", callback_data=f"status_user_del{user_id}")],
        [IButton(text="◀️  Назад", callback_data="status_users")]])
    return {"text": f"🌐 <b>Друг в сети</b>\nКогда <b>{user['name']}</b> будет онлайн/оффлайн, проснется или прочитает сообщение, "
                    "я сообщу", "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data.startswith("status_user_online_on").__or__(F.data.startswith("status_user_online_off")).__or__(
                   F.data.startswith("status_user_offline_on")).__or__(F.data.startswith("status_user_offline_off")).__or__(
                   F.data.startswith("status_user_reading_on")).__or__(F.data.startswith("status_user_reading_off")).__or__(
                   F.data.startswith("status_user_awake_on")).__or__(F.data.startswith("status_user_awake_off")))
@security()
async def _status_user_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    function_status_user, command, user_id = callback_query.data.replace("status_user_", "").split("_")
    user = await db.fetch_one(f"SELECT true FROM status_users WHERE account_id={account_id} AND user_id={user_id}", one_data=True)
    if user is None:  # Пользователь удален из списка друзей в сети
        return await callback_query.message.edit_text(**await status_users_menu(account_id))
    if function_status_user == "awake":
        await db.execute(f"UPDATE status_users SET {function_status_user}={'now()' if command == 'on' else 'NULL'} WHERE "
                         f"account_id={account_id} AND user_id={user_id}")  # Вкл/выкл функции
    else:
        await db.execute(f"UPDATE status_users SET {function_status_user}={'true' if command == 'on' else 'false'} WHERE "
                         f"account_id={account_id} AND user_id={user_id}")  # Вкл/выкл нужной функции друга в сети
    await callback_query.message.edit_text(**await status_user_menu(account_id, int(user_id)))


@dp.callback_query(F.data == "new_status_user")
@security('state')
async def _new_status_user_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    if await db.fetch_one(f"SELECT COUNT(*) FROM status_users WHERE account_id={callback_query.from_user.id}", one_data=True) >= 3:
        # Количество друзей в сети уже достигло максимума
        return await callback_query.answer("У вас максимальное количество!", True)
    await state.set_state(UserState.status_user)
    request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request_users)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте пользователя для отслеживания", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.status_user)
@security('state')
async def _new_status_user(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    if message.content_type == "users_shared":
        user_id = message.users_shared.user_ids[0]
        account_id = message.chat.id
        if user_id == account_id:  # Себя нельзя
            await message.answer(**await status_users_menu(account_id))
        else:
            user = await telegram_clients[message.chat.id].get_entity(user_id)
            name = user.first_name + (f" {user.last_name}" if user.last_name else "")
            name = (name[:30] + "...") if len(name) > 30 else name
            telegram_clients[account_id].list_event_handlers()[4][1].chats.add(user_id)
            await db.execute(f"INSERT INTO status_users VALUES ({account_id}, {user_id}, $1, false, false, false, NULL)", name)
            await message.answer(**await status_user_menu(message.chat.id, user_id))
    else:
        await message.answer(**await status_users_menu(message.chat.id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data.startswith("status_user_del"))
@security()
async def _status_user_del(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    user_id = int(callback_query.data.replace("status_user_del", ""))
    account_id = callback_query.from_user.id
    telegram_clients[account_id].list_event_handlers()[4][1].chats.remove(user_id)
    await db.execute(f"DELETE FROM status_users WHERE account_id={account_id} AND user_id={user_id}")  # Удаление друга в сети
    await callback_query.message.edit_text(**await status_users_menu(callback_query.message.chat.id))


def status_users_initial():
    pass  # Чтобы PyCharm не ругался
