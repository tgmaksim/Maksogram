from typing import Any
from asyncpg.exceptions import UniqueViolationError
from core import (
    db,
    html,
    security,
    get_avatars,
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


@dp.callback_query(F.data == "avatars")
@security()
async def _avatars(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await avatars_menu(callback_query.message.chat.id))


async def avatars_menu(account_id: int) -> dict[str, Any]:
    buttons = []
    users = sorted(await db.fetch_all(f"SELECT user_id, name FROM avatars WHERE account_id={account_id}"),
                   key=lambda x: len(x['name']))  # Список новых аватарок, отсортированных по возрастанию длины имени
    i = 0
    while i < len(users):
        if i + 1 < len(users) and all(map(lambda x: len(x['name']) <= 15, users[i:i+1])):
            buttons.append([IButton(text=f"📸 {users[i]['name']}", callback_data=f"avatar_menu{users[i]['user_id']}"),
                            IButton(text=f"📸 {users[i+1]['name']}", callback_data=f"avatar_menu{users[i+1]['user_id']}")])
            i += 1
        else:
            buttons.append([IButton(text=f"📸 {users[i]['name']}", callback_data=f"avatar_menu{users[i]['user_id']}")])
        i += 1
    buttons.append([IButton(text="➕ Добавить пользователя", callback_data="new_avatar")])
    buttons.append([IButton(text="◀️  Назад", callback_data="changed_profile")])
    return {"text": "📸 <b>Новая аватарка</b>\nКогда кто-то из выбранных пользователей изменит или добавит аватарку, я сообщу вам",
            "parse_mode": html, "reply_markup": IMarkup(inline_keyboard=buttons)}


@dp.callback_query(F.data.startswith("new_avatar"))
@security('state')
async def _new_avatar_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    if await db.fetch_one(f"SELECT COUNT(*) FROM avatars WHERE account_id={callback_query.from_user.id}", one_data=True) >= 4:
        # Количество новых аватарок уже достигло максимума
        return await callback_query.answer("У вас максимальное количество \"новых аватарок\"")
    await state.set_state(UserState.avatar)
    request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request_users)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте пользователя для отслеживания", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.avatar)
@security('state')
async def _new_avatar(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    if message.content_type == "users_shared":
        user_id = message.users_shared.user_ids[0]
        account_id = message.chat.id
        if user_id == account_id:  # Себя нельзя
            await message.answer(**await avatars_menu(account_id))
        else:
            user = await telegram_clients[account_id].get_entity(user_id)
            name = user.first_name + (f" {user.last_name}" if user.last_name else "")
            avatars = await get_avatars(account_id, user_id)
            if avatars is None:
                await message.answer(f"<b>Слишком много аватарок у {name}</b>", parse_mode=html,
                                     reply_markup=(await avatars_menu(account_id))['reply_markup'])
            else:
                id_avatars = list(map(lambda x: x.id, avatars.values()))
                try:
                    await db.execute(f"INSERT INTO avatars VALUES ({account_id}, {user_id}, $1, '{id_avatars}')", name)  # Добавление новой аватарки
                except UniqueViolationError:  # Уже есть
                    pass
                await message.answer(**await avatar_menu(message.chat.id, user_id))
    else:
        await message.answer(**await avatars_menu(message.chat.id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


async def avatar_menu(account_id: int, user_id: int) -> dict[str, Any]:
    name = await db.fetch_one(f"SELECT name FROM avatars WHERE account_id={account_id} AND user_id={user_id}", one_data=True)  # Имя новой аватарки
    if name is None:
        return await avatars_menu(account_id)
    markup = IMarkup(inline_keyboard=[
        [IButton(text="🔴 Выключить", callback_data=f"avatar_del{user_id}")],
        [IButton(text="◀️  Назад", callback_data="avatars")]])
    return {"text": f"📸 <b>Новая аватарка</b>\nКогда <b>{name}</b> изменит или добавит аватарку, я сообщу вам\n",
            "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data.startswith("avatar_del"))
@security()
async def _avatar_del(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    user_id = int(callback_query.data.replace("avatar_del", ""))
    await db.execute(f"DELETE FROM avatars WHERE account_id={callback_query.from_user.id} AND user_id={user_id}")  # Удаление новой аватарки
    await callback_query.message.edit_text(**await avatars_menu(callback_query.message.chat.id))


@dp.callback_query(F.data.startswith("avatar_menu"))
@security()
async def _avatar_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    user_id = int(callback_query.data.replace("avatar_menu", ""))
    await callback_query.message.edit_text(**await avatar_menu(callback_query.message.chat.id, user_id))


def avatars_initial():
    pass  # Чтобы PyCharm не ругался
