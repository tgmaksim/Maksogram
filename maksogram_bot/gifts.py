from typing import Any
from asyncpg.exceptions import UniqueViolationError
from core import (
    db,
    html,
    security,
    get_gifts,
    json_encode,
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


@dp.callback_query(F.data == "gifts")
@security()
async def _gifts(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await gifts_menu(callback_query.message.chat.id))


async def gifts_menu(account_id: int) -> dict[str, Any]:
    buttons = []
    users = await db.fetch_all(f"SELECT user_id, name FROM gifts WHERE account_id={account_id}")
    for user in users:
        buttons.append([IButton(text=f"🎁 {user['name']}", callback_data=f"gift_menu{user['user_id']}")])
    buttons.append([IButton(text="➕ Добавить пользователя", callback_data="new_gift")])
    buttons.append([IButton(text="◀️  Назад", callback_data="menu")])
    return {"text": "🎁 <b>Новый подарок</b>\nКогда кто-то из выбранных пользователей получит или скроет подарок, я сообщу вам",
            "parse_mode": html, "reply_markup": IMarkup(inline_keyboard=buttons)}


@dp.callback_query(F.data.startswith("new_gift"))
@security('state')
async def _new_gift_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    if await db.fetch_one(f"SELECT COUNT(*) FROM gifts WHERE account_id={callback_query.from_user.id}", one_data=True) >= 4:
        return await callback_query.answer("У вас максимальное количество")
    await state.set_state(UserState.gift)
    request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request_users)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте пользователя для отслеживания", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.gift)
@security('state')
async def _new_gift(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    if message.content_type == "users_shared":
        user_id = message.users_shared.user_ids[0]
        account_id = message.chat.id
        if user_id == account_id:  # Себя нельзя
            await message.answer(**await gifts_menu(account_id))
        else:
            user = await telegram_clients[account_id].get_entity(user_id)
            name = user.first_name + (f" {user.last_name}" if user.last_name else "")
            gifts = json_encode({gift.id: gift.__dict__ for gift in (await get_gifts(account_id, user_id)).values()})
            try:
                await db.execute(f"INSERT INTO gifts VALUES ({account_id}, {user_id}, $1, $2)", name, gifts)
            except UniqueViolationError:  # Уже есть
                pass
            await message.answer(**await gift_menu(message.chat.id, user_id))
    else:
        await message.answer(**await gifts_menu(message.chat.id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


async def gift_menu(account_id: int, user_id: int) -> dict[str, Any]:
    name = await db.fetch_one(f"SELECT name FROM gifts WHERE account_id={account_id} AND user_id={user_id}", one_data=True)
    if name is None:
        return await gifts_menu(account_id)
    markup = IMarkup(inline_keyboard=[
        [IButton(text="🔴 Выключить", callback_data=f"gift_del{user_id}")],
        [IButton(text="◀️  Назад", callback_data="gifts")]])
    return {"text": f"🎁 <b>Новый подарок</b>\nКогда <b>{name}</b> получит или скроет подарок, я сообщу вам\n",
            "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data.startswith("gift_del"))
@security()
async def _gift_del(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    user_id = int(callback_query.data.replace("gift_del", ""))
    await db.execute(f"DELETE FROM gifts WHERE account_id={callback_query.from_user.id} AND user_id={user_id}")
    await callback_query.message.edit_text(**await gifts_menu(callback_query.message.chat.id))


@dp.callback_query(F.data.startswith("gift_menu"))
@security()
async def _gift_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    user_id = int(callback_query.data.replace("gift_menu", ""))
    await callback_query.message.edit_text(**await gift_menu(callback_query.message.chat.id, user_id))


def gifts_initial():
    pass  # Чтобы PyCharm не ругался
