from html import escape
from typing import Any, Union
from modules.weather import check_city
from asyncpg.exceptions import UniqueViolationError
from core import (
    db,
    html,
    SITE,
    OWNER,
    security,
    json_encode,
    unzip_int_data,
    preview_options,
    telegram_clients,
    generate_sensitive_link,
    registration_date_by_id,
)

from aiogram import F
from aiogram.fsm.context import FSMContext
from telethon.tl.types.messages import ChatFull
from aiogram.filters import Command, CommandStart
from aiogram.types import KeyboardButton as KButton
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import ReplyKeyboardRemove as KRemove
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import InputChannel, InputPeerChat, InputPeerChannel
from aiogram.types import KeyboardButtonRequestChat, KeyboardButtonRequestUsers
from .core import (
    dp,
    bot,
    Data,
    UserState,
    new_message,
    new_callback_query,
    username_acquaintance,
)
from aiogram.types import (
    Message,
    WebAppInfo,
    CallbackQuery,
)


@dp.message(CommandStart())
@security('state')
async def _start(message: Message, state: FSMContext):
    if await new_message(message): return
    await state.clear()
    service_message = await message.answer("...", reply_markup=KRemove())
    if await db.fetch_one(f"SELECT true FROM accounts WHERE account_id={message.chat.id}", one_data=True):  # Зарегистрирован(а)
        markup = IMarkup(inline_keyboard=[[IButton(text="⚙️ Меню и настройки", callback_data="menu")]])
    else:
        markup = IMarkup(inline_keyboard=[[IButton(text="🚀 Запустить бота", callback_data="menu")]])
    acquaintance = await username_acquaintance(message.chat.id, message.from_user.first_name, 'first_name')
    start_message = await message.answer(f"Привет, {escape(acquaintance)} 👋\n"
                                         f"<a href='{SITE}'>Обзор всех функций</a> 👇",
                                         parse_mode=html, reply_markup=markup, link_preview_options=preview_options())
    params = message.text.replace("/start ", "").split()
    if message.text.startswith('/start r'):
        friend_id = unzip_int_data(message.text.replace('/start r', ''))
        if message.chat.id == friend_id:
            await message.answer("Вы не можете зарегистрироваться по своей реферальной ссылке!")
        elif not await db.fetch_one(f"SELECT true FROM accounts WHERE account_id={friend_id}", one_data=True):
            await message.answer("Реферальная ссылка не найдена!")
        elif await db.fetch_one(f"SELECT true FROM accounts WHERE account_id={message.chat.id}", one_data=True):
            await message.answer("Вы уже зарегистрированы и не можете использовать чьи-то реферальные ссылки")
        else:
            try:
                await db.execute(f"INSERT INTO referals VALUES ({friend_id}, {message.chat.id})")
            except UniqueViolationError:
                await db.execute(f"UPDATE referals SET account_id={friend_id} WHERE referal_id={message.chat.id}")
            await bot.send_message(friend_id, "По вашей реферальной ссылке зарегистрировался новый пользователь. Если он "
                                              "подключит бота, то вы получите месяц подписки в подарок")
            await bot.send_message(OWNER, f"Регистрация по реферальной ссылке #r{friend_id}")
    elif "menu" in params:
        await start_message.edit_text(**await menu(message.chat.id))
    await service_message.delete()


@dp.message(Command('menu'))
@security()
async def _menu(message: Message):
    if await new_message(message): return
    await message.answer(**await menu(message.chat.id))


@dp.callback_query(F.data == "menu")
@security()
async def _menu_button(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await menu(callback_query.message.chat.id))


async def menu(account_id: int) -> dict[str, Any]:
    status = await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True)  # Вкл/выкл Maksogram
    if status is None:
        markup = IMarkup(inline_keyboard=[[IButton(text="🟢 Включить Maksogram", callback_data="registration")],
                                          [IButton(text="🤖 Автоответчик", callback_data="answering_machinePrev"),
                                           IButton(text="👨‍🏫 Профиль друга", callback_data="changed_profilePrev")],
                                          [IButton(text="🌐 Друг в сети", callback_data="status_usersPrev"),
                                           IButton(text="👀 Призрак", callback_data="ghost_modePrev")],
                                          [IButton(text="⚙️ Настройки", callback_data="settingsPrev"),
                                           IButton(text="💬 Maksogram в чате", callback_data="modulesPrev")],  # IButton(text="🛡 Защита аккаунта", callback_data="security")
                                          [IButton(text="ℹ️ Памятка по функциям", url=await generate_sensitive_link(account_id))]])
    elif status is False:
        markup = IMarkup(inline_keyboard=[[IButton(text="🟢 Включить Maksogram", callback_data="on")],
                                          [IButton(text="⚙️ Настройки", callback_data="settings")],
                                          [IButton(text="ℹ️ Памятка по функциям", url=await generate_sensitive_link(account_id))]])
    else:
        markup = IMarkup(inline_keyboard=[[IButton(text="🔴 Выключить Maksogram", callback_data="off")],
                                          [IButton(text="🤖 Автоответчик", callback_data="answering_machine"),
                                           IButton(text="👨‍🏫 Профиль друга", callback_data="changed_profile")],
                                          [IButton(text="🌐 Друг в сети", callback_data="status_users"),
                                           IButton(text="👀 Призрак", callback_data="ghost_mode")],
                                          [IButton(text="⚙️ Настройки", callback_data="settings"),
                                           IButton(text="💬 Maksogram в чате", callback_data="modules")],  # IButton(text="🛡 Защита аккаунта", callback_data="security")
                                          [IButton(text="ℹ️ Памятка по функциям", url=await generate_sensitive_link(account_id))]])
    return {"text": "⚙️ Maksogram — меню ⚙️", "reply_markup": markup}


@dp.message(Command('settings'))
@security()
async def _settings(message: Message):
    if await new_message(message): return
    await message.answer(**await settings(message.chat.id))


@dp.callback_query(F.data == "settingsPrev")
@security()
async def _settings_prev(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.answer("Ваши настройки не найдены!", True)


@dp.callback_query(F.data == "settings")
@security()
async def _settings_button(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await settings(callback_query.from_user.id))


async def settings(account_id: int) -> dict[str, Any]:
    account_settings = await db.fetch_one(f"SELECT time_zone, city, gender FROM settings WHERE account_id={account_id}")
    time_zone = f"+{account_settings['time_zone']}" if account_settings['time_zone'] >= 0 else str(account_settings['time_zone'])
    city = account_settings['city']
    gender = {None: "не указан", True: "мужчина", False: "женщина"}[account_settings['gender']]  # Заранее извиняюсь :)
    reply_markup = IMarkup(inline_keyboard=[[IButton(text="👁 Профиль", callback_data="profile"),
                                             IButton(text="🕰 Часовой пояс", callback_data="time_zone")],
                                            [IButton(text="🌏 Город", callback_data="city"),
                                             IButton(text="🚹 🚺 Пол", callback_data="gender")],
                                            [IButton(text="🎁 Пригласить друга", callback_data="friends")],
                                            [IButton(text="⚙️ Сохранение сообщений", callback_data="saving_messages")],
                                            [IButton(text="◀️  Назад", callback_data="menu")]])
    return {"text": f"⚙️ Общие настройки Maksogram\nЧасовой пояс: {time_zone}:00\nГород: {city}\nПол: {gender}",
            "reply_markup": reply_markup}


@dp.callback_query(F.data == "saving_messages")
@security()
async def _saving_messages(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await saving_messages_menu(callback_query.from_user.id))


async def saving_messages_menu(account_id: int) -> dict[str, Any]:
    account_settings = await db.fetch_one(f"SELECT added_chats, removed_chats, saving_messages, notify_changes "
                                          f"FROM settings WHERE account_id={account_id}")
    if account_settings['saving_messages']:  # Сохранение сообщений включено
        indicator, command = ("🔴", "off") if account_settings['notify_changes'] else ("🟢", "on")
        markup = IMarkup(inline_keyboard=[[IButton(text="🔴 Выкл", callback_data="saving_messages_off"),
                                           IButton(text="Чаты работы", callback_data="chats")],
                                          [IButton(text=f"{indicator} Увед об изменении сообщений", callback_data=f"notify_changes_{command}")],
                                          [IButton(text="◀️  Назад", callback_data="settings")]])
    else:
        markup = IMarkup(inline_keyboard=[[IButton(text="🟢 Включить", callback_data="saving_messages_on")],
                                          [IButton(text="◀️  Назад", callback_data="settings")]])
    return {"text": "💬 Сохранение сообщений\n<blockquote expandable>⚠️ По умолчанию Maksogram работает только в личных чатах. "
                    "Можно добавить нужные группы и удалить ненужные лички\n\n• При выключении Сохранения сообщений остальные функции "
                    "смогут работать\n\n• Изменения сообщений можно посмотреть в канале Мои сообщения в комментариях "
                    "под нужным сообщением. Если вкл уведомления, то я буду также отдельно вас уведомлять</blockquote>",
            "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data.in_(["saving_messages_on", "saving_messages_off", "notify_changes_on", "notify_changes_off"]))
@security()
async def _saving_messages_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    function, command = callback_query.data.rsplit("_", 1)
    await db.execute(f"UPDATE settings SET {function}={'true' if command == 'on' else 'false'} WHERE account_id={account_id}")
    if function == "notify_changes" and command == "on":
        await callback_query.answer("Теперь каждое изменение сообщения будет уведомляться! Оно вам надо? :)", True)
    await callback_query.message.edit_text(**await saving_messages_menu(account_id))


@dp.callback_query(F.data == "chats")
@security()
async def _chats(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await chats_menu(callback_query.from_user.id))


async def chats_menu(account_id: int) -> dict[str, Any]:
    chats = await db.fetch_one(f"SELECT added_chats, removed_chats FROM settings WHERE account_id={account_id}")
    added_names = "\n".join([f"    • {name}" for name in chats['added_chats'].values()])
    removed_names = "\n".join([f"    • {name}" for name in chats['removed_chats'].values()])
    buttons = [IButton(text=f"🚫 {name}", callback_data=f"remove_added_chat_{chat_id}") for chat_id, name in chats['added_chats'].items()] + \
              [IButton(text=f"🚫 {name}", callback_data=f"remove_removed_chat_{chat_id}") for chat_id, name in chats['removed_chats'].items()]
    buttons = [([buttons[i], buttons[i+1]] if i+1 < len(buttons) else [buttons[i]]) for i in range(0, len(buttons), 2)]
    markup = IMarkup(inline_keyboard=[*buttons,
                                      [IButton(text="➕ Добавить", callback_data="add_chat"),
                                       IButton(text="➖ Удалить", callback_data="remove_chat")],
                                      [IButton(text="◀️  Назад", callback_data="saving_messages")]])
    return {"text": f"💬 Чаты работы Maksogram\n<b>По умолчанию только личные</b>\nДобавлены:\n{added_names}\nУдалены:\n{removed_names}",
            "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data == "add_chat")
@security('state')
async def _add_chat_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    if await db.fetch_one(f"SELECT COUNT(*) FROM jsonb_object_keys((SELECT added_chats FROM settings "
                          f"WHERE account_id={account_id}))", one_data=True) >= 3:
        if account_id != OWNER:
            return await callback_query.answer("Вы добавили максимальное кол-во чатов")
    await state.set_state(UserState.add_chat)
    request_chat = KeyboardButtonRequestChat(request_id=1, chat_is_channel=False, request_title=True)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_chat=request_chat)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте группу для работы Maksogram", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.add_chat)
@security('state')
async def _add_chat(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']
    await state.clear()
    if message.content_type == "chat_shared":
        chat_id, chat_name = message.chat_shared.chat_id, message.chat_shared.title
        telegram_client = telegram_clients[account_id]
        chat: Union[InputChannel, InputPeerChat] = await telegram_client.get_input_entity(chat_id)
        if isinstance(chat, (InputChannel, InputPeerChannel, InputPeerChat)):
            if isinstance(chat, (InputChannel, InputPeerChannel)):
                chat = InputChannel(chat.channel_id, chat.access_hash)
                full_chat: ChatFull = await telegram_client(GetFullChannelRequest(chat))
                count = full_chat.full_chat.participants_count
            else:  # InputPeerChat
                full_chat: ChatFull = await telegram_client(GetFullChatRequest(-chat_id))
                count = len(full_chat.full_chat.participants.participants)
            if count > 100:
                await message.answer("<b>Чат слишком большой!</b>", parse_mode=html)
            else:
                new_chat = json_encode({f"{chat_id}": chat_name})
                await db.execute(f"UPDATE settings SET added_chats=added_chats || '{new_chat}' WHERE account_id={account_id}")
        else:
            await message.answer("<b>Сожалеем. Чат не найден!</b>", parse_mode=html)
        await message.answer(**await chats_menu(account_id))
    else:
        await message.answer(**await chats_menu(account_id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data == "remove_chat")
@security('state')
async def _remove_chat_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.remove_chat)
    request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False, max_quantity=1)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request_users)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте личный чат, в котором не будет работать Maksogram", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.remove_chat)
@security('state')
async def _remove_chat(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']
    await state.clear()
    if message.content_type == "users_shared":
        user_id = message.users_shared.user_ids[0]
        user = await telegram_clients[account_id].get_entity(user_id)
        name = f"{user.first_name} {user.last_name or ''}".strip()
        new_chat = json_encode({f"{user_id}": name})
        await db.execute(f"UPDATE settings SET removed_chats=removed_chats || '{new_chat}' WHERE account_id={account_id}")
    await message.answer(**await chats_menu(account_id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data.startswith("remove_added_chat").__or__(F.data.startswith("remove_removed_chat")))
@security()
async def _remove_this_chat(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    field, chat_id = callback_query.data.replace("remove_", "").replace("chat", "chats").rsplit("_", 1)
    await db.execute(f"UPDATE settings SET {field}={field} - '{chat_id}' WHERE account_id={account_id}")
    await callback_query.message.edit_text(**await chats_menu(account_id))


@dp.callback_query(F.data == "gender")
@security()
async def _gender(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await gender_menu(callback_query.from_user.id))


async def gender_menu(account_id: int) -> dict[str, Any]:
    account_settings = await db.fetch_one(f"SELECT gender FROM settings WHERE account_id={account_id}")
    gender = {None: "не указан", True: "мужчина", False: "женщина"}[account_settings['gender']]  # Заранее извиняюсь :)
    reply_markup = IMarkup(inline_keyboard=[[IButton(text="🚹 Мужчина", callback_data="gender_edit__man")],
                                            [IButton(text="🚺 Женщина", callback_data="gender_edit_woman")],
                                            [IButton(text="◀️  Назад", callback_data="settings")]])
    return {"text": f"Вы можете выбрать пол. Он нужен для красивых поздравлений\nПол: {gender}", "reply_markup": reply_markup}


@dp.callback_query(F.data.startswith("gender_edit"))
@security()
async def _gender_edit(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    gender = "true" if callback_query.data.split("_")[-1] == "man" else "false"
    account_id = callback_query.from_user.id
    await db.execute(f"UPDATE settings SET gender={gender} WHERE account_id={account_id}")
    await callback_query.message.edit_text(**await settings(account_id))


@dp.callback_query(F.data == "profile")
@security()
async def _profile_button(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await profile_menu(callback_query.from_user.id))


async def profile_menu(account_id: int) -> dict[str, Any]:
    reply_markup = IMarkup(inline_keyboard=[[IButton(text="◀️  Назад", callback_data="settings")]])
    account = await db.fetch_one(f"SELECT name, registration_date FROM accounts WHERE account_id={account_id}")
    subscription = await db.fetch_one(f"SELECT \"user\", fee, next_payment FROM payment WHERE account_id={account_id}")
    account['registration_date'] = account['registration_date'].strftime("%Y-%m-%d %H:%M")
    subscription['next_payment'] = subscription['next_payment'].strftime("%Y-%m-%d 20:00")  # Время перезапуска
    my_referal = await db.fetch_one(f"SELECT account_id FROM referals WHERE referal_id={account_id}", one_data=True)
    if my_referal:
        my_referal = f'<a href="tg://user?id={my_referal}">{my_referal}</a>'
    else:
        gender = await db.fetch_one(f"SELECT gender FROM settings WHERE account_id={account_id}", one_data=True)
        if gender is True:  # мужчина
            my_referal = '<span class="tg-spoiler">сам пришел 🤓</span>'
        elif gender is False:  # женщина
            my_referal = '<span class="tg-spoiler">сама пришла 🤓</span>'
        else:
            my_referal = '<span class="tg-spoiler">сам(а) пришел(ла) 🤓</span>'
    if subscription['user'] == 'admin':
        subscription['next_payment'] = "конца жизни 😎"
        subscription['fee'] = "бесплатно"
    count = await db.fetch_one(f"SELECT MAX(message_id) AS m, COUNT(*) AS sm FROM zz{account_id}")
    return {"text": f"👁 <b>Профиль</b>\nID: {account_id} (аккаунт ≈{registration_date_by_id(account_id)} года)\n"
                    f"Регистрация: {account['registration_date']}\nСообщений в личках: {count['m']}\nСохранено: {count['sm']}\n"
                    f"Меня пригласил: {my_referal}\nПодписка до {subscription['next_payment']}\nСтоимость: {subscription['fee']}",
            "parse_mode": html, "reply_markup": reply_markup}


@dp.callback_query(F.data == "city")
@security('state')
async def _city_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.city)
    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте название вашего города", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.city)
@security('state')
async def _city(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    account_id = message.chat.id
    if message.text != "Отмена":
        if not await check_city(message.text.lower()):
            markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
            await state.update_data(message_id=(await message.answer("Город не найден...", reply_markup=markup)).message_id)
        else:
            await state.clear()
            await db.execute(f"UPDATE settings SET city=$1 WHERE account_id={account_id}", message.text)
            await message.answer(**await settings(account_id))
    else:
        await state.clear()
        await message.answer(**await settings(account_id))
    await bot.delete_messages(account_id, [message_id, message.message_id])


@dp.callback_query(F.data == "time_zone")
@security('state')
async def _time_zone_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.time_zone)
    button = KButton(text="Выбрать часовой пояс", web_app=WebAppInfo(url=f"{Data.web_app}/time_zone"))
    back_button = KButton(text="Отмена")
    message_id = (await callback_query.message.answer(
        "Нажмите на кнопку, чтобы выбрать часовой пояс", reply_markup=KMarkup(keyboard=[[button], [back_button]],
                                                                              resize_keyboard=True))).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.time_zone)
@security('state')
async def _time_zone(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    account_id = message.chat.id
    if message.content_type == "web_app_data":
        time_zone = int(message.web_app_data.data)
        await db.execute(f"UPDATE settings SET time_zone={time_zone} WHERE account_id={account_id}")
    await message.answer(**await settings(account_id))
    await bot.delete_messages(message.chat.id, [message_id, message.message_id])


def menu_initial():
    pass  # Чтобы PyCharm не ругался
