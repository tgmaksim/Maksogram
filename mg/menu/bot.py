from mg.config import SITE, OWNER, WEB_APP

from typing import Any
from html import escape

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, CommandStart
from mg.bot.types import dp, bot, CallbackData, UserState, support_link
from aiogram.types import Message, CallbackQuery, WebAppInfo, KeyboardButtonRequestChat, KeyboardButtonRequestUsers
from . functions import (
    add_chat,
    set_city,
    set_gender,
    delete_chat,
    remove_chat,
    set_time_zone,
    count_messages,
    update_referral,
    set_notify_changes,
    set_saving_messages,
    get_registration_date,
    check_count_added_chats,
    get_registration_date_by_id,
)
from mg.bot.functions import (
    new_message,
    get_referral,
    request_user,
    request_chat,
    preview_options,
    get_subscription,
    new_callback_query,
    generate_sensitive_link,
)

from telethon.tl.types import Channel
from telethon.utils import get_peer_id
from telethon.tl.types.messages import ChatFull
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.tl.functions.channels import GetFullChannelRequest

from aiogram.types import KeyboardButton as KButton
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import ReplyKeyboardRemove as KRemove
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton

from mg.modules.weather import check_city
from mg.client.types import maksogram_clients
from mg.core.yoomoney import check_payment, delete_payment
from mg.core.functions import unzip_int_data, error_notify, get_account_status, get_settings, full_name, renew_subscription


cb = CallbackData()
MAX_COUNT_PARTICIPANTS = 50


@dp.message(CommandStart())
@error_notify('state')
async def _start(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    await state.clear()

    service_message = await message.answer(".", reply_markup=KRemove())

    if await get_account_status(account_id):
        markup = IMarkup(inline_keyboard=[[IButton(text="⚙️ Меню и настройки", callback_data=cb('menu'))]])
    else:
        markup = IMarkup(inline_keyboard=[[IButton(text="🚀 Запустить бота", callback_data=cb('menu'))]])
    hello_message = await message.answer(f"Привет, {escape(message.from_user.first_name)} 👋\n"
                                         f"<a href='{SITE}'>Обзор функций Maksogram</a> 👇", reply_markup=markup, link_preview_options=preview_options())

    params = message.text.removeprefix('/start ').split()
    if len(params) == 1 and params[0].startswith('r'):
        friend_id = unzip_int_data(params[0].removeprefix('r'))  # Клиент, который пригласил нового пользователя по своей реферальной ссылке

        if account_id == friend_id:
            await message.answer("Вы не можете зарегистрироваться по своей реферальной ссылке")
        elif await get_account_status(friend_id) is None:  # Владелец реферальной ссылки не найден
            await message.answer("Реферальная ссылка не найдена")
        elif await get_account_status(account_id):  # Клиент уже зарегистрировался, поэтому не может использовать реферальные ссылки
            await message.answer("Вы уже зарегистрировались, поэтому не можете использовать чью-либо реферальную ссылку")
        else:
            await update_referral(friend_id, account_id)

            await bot.send_message(friend_id, "По вашей реферальной ссылке зашел новый пользователь. "
                                              "Когда он запустит Maksogram, придет подарок в виде месяца подписки")
            await bot.send_message(OWNER, f"Регистрация по реферальной ссылке #r{friend_id}")
    elif len(params) == 1 and params[0].startswith('p'):
        subscription_id = unzip_int_data(params[0].removeprefix('p'))
        subscription = await get_subscription(subscription_id)

        if (status := await check_payment(account_id)) == 'succeeded':
            await delete_payment(account_id)
            await renew_subscription(account_id, subscription.duration)

            await hello_message.edit_text(f"🌟 <b>Maksogram Premium</b>\n"
                                          f"Спасибо за проведенную оплату: Maksogram Premium продлен на {subscription.about.lower()}")
            await bot.send_message(OWNER, f"Пользовать отправил оплату. Подписка продлена на {subscription.about.lower()}")

        elif status == 'canceled':
            await delete_payment(account_id)

            await hello_message.edit_text("🌟 <b>Maksogram Premium</b>\nТранзакция была прервана или ее время истекло\n")
            await bot.send_message(OWNER, f"Пользователь {account_id} попытался подтвердить платеж, но его статус {status}")

        elif status == 'pending':
            await hello_message.edit_text("🌟 <b>Maksogram Premium</b>\nЗавершите оплату, чтобы получить Maksogram Premium")
            await bot.send_message(OWNER, "Платеж находится в состоянии ожидания оплаты от пользователя")

        elif status is None:
            await hello_message.edit_text(f"Данные о платеже отсутствуют, напишите {support_link}")
            await bot.send_message(OWNER, "Данные о платеже не найдены...")

        else:
            await bot.send_message(OWNER, f"Неизвестный статус платежа: {status}")

    elif 'menu' in params:
        await hello_message.edit_text(**await menu(account_id))

    await service_message.delete()


@dp.message(Command('menu'))
@error_notify()
async def _menu(message: Message):
    if await new_message(message): return
    service_message = await message.answer(".", reply_markup=KRemove())
    await message.answer(**await menu(message.chat.id))
    await service_message.delete()


@dp.callback_query(F.data.startswith(cb('menu')))
@error_notify()
async def _menu_button(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    new = cb.deserialize(callback_query.data).get(0) == 'new'
    if new:
        await callback_query.message.answer(**await menu(callback_query.from_user.id))
        await callback_query.message.delete()
    else:
        await callback_query.message.edit_text(**await menu(callback_query.from_user.id))


async def menu(account_id: int) -> dict[str, Any]:
    status = await get_account_status(account_id)
    prev = status is None
    main_button_text = "🟢 Maksogram" if status else "🔴 Maksogram"
    button_command = 'registration' if status is None else 'off'

    if status is False:
        markup = IMarkup(inline_keyboard=[[IButton(text=main_button_text, callback_data=cb('on')),
                                           IButton(text="⚙️ Настройки", callback_data=cb('settings'))],
                                          [IButton(text="ℹ️ Памятка по функциям", url=await generate_sensitive_link(account_id))]])
    else:
        markup = IMarkup(inline_keyboard=[[IButton(text=main_button_text, callback_data=cb(button_command)),
                                           IButton(text="⚙️ Настройки", callback_data=cb('settings', prev))],
                                          [IButton(text="🤖 Автоответчик", callback_data=cb('answering_machine', prev)),
                                           IButton(text="👨‍🏫 Профиль друга", callback_data=cb('changed_profile', prev))],
                                          [IButton(text="🌐 Друг в сети", callback_data=cb('status_users', prev)),
                                           IButton(text="👀 Призрак", callback_data=cb('ghost_mode', prev))],
                                          [IButton(text="🪧 Быстрые ответы", callback_data=cb('speed_answers', prev)),
                                           IButton(text="🛡 Защита аккаунта", callback_data=cb('security', prev))],
                                          [IButton(text="🔥 Огонек", callback_data=cb('fire', prev)),
                                           IButton(text="💬 Maksogram в чате", callback_data=cb('modules', prev))],
                                          [IButton(text="🌟 Maksogram Premium", callback_data=cb('premium', prev))]])

    return dict(text="⚙️ Maksogram — меню ⚙️", reply_markup=markup)


@dp.message(Command('settings'))
@error_notify()
async def _settings(message: Message):
    if await new_message(message): return
    account_id = message.chat.id
    status  = await get_account_status(account_id)
    if status is None:
        await message.answer("Настройки не найдены!")
        return

    await message.answer(**await settings_menu(account_id))


@dp.callback_query(F.data.startswith(cb.command('settings')))
@error_notify()
async def _settings_button(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    prev = cb.deserialize(callback_query.data).get(0) is True
    if prev:
        await callback_query.answer("Настройки не найдены!", True)
        return

    await callback_query.message.edit_text(**await settings_menu(callback_query.from_user.id))


async def settings_menu(account_id: int) -> dict[str, Any]:
    settings = await get_settings(account_id)

    markup = IMarkup(inline_keyboard=[[
        IButton(text="👁 Профиль", callback_data=cb('profile')), IButton(text="🕰 Часовой пояс", callback_data=cb('time_zone'))],
        [IButton(text="🌏 Город", callback_data=cb('city')), IButton(text="🚹 🚺 Пол", callback_data=cb('gender'))],
        [IButton(text="🎁 Пригласить друга", callback_data=cb('friends'))],
        [IButton(text="⚙️ Сохранение сообщений", callback_data=cb('saving_messages'))],
        [IButton(text="◀️  Назад", callback_data=cb('menu'))]])

    return dict(text=f"⚙️ Общие настройки Maksogram\nЧасовой пояс: {settings.str_time_zone}:00\nГород: {settings.city}\n"
                     f"Пол: {settings.str_gender or 'не указан'}", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('profile')))
@error_notify()
async def _profile(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await profile_menu(callback_query.from_user.id))


async def profile_menu(account_id: int) -> dict[str, Any]:
    telegram_registration_date = get_registration_date_by_id(account_id)
    maksogram_registration_date = (await get_registration_date(account_id)).strftime('%Y-%m-%d %H:%M')
    messages, saved_messages = await count_messages(account_id)

    referral = await get_referral(account_id)
    if referral:
        referral = f'<a href="tg://openmessage?user_id={referral}">{referral}</a>'
    else:
        referral = '<span class="tg-spoiler">сам пришел 🤓</span>'

    markup = IMarkup(inline_keyboard=[[IButton(text="◀️  Назад", callback_data=cb('settings'))]])
    return dict(
        text=f"👁 <b>Профиль пользователя</b>\nID: {account_id} (аккаунт ≈{telegram_registration_date})\n\nРегистрация: {maksogram_registration_date}\n"
             f"Сообщений в личках: {messages}\nСохранено: {saved_messages}\n\nМеня пригласил: {referral}\n", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('city')))
@error_notify('state')
async def _city_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.city)

    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте название города, чтобы правильно работала погода", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.city)
@error_notify('state')
async def _city(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']

    if message.text != "Отмена":
        if await check_city(message.text):
            await state.clear()
            await set_city(account_id, message.text)
            await message.answer(**await settings_menu(account_id))
        else:
            markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
            new_message_id = (await message.answer("Город не найден", reply_markup=markup)).message_id
            await state.update_data(message_id=new_message_id)
    else:
        await state.clear()
        await message.answer(**await settings_menu(account_id))

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data.startswith(cb.command('time_zone')))
@error_notify('state')
async def _time_zone_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.time_zone)

    markup = KMarkup(keyboard=[[KButton(text="Выбрать часовой пояс", web_app=WebAppInfo(url=f"{WEB_APP}/time_zone"))],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Выберите часовой пояс, чтобы правильно работали некоторые функции", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.time_zone)
@error_notify('state')
async def _time_zone(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']
    await state.clear()

    if message.web_app_data:
        time_zone = int(message.web_app_data.data)
        await set_time_zone(account_id, time_zone)

    await message.answer(**await settings_menu(account_id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data.startswith(cb.command('gender')))
@error_notify()
async def _gender(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    markup = IMarkup(inline_keyboard=[[IButton(text="🚹 Мужчина", callback_data=cb('gender_edit', True))],
                                      [IButton(text="🚺 Женщина", callback_data=cb('gender_edit', False))],
                                      [IButton(text="◀️  Назад", callback_data=cb('settings'))]])
    await callback_query.message.edit_text("Вы можете выбрать пол. Он нужен для красивых поздравлений и некоторых мелочей", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('gender_edit')))
@error_notify()
async def _gender_edit(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id

    gender = cb.deserialize(callback_query.data)[0]
    await set_gender(account_id, gender)
    await callback_query.message.edit_text(**await settings_menu(account_id))


@dp.callback_query(F.data.startswith(cb.command('saving_messages')))
@error_notify()
async def _saving_messages(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    if cb.deserialize(callback_query.data).get(0) == "new":
        await callback_query.message.edit_reply_markup()
        await callback_query.message.answer(**await saving_message_menu(callback_query.from_user.id))
    else:
        await callback_query.message.edit_text(**await saving_message_menu(callback_query.from_user.id))


async def saving_message_menu(account_id: int) -> dict[str, Any]:
    settings = await get_settings(account_id)

    if settings.saving_messages:  # Сохранение сообщений включено
        ind = "🟢" if settings.notify_changes else "🔴"
        markup = IMarkup(inline_keyboard=
                         [[IButton(text="🟢 Сохр сообщ", callback_data=cb('saving_messages_switch', False)),
                           IButton(text="Рабочие чаты", callback_data=cb('chats'))],
                          [IButton(text=f"{ind} Увед об изменении сообщений",
                                   callback_data=cb('notify_changes_switch', not settings.notify_changes))],
                          [IButton(text="◀️  Назад", callback_data=cb('settings'))]])
    else:
        markup = IMarkup(inline_keyboard=[[IButton(text="🔴 Сохранение сообщений", callback_data=cb('saving_messages_switch', True))],
                                          [IButton(text="◀️  Назад", callback_data=cb('settings'))]])

    return dict(
        text="💬 Сохранение сообщений\n<blockquote expandable>⚠️ По умолчанию Maksogram работает только в личных чатах. Можно добавить в рабочие чаты "
             "нужные группы и удалить ненужные личные чаты\n\n• При выключении Сохранения сообщений остальные функции, в том числе Maksogram в чате, "
             "смогут работать\n\n• Изменения сообщений можно посмотреть в канале Мои сообщения в комментариях под нужным сообщением. "
             "Если включить уведомления, то <b>каждое изменение</b> будет приходить отдельным уведомлением</blockquote>", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('saving_messages_switch')))
@error_notify()
async def _saving_messages_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    command = cb.deserialize(callback_query.data)[0]

    await set_saving_messages(account_id, command)
    await callback_query.message.edit_text(**await saving_message_menu(account_id))


@dp.callback_query(F.data.startswith(cb.command('notify_changes_switch')))
@error_notify()
async def _notify_changes_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    command = cb.deserialize(callback_query.data)[0]

    await set_notify_changes(account_id, command)
    await callback_query.message.edit_text(**await saving_message_menu(account_id))


@dp.callback_query(F.data.startswith(cb.command('chats')))
@error_notify()
async def _chats(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await chats_menu(callback_query.from_user.id))


async def chats_menu(account_id: int, text: str = None) -> dict[str, Any]:
    settings = await get_settings(account_id)
    added_chat_ids = list(settings.added_chats)
    removed_chat_ids = list(settings.removed_chats)

    added_chat_names = '\n'.join([f"    • {name}" for name in settings.added_chats.values()]) or '    только личные'
    removed_chat_names = '\n'.join([f"    • {name}" for name in settings.removed_chats.values()]) or '    отсутствуют'
    buttons = []

    for i in range(max(len(added_chat_ids), len(removed_chat_ids))):
        row = []
        if len(added_chat_ids) > i:
            added_chat_name = settings.added_chats[added_chat_ids[i]]
            row.append(IButton(text=f"🚫 {added_chat_name}", callback_data=cb('del_chat', 'added', added_chat_ids[i])))
        else:
            row.append(IButton(text=" ", callback_data='none'))

        if len(removed_chat_ids) > i:
            removed_chat_name = settings.removed_chats[removed_chat_ids[i]]
            row.append(IButton(text=f"🚫 {removed_chat_name}", callback_data=cb('del_chat', 'removed', removed_chat_ids[i])))
        else:
            row.append(IButton(text=" ", callback_data='none'))

        buttons.append(row)

    markup = IMarkup(inline_keyboard=[*buttons,
                                      [IButton(text="➕ Добавить", callback_data=cb('add_chat')),
                                       IButton(text="➖ Удалить", callback_data=cb('remove_chat'))],
                                      [IButton(text="◀️  Назад", callback_data=cb('saving_messages'))]])
    return dict(
        text=text or "💬 Рабочие чаты Maksogram\n<blockquote>⚠️ По умолчанию Maksogram работает только в личных чатах. Можно "
                     "добавить в рабочие чаты нужные группы и удалить ненужные личные чаты</blockquote>\n"
                     f"Добавлены:\n{added_chat_names}\nУдалены:\n{removed_chat_names}", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('add_chat')))
@error_notify('state')
async def _add_chat_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    if not await check_count_added_chats(account_id):
        await callback_query.answer("Количество добавленных рабочих чатов достигло максимума", True)
        return

    await state.set_state(UserState.add_chat)

    request = KeyboardButtonRequestChat(request_id=1, chat_is_channel=False)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_chat=request)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте группу для добавления в рабочие чаты Maksogram", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.add_chat)
@error_notify('state')
async def _add_chat(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']

    request = KeyboardButtonRequestChat(request_id=1, chat_is_channel=False)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_chat=request)],
                               [KButton(text="Отмена")]], resize_keyboard=True)

    if message.text == "Отмена":
        await state.clear()
        await message.answer(**await chats_menu(account_id))
    else:
        response = await request_chat(message)

        if not response.ok:
            new_message_id = (await message.answer(response.warning, reply_markup=markup)).message_id
            await state.update_data(message_id=new_message_id)
        else:
            await state.clear()

            # chat_id - полный идентификатор чата (-id) или супергруппы (-100id)
            chat_id = get_peer_id(response.chat, add_mark=True)
            maksogram_client = maksogram_clients[account_id]
            telegram_client = maksogram_client.client

            if isinstance(response.chat, Channel):  # Канал или супергруппа
                full_chat: ChatFull = await telegram_client(GetFullChannelRequest(response.chat.id))
                count = full_chat.full_chat.participants_count
            else:  # Chat (обычная группа)
                full_chat: ChatFull = await telegram_client(GetFullChatRequest(response.chat.id))
                count = len(full_chat.full_chat.participants.participants)

            if chat_id in (maksogram_client.my_messages, maksogram_client.message_changes):
                new_message_id = (await message.answer("<b>Нельзя добавить этот чат!!!</b>", reply_markup=markup)).message_id
                await state.update_data(message_id=new_message_id)
            elif count > MAX_COUNT_PARTICIPANTS:
                new_message_id = (await message.answer("Чат слишком большой!", reply_markup=markup)).message_id
                await state.update_data(message_id=new_message_id)
            else:
                await add_chat(account_id, chat_id, response.chat.title)  # Также полный идентификатор чата или супергруппы
                await message.answer(**await chats_menu(account_id))

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data.startswith(cb.command('remove_chat')))
@error_notify('state')
async def _remove_chat_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.remove_chat)

    request = KeyboardButtonRequestUsers(request_id=2, user_is_bot=False, max_quantity=1)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте личный чат для удаления из рабочих чатов Maksogram", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.remove_chat)
@error_notify('state')
async def _remove_chat(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']

    if message.text == "Отмена":
        await state.clear()
        await message.answer(**await chats_menu(account_id))
    else:
        response = await request_user(message)

        if not response.ok:
            request = KeyboardButtonRequestUsers(request_id=2, user_is_bot=False, max_quantity=1)
            markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request)],
                                       [KButton(text="Отмена")]], resize_keyboard=True)
            new_message_id = (await message.answer(response.warning, reply_markup=markup)).message_id
            await state.update_data(message_id=new_message_id)
        else:
            await state.clear()
            await remove_chat(account_id, response.user.id, full_name(response.user))

            await message.answer(**await chats_menu(account_id))

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data.startswith(cb.command('del_chat')))
@error_notify()
async def _del_chat(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    type_chat, chat_id = cb.deserialize(callback_query.data)

    await delete_chat(account_id, type_chat, chat_id)
    await callback_query.message.edit_text(**await chats_menu(account_id))


def menu_initial():
    pass  # Чтобы PyCharm не ругался
