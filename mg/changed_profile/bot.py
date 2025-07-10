from typing import Any

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.types import KeyboardButton as KButton
from aiogram.types import KeyboardButtonRequestUsers
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from mg.bot.types import (
    dp,
    bot,
    UserState,
    CallbackData,
)
from mg.bot.functions import (
    new_message,
    request_user,
    new_callback_query,
)

from mg.core.database import Database
from mg.core.functions import error_notify, full_name

from . functions import (
    get_bio,
    get_gifts,
    get_avatars,
    delete_avatars,
    download_avatars,
    add_changed_profile,
    delete_changed_profile,
    update_changed_profile,
    check_count_changed_profiles,
    get_changed_profile_settings,
    get_changed_profiles_settings,
)

cb = CallbackData()


@dp.callback_query(F.data.startswith(cb.command('changed_profile')))
@error_notify()
async def _changed_profile(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    prev = cb.deserialize(callback_query.data).get(0) is True
    await callback_query.message.edit_text(**await changed_profiles_menu(callback_query.from_user.id, prev=prev))


async def changed_profiles_menu(account_id: int, prev: bool = False) -> dict[str, Any]:
    buttons = []
    users = await get_changed_profiles_settings(account_id)
    i = 0

    while i < len(users):  # Если длина имен достаточно короткая, то помещаем 2 в ряд, иначе 1
        if i + 1 < len(users) and len(users[i].name) <= 15 and len(users[i+1].name) <= 15:

            buttons.append([IButton(text=f"🖼️ {users[i].name}", callback_data=cb('changed_profile_menu', users[i].user_id)),
                            IButton(text=f"🖼️ {users[i+1].name}", callback_data=cb('changed_profile_menu', users[i+1].user_id))])
            i += 1
        else:
            buttons.append([IButton(text=f"🖼️ {users[i].name}", callback_data=cb('changed_profile_menu', users[i].user_id))])
        i += 1

    buttons.append([IButton(text="➕ Добавить пользователя", callback_data=cb('new_changed_profile', prev))])
    buttons.append([IButton(text="◀️  Назад", callback_data=cb('menu'))])

    return dict(
        text="🖼️ <b>Профиль друга</b>\nДобавьте пользователя и первым узнавайте о новой аватарке, новом подарке или измененном «О себе» в "
             "профиле собеседника", reply_markup=IMarkup(inline_keyboard=buttons))


@dp.callback_query(F.data.startswith(cb.command('changed_profile_menu')))
@error_notify()
async def _changed_profile_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    user_id = cb.deserialize(callback_query.data)[0]
    await callback_query.message.edit_text(**await changed_profile_menu(callback_query.from_user.id, user_id))


async def changed_profile_menu(account_id: int, user_id: int) -> dict[str, Any]:
    indicator = lambda status: "🔴" if status is None else "🟢"

    user = await get_changed_profile_settings(account_id, user_id)
    if user is None:  # Пользователь у клиента в базе данных не найден
        return await changed_profiles_menu(account_id)

    markup = IMarkup(inline_keyboard=[[
        IButton(text=f"{indicator(user.avatars)} Аватарка 📷",
                callback_data=cb('changed_profile_switch', 'avatars', user.avatars is None, user_id)),
         IButton(text=f"{indicator(user.gifts)} Подарки 🎁",
                 callback_data=cb('changed_profile_switch', 'gifts', user.gifts is None, user_id))],
        [IButton(text=f"{indicator(user.bio)} О себе",
                 callback_data=cb('changed_profile_switch', 'bio', user.bio is None, user_id)),
         IButton(text="🚫 Удалить", callback_data=cb('changed_profile_del', user_id))],
        [IButton(text="◀️  Назад", callback_data=cb('changed_profile'))]])

    return dict(
        text=f"🖼️ <b>Профиль друга</b>\nМожно выбрать, о каких изменениях в профиле у <b>{user.name}</b> получать уведомления. "
             f"Удалите пользователя, если слежка больше не нужна", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('new_changed_profile')))
@error_notify('state')
async def _new_changed_profile_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    prev = cb.deserialize(callback_query.data).get(0) is True
    if prev:
        await callback_query.answer("Следить за профилем друга доступно только для пользователей Maksogram", True)
        return

    if not await check_count_changed_profiles(callback_query.from_user.id):
        await callback_query.answer("У вас максимальное количество отслеживаемых пользователей", True)
        return

    request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request_users)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте пользователя для отслеживания кнопкой, ID, username или "
                                                      "номер телефона", reply_markup=markup)).message_id

    await state.set_state(UserState.new_changed_profile)
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.new_changed_profile)
@error_notify('state')
async def _new_changed_profile(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    account_id = message.chat.id

    if message.text == "Отмена":
        await state.clear()
        await message.answer(**await changed_profiles_menu(account_id))
    else:
        response = await request_user(message, can_yourself=False)

        if not response.ok:
            request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False, max_quantity=1)
            markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request_users)],
                                       [KButton(text="Отмена")]], resize_keyboard=True)
            new_message_id = (await message.answer(response.warning, reply_markup=markup)).message_id
            await state.update_data(message_id=new_message_id)
        else:
            await state.clear()
            user_id = response.user.id
            await add_changed_profile(account_id, user_id, full_name(response.user))
            await message.answer(**await changed_profile_menu(account_id, user_id))

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data.startswith(cb.command('changed_profile_switch')))
@error_notify()
async def _changed_profile_function_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    function, command, user_id = cb.deserialize(callback_query.data)
    user_id = int(user_id)

    user = await get_changed_profile_settings(account_id, user_id)
    if user is None:  # Пользователь у клиента в базе данных не найден
        await callback_query.answer(f"Пользователь не найден...", True)
        await changed_profiles_menu(account_id)
        return

    if command == user.__getattribute__(function) is not None:  # Результат совпадает с действием
        await callback_query.answer()
        return

    data, warning = None, "Произошла ошибка..."
    if command:
        if function == "avatars":
            avatars, data = await get_avatars(account_id, user_id), '{}'
            warning = f"У пользователя {user.name} слишком много аватарок"
            if avatars:
                await callback_query.answer("Подождите зеленого сигнала, пока скачиваются все аватарки...", True)
                await download_avatars(account_id, user_id, avatars=avatars)
                data = Database.serialize({str(avatar_id): full_avatar.to_dict() for avatar_id, full_avatar in avatars.items()})

        elif function == "gifts":
            warning = f"У пользователя {user.name} слишком много подарков"
            gifts, data = await get_gifts(account_id, user_id), '{}'
            if gifts:
                data = Database.serialize({str(gift_id): gift.to_dict() for gift_id, gift in gifts.items()})

        elif function == "bio":
            data = await get_bio(account_id, user_id)

        if data is None:
            await callback_query.answer(warning, True)
            return
    else:
        if function == "avatars":  # Удаляем ранее сохраненные аватарки
            delete_avatars(account_id, user_id)

    await update_changed_profile(account_id, user_id, function, data)
    await callback_query.message.edit_text(**await changed_profile_menu(account_id, user_id))


@dp.callback_query(F.data.startswith(cb.command('changed_profile_del')))
@error_notify()
async def _changed_profile_del(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    user_id = cb.deserialize(callback_query.data)[0]
    await delete_changed_profile(account_id, user_id)
    await callback_query.message.edit_text(**await changed_profiles_menu(account_id))


def changed_profile_initial():
    pass  # Чтобы PyCharm не ругался
