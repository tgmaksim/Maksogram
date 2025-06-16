from typing import Any
from core import (
    db,
    html,
    security,
    full_name,
    json_encode,
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

from changed_profile.functions import (
    get_bio,
    get_gifts,
    get_avatars,
    delete_avatars,
    add_saved_user,
    get_saved_users,
    download_avatars,
    delete_saved_user,
    get_saved_full_user,
    check_count_saved_users,
)


@dp.callback_query((F.data == "changed_profile").__or__(F.data == "changed_profilePrev"))
@security()
async def _changed_profile(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    prev = "Prev" if callback_query.data == "changed_profilePrev" else ""
    await callback_query.message.edit_text(**await changed_profiles_menu(callback_query.from_user.id, prev=prev))


async def changed_profiles_menu(account_id: int, text: str = None, prev: str = "") -> dict[str, Any]:
    buttons = []
    users = [] if prev else await get_saved_users(account_id)
    i = 0
    while i < len(users):  # Если длина имен достаточно короткая, то помещаем 2 в ряд, иначе 1
        if i + 1 < len(users) and len(users[i].name) <= 15 and len(users[i+1].name) <= 15:
            buttons.append([IButton(text=f"🖼️ {users[i].name}", callback_data=f"changed_profile_menu{users[i].user_id}"),
                            IButton(text=f"🖼️ {users[i+1].name}", callback_data=f"changed_profile_menu{users[i+1].user_id}")])
            i += 1
        else:
            buttons.append([IButton(text=f"🖼️ {users[i].name}", callback_data=f"changed_profile_menu{users[i].user_id}")])
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
    if not await check_count_saved_users(callback_query.from_user.id):
        return await callback_query.answer("У вас максимальное количество отслеживаемых пользователей", True)

    request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request_users)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте пользователя для отслеживания кнопкой, ID, username или "
                                                      "номер телефона", reply_markup=markup)).message_id

    await state.set_state(UserState.changed_profile)
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
            name = full_name(user)
            await add_saved_user(account_id, user_id, name)
            await message.answer(**await changed_profile_menu(account_id, user_id))

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


async def changed_profile_menu(account_id: int, user_id: int) -> dict[str, Any]:
    indicator = lambda status: "🔴" if status is None else "🟢"
    command = lambda status: "on" if status is None else "off"

    user = await get_saved_full_user(account_id, user_id)
    if user is None:  # Пользователь у клиента в базе данных не найден
        return await changed_profiles_menu(account_id)

    markup = IMarkup(inline_keyboard=[
        [IButton(text=f"{indicator(user.avatars)} Аватарка 📷",
                 callback_data=f"changed_profile_avatars_{command(user.avatars)}_{user_id}"),
         IButton(text=f"{indicator(user.gifts)} Подарки 🎁", callback_data=f"changed_profile_gifts_{command(user.gifts)}_{user_id}")],
        [IButton(text=f"{indicator(user.bio)} О себе", callback_data=f"changed_profile_bio_{command(user.bio)}_{user_id}"),
         IButton(text="🚫 Удалить", callback_data=f"changed_profile_del{user_id}")],
        [IButton(text="◀️  Назад", callback_data="changed_profile")]])
    return {"text": f"🖼️ <b>Профиль друга</b>\nМожно выбрать, о каких изменениях в профиле у <b>{user.name}</b> получать "
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

    user = await get_saved_full_user(account_id, user_id)
    if user is None:  # Пользователь у клиента в базе данных не найден
        await callback_query.answer(f"Пользователь не найден...", True)
        return await changed_profiles_menu(account_id)

    if (command == "on") == user.__getattribute__(function) is not None:  # Результат совпадает с действием
        return await callback_query.answer()

    data, warning = None, "Произошла ошибка..."
    if command == "on":
        if function == "avatars":
            avatars, data = await get_avatars(account_id, user_id), '{}'
            if avatars:
                await callback_query.answer("Подождите зеленого сигнала, пока скачиваются все аватарки...", True)
                await download_avatars(account_id, user_id, avatars=avatars)
                data = json_encode({str(avatar_id): full_avatar.to_dict() for avatar_id, full_avatar in avatars.items()})
            warning = f"У пользователя {user.name} слишком много аватарок"
        elif function == "gifts":
            gifts, data = await get_gifts(account_id, user_id), '{}'
            if gifts:
                data = json_encode({str(gift_id): gift.to_dict() for gift_id, gift in gifts.items()})
            warning = f"У пользователя {user.name} слишком много подарков"
        elif function == "bio":
            data = await get_bio(account_id, user_id)

        if data is None:
            return await callback_query.answer(warning, True)
    else:
        if function == "avatars":  # Удаляем ранее сохраненные аватарки
            delete_avatars(account_id, user_id)

    await db.execute(f"UPDATE changed_profiles SET {function}=$1 WHERE account_id={account_id} AND user_id={user_id}", data)
    await callback_query.message.edit_text(**await changed_profile_menu(account_id, user_id))


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
    await delete_saved_user(account_id, user_id)
    await callback_query.message.edit_text(**await changed_profiles_menu(account_id))


def changed_profile_initial():
    pass  # Чтобы PyCharm не ругался
