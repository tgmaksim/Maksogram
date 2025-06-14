import os

from typing import Any
from asyncpg.exceptions import UniqueViolationError
from core import (
    db,
    html,
    OWNER,
    get_bio,
    security,
    get_gifts,
    get_avatars,
    json_encode,
    resources_path,
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
    new_user,
    UserState,
    new_message,
    new_callback_query,
)


@dp.callback_query((F.data == "changed_profile").__or__(F.data == "changed_profilePrev"))
@security()
async def _changed_profile(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    prev = "Prev" if callback_query.data == "changed_profilePrev" else ""
    await callback_query.message.edit_text(**await changed_profiles_menu(callback_query.from_user.id, prev=prev))


async def changed_profiles_menu(account_id: int, text: str = None, prev: str = "") -> dict[str, Any]:
    buttons = []
    if prev:
        users = []
    else:
        users = sorted(await db.fetch_all(f"SELECT user_id, name FROM changed_profiles WHERE account_id={account_id}"),
                       key=lambda x: len(x['name']))  # Список пользователей, отсортированных по возрастанию длины имени
    i = 0
    while i < len(users):  # Если длина имен достаточно короткая, то помещаем 2 в ряд, иначе 1
        if i + 1 < len(users) and all(map(lambda x: len(x['name']) <= 15, users[i:i+1])):
            buttons.append([IButton(text=f"🖼️ {users[i]['name']}", callback_data=f"changed_profile_menu{users[i]['user_id']}"),
                            IButton(text=f"🖼️ {users[i+1]['name']}", callback_data=f"changed_profile_menu{users[i+1]['user_id']}")])
            i += 1
        else:
            buttons.append([IButton(text=f"🖼️ {users[i]['name']}", callback_data=f"changed_profile_menu{users[i]['user_id']}")])
        i += 1
    buttons.append([IButton(text="➕ Добавить пользователя", callback_data=f"new_changed_profile{prev}")])
    buttons.append([IButton(text="◀️  Назад", callback_data="menu")])
    return {"text": text or "🖼️ <b>Профиль друга</b>\nДобавьте пользователя и первым узнавайте о новой аватарке, новом подарке или "
                            "измененном «О себе» в профиле собеседника", "parse_mode": html, "reply_markup": IMarkup(inline_keyboard=buttons)}


@dp.callback_query(F.data == "new_changed_profilePrev")
@security()
async def _new_changed_profile_prev(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.answer("Следить за профилем друга доступно только для пользователей Maksogram", True)


@dp.callback_query(F.data == "new_changed_profile")
@security('state')
async def _new_changed_profile_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    if await db.fetch_one(f"SELECT COUNT(*) FROM changed_profiles WHERE account_id={callback_query.from_user.id}", one_data=True) >= 4:
        if callback_query.from_user.id != OWNER:
            return await callback_query.answer("У вас максимальное количество отслеживаемых пользователей", True)
    await state.set_state(UserState.changed_profile)
    request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request_users)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте пользователя для отслеживания кнопкой, ID, username или "
                                                      "номер телефона", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.changed_profile)
@security('state')
async def _changed_profile(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    account_id = message.chat.id

    user = await new_user(message, changed_profiles_menu)
    if user:
        user_id = user.id
        if user_id == account_id:  # Себя нельзя
            await message.answer(**await changed_profiles_menu(account_id))
        else:
            name = f"{user.first_name} {user.last_name or ''}".strip()
            try:
                await db.execute(f"INSERT INTO changed_profiles VALUES ({account_id}, {user_id}, $1, NULL, NULL, NULL)", name)
            except UniqueViolationError:  # Уже есть
                pass
            await message.answer(**await changed_profile_menu(account_id, user_id, dict(name=name, avatars=None, gifts=None, bio=None)))

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


async def changed_profile_menu(account_id: int, user_id: int, user: dict = None) -> dict[str, Any]:
    indicator = lambda status: "🔴" if status is None else "🟢"
    command = lambda status: "on" if status is None else "off"
    if not user:
        user = await db.fetch_one(f"SELECT name, avatars, gifts, bio FROM changed_profiles "
                                  f"WHERE account_id={account_id} AND user_id={user_id}")
    if user is None:
        return await changed_profiles_menu(account_id)
    markup = IMarkup(inline_keyboard=[[IButton(text=f"{indicator(user['avatars'])} Аватарка 📷",
                                               callback_data=f"changed_profile_avatars_{command(user['avatars'])}_{user_id}"),
                                       IButton(text=f"{indicator(user['gifts'])} Подарки 🎁",
                                               callback_data=f"changed_profile_gifts_{command(user['gifts'])}_{user_id}")],
                                      [IButton(text=f"{indicator(user['bio'])} О себе",
                                               callback_data=f"changed_profile_bio_{command(user['bio'])}_{user_id}"),
                                       IButton(text="🚫 Удалить", callback_data=f"changed_profile_del{user_id}")],
                                      [IButton(text="◀️  Назад", callback_data="changed_profile")]])
    return {"text": f"🖼️ <b>Профиль друга</b>\nМожно выбрать, о каких изменениях в профиле у <b>{user['name']}</b> получать "
                    f"уведомления. Удалите пользователя, если слежка больше не нужна\n", "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data.startswith("changed_profile_avatars_on").__or__(F.data.startswith("changed_profile_avatars_off")).__or__(
    F.data.startswith("changed_profile_gifts_on")).__or__(F.data.startswith("changed_profile_gifts_off")).__or__(
    F.data.startswith("changed_profile_bio_on")).__or__(F.data.startswith("changed_profile_bio_off")))
@security()
async def _changed_profile_function_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    function, command, user_id = callback_query.data.replace("changed_profile_", "").split("_")
    user_id = int(user_id)
    user = await db.fetch_one(f"SELECT name, {function} FROM changed_profiles WHERE account_id={account_id} AND user_id={user_id}")
    if user is None:
        return await changed_profiles_menu(account_id)
    if (command == "on") == user[function]:
        return await callback_query.answer()
    data, warning = None, "Произошла ошибка..."
    if command == "on":
        if function == "avatars":
            await callback_query.answer("Подождите зеленого сигнала, пока скачиваются все аватарки...", True)
            data = json_encode({avatar[0]: 'mp4' if avatar[1].video_sizes else 'png' for avatar in
                                (await get_avatars(account_id, user_id, download=True) or {}).items()})
            warning = f"У пользователя {user['name']} слишком много аватарок"
        elif function == "gifts":
            data = json_encode({gift.id: gift.__dict__ for gift in (await get_gifts(account_id, user_id) or {}).values()})
            warning = f"У пользователя {user['name']} слишком много подарков"
        elif function == "bio":
            data = await get_bio(account_id, user_id)
        if data is None:
            return await callback_query.answer(warning, True)
    else:
        if function == "avatars":  # Удаляем ранее сохраненные аватарки
            path = resources_path("avatars")
            for avatar in os.listdir(path):
                if avatar.startswith(f"{account_id}.{user_id}"):
                    os.remove(resources_path(f"avatars/{avatar}"))
    await db.execute(f"UPDATE changed_profiles SET {function}=$1 WHERE account_id={account_id} AND user_id={user_id}", data)
    await callback_query.message.edit_text(**await changed_profile_menu(account_id, int(user_id)))


@dp.callback_query(F.data.startswith("changed_profile_menu"))
@security()
async def _changed_profile_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    user_id = int(callback_query.data.replace("changed_profile_menu", ""))
    await callback_query.message.edit_text(**await changed_profile_menu(callback_query.from_user.id, user_id))


@dp.callback_query(F.data.startswith("changed_profile_del"))
@security()
async def _changed_profile_del(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    user_id = int(callback_query.data.replace("changed_profile_del", ""))
    path = resources_path("avatars")
    for avatar in os.listdir(path):
        if avatar.startswith(f"{account_id}.{user_id}"):
            os.remove(resources_path(f"avatars/{avatar}"))
    await db.execute(f"DELETE FROM changed_profiles WHERE account_id={account_id} AND user_id={user_id}")
    await callback_query.message.edit_text(**await changed_profiles_menu(account_id))


def changed_profile_initial():
    pass  # Чтобы PyCharm не ругался
