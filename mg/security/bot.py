import random

from mg.config import OWNER

from aiogram import F

from aiogram.fsm.context import FSMContext
from mg.bot.functions import new_callback_query, new_message, request_user
from aiogram.types import CallbackQuery, Message, KeyboardButtonRequestUsers
from mg.bot.types import dp, bot, CallbackData, UserState, support_link, support

from mg.client.types import maksogram_clients
from mg.client.functions import get_is_started
from telethon.errors.rpcerrorlist import HashInvalidError
from telethon.tl.functions.account import ResetAuthorizationRequest

from aiogram.types import KeyboardButton as KButton
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton

from typing import Any
from mg.core.functions import error_notify, send_email_message, format_error, full_name

from . functions import (
    get_security_settings,
    get_security_agents,
    set_recovery,
    update_email,
    is_security_agent,
    check_valid_email,
    check_count_agents,
    add_security_agent,
    get_security_agent,
    delete_security_agent,
    set_security_function,
)

cb = CallbackData()

email_message = ("Ваш код: {code}. Его можно использовать, чтобы подтвердить адрес электронной почты и включить защиту аккаунта в Telegram.\n"
                 "Если Вы не запрашивали это сообщение, проигнорируйте его.\n"
                 "С уважением,\n"
                 "Команда Maksogram\n")


@dp.callback_query(F.data.startswith(cb.command('security')))
@error_notify()
async def _security(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    prev = cb.deserialize(callback_query.data).get(0) is True
    await callback_query.message.edit_text(**await security_menu(callback_query.from_user.id, prev=prev))


async def security_menu(account_id: int, prev: bool = False) -> dict[str, Any]:
    buttons = []

    if await is_security_agent(account_id):
        buttons.append([IButton(text="🌐 Восстановить доступ", callback_data=cb('security_agent', prev))])

    markup = IMarkup(inline_keyboard=[[IButton(text="💀 Защита от взлома", callback_data=cb('security_hack', prev))],
                                      [IButton(text="📵 Защита от потери телефона", callback_data=cb('security_no_access', prev))],
                                      [IButton(text="⚙️ Настройки функции", callback_data=cb('security_settings', prev))],
                                      *buttons,
                                      [IButton(text="◀️  Назад", callback_data=cb('menu'))]])

    return dict(
        text="🛡 <b>Защита аккаунта</b>\nДанная функция поможет защитить аккаунт от взлома, а также помочь "
             "восстановить доступ, если вы потеряете телефон", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('security_settings')))
@error_notify()
async def _security_settings(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    prev = cb.deserialize(callback_query.data).get(0) is True
    if prev:
        await callback_query.answer("Настройки не найдены!", True)
        return

    await callback_query.message.edit_text(**await security_settings(callback_query.from_user.id))


async def security_settings(account_id: int) -> dict[str, Any]:
    settings = await get_security_settings(account_id)

    agents = '\n'.join([f"    • <a href='tg://openmessage?user_id={agent.id}'>{agent.name}</a>" for agent in settings.agents]) or '    отсутствуют'
    markup = IMarkup(inline_keyboard=[[IButton(text=f"📨 {'Добавить' if not settings.email else 'Изменить'} почту", callback_data=cb('security_email'))],
                                      [IButton(text="🫡 Доверенные лица", callback_data=cb('security_agents'))],
                                      [IButton(text="◀️  Назад", callback_data=cb('security'))]])

    return dict(
        text=f"⚙️ <b>Настройки защиты аккаунта</b>\nПочта: {settings.email or 'отсутствует'}\nДоверенные лица:\n{agents}", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('security_email')))
@error_notify('state')
async def _security_email_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.security_email)

    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте свою почту для подтверждения", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.security_email)
@error_notify('state')
async def _security_email(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']

    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)

    if message.text == "Отмена":
        await state.clear()
        await message.answer(**await security_menu(account_id))
    else:
        if check_valid_email(message.text, message.entities):
            code = str(random.randint(100000, 999999))
            try:
                await send_email_message(message.text, "Подтверждение почты", email_message.format(code=code))
            except Exception as e:
                await bot.send_message(OWNER, format_error(e))

                new_message_id = (await message.answer("Произошла ошибка при отправке проверочного кода, возможно, указана неверная почта",
                                                       reply_markup=markup)).message_id
            else:
                await state.set_state(UserState.confirm_email)
                await state.update_data(email=message.text, code=code)
                new_message_id = (await message.answer("Проверьте почту и отправьте проверочный код из сообщения", reply_markup=markup)).message_id
        else:
            new_message_id = (await message.answer("Почта введена неверно, попробуйте еще раз", reply_markup=markup)).message_id

        await state.update_data(message_id=new_message_id)

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.message(UserState.confirm_email)
@error_notify('state')
async def _confirm_email(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    data = await state.get_data()
    message_id = data['message_id']
    email = data['email']
    code = data['code']

    if message.text == "Отмена":
        await state.clear()
        await message.answer(**await security_settings(account_id))
    elif message.text == code:
        await state.clear()
        await update_email(account_id, email)
        await message.answer(**await security_settings(account_id))
    else:
        markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
        new_message_id = (await message.answer("Проверочный код неверный", reply_markup=markup)).message_id
        await state.update_data(message_id=new_message_id)

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data.startswith(cb.command('security_agents')))
@error_notify()
async def _security_agents(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await security_agents_menu(callback_query.from_user.id))


async def security_agents_menu(account_id: int) -> dict[str, Any]:
    agents = await get_security_agents(account_id)

    i, buttons = 0, []
    while i < len(agents):  # Если длина имен достаточно короткая, то помещаем 2 в ряд, иначе 1
        if i + 1 < len(agents) and len(agents[i].name) <= 15 and len(agents[i+1].name) <= 15:
            buttons.append([IButton(text=f"🚫 {agents[i].name}", callback_data=cb('del_security_agent', agents[i].id)),
                            IButton(text=f"🚫 {agents[i+1].name}", callback_data=cb('del_security_agent', agents[i+1].id))])
            i += 1
        else:
            buttons.append([IButton(text=f"🚫 {agents[i].name}", callback_data=cb('del_security_agent', agents[i].id))])
        i += 1
    buttons.append([IButton(text="➕ Пригласить", callback_data=cb('new_security_agent'))])
    buttons.append([IButton(text="◀️  Назад", callback_data=cb('security_settings'))])

    return dict(
        text="🫡 <b>Доверенные лица</b>\nЗдесь вы можете удалить доверенное лицо или пригласить его", reply_markup=IMarkup(inline_keyboard=buttons))


@dp.callback_query(F.data.startswith(cb.command('new_security_agent')))
@error_notify('state')
async def _new_security_agent_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id

    if not await check_count_agents(account_id):
        await callback_query.answer("Количество доверенных лиц достигло максимума", True)
        return

    await state.set_state(UserState.new_security_agent)

    request = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте пользователя, которому вы доверяете, кнопкой, ID, username или "
                                                      "номер телефона", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.new_security_agent)
@error_notify('state')
async def _new_security_agent(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']

    request = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False, max_quantity=1)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request)],
                               [KButton(text="Отмена")]], resize_keyboard=True)

    if message.text == "Отмена":
        await state.clear()
        await message.answer(**await security_agents_menu(account_id))
    else:
        response = await request_user(message, can_yourself=False)

        if not response.ok:
            new_message_id = (await message.answer(response.warning, reply_markup=markup)).message_id
            await state.update_data(message_id=new_message_id)
        else:
            user_id = response.user.id
            if not await add_security_agent(account_id, user_id, full_name(response.user)):  # Пользовать уже является чьим-то доверенным лицом
                new_message_id = (await message.answer("Пользовать уже является чьим-то доверенным лицом")).message_id
                await state.update_data(message_id=new_message_id)
            else:
                await state.clear()
                await message.answer(**await security_agents_menu(account_id))

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data.startswith(cb.command('del_security_agent')))
@error_notify()
async def _del_security_agent(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    agent_id = cb.deserialize(callback_query.data)[0]

    await delete_security_agent(account_id, agent_id)
    await callback_query.message.edit_text(**await security_agents_menu(account_id))


@dp.callback_query(F.data.startswith(cb.command('security_hack')))
@error_notify()
async def _security_hack(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    prev = cb.deserialize(callback_query.data)[0] is True
    await callback_query.message.edit_text(**await security_hack(callback_query.from_user.id, prev=prev))


async def security_hack(account_id: int, prev: bool = False) -> dict[str, Any]:
    settings = None if prev else await get_security_settings(account_id)

    if settings is None or not settings.security_hack:
        markup = IMarkup(inline_keyboard=[[IButton(text="🔴 Включить защиту",
                                                   callback_data=cb('security_switch', 'hack', True, prev))],
                                          [IButton(text="◀️  Назад", callback_data=cb('security', prev))]])
    else:
        markup = IMarkup(inline_keyboard=[[IButton(text="🟢 Выключить защиту",
                                                   callback_data=cb('security_switch', 'hack', False, prev))],
                                          [IButton(text="◀️  Назад", callback_data=cb('security', prev))]])

    return dict(
        text="💀 <b>Защита от взлома</b>\n"
             "<blockquote expandable>🧐 <b>Когда пригодится?</b>\n"
             "    • Напрямую Telegram-аккаунт взломать невозможно\n"
             "    • Некоторые сервисы требуют официальный и безопасный вход, но некоторые получают полный доступ к аккаунту\n"
             "💪 <b>Как осуществляется защита?</b>\n"
             "    • При обнаружении нового входа Maksogram отправит уведомление об опасности такого действия\n"
             "    • Только вход вами через официальное приложение является безопасным\n"
             "⚠️ Таким образом Maksogram всегда предупредит о нежелательном входе и обезопасит от получения полного доступа мошенниками</blockquote>",
        reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('security_no_access')))
@error_notify()
async def _security_no_access(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    prev = cb.deserialize(callback_query.data)[0] is True
    await callback_query.message.edit_text(**await security_no_access(callback_query.from_user.id, prev=prev))


async def security_no_access(account_id: int, prev: bool = False):
    settings = None if prev else await get_security_settings(account_id)

    if settings is None or not settings.security_no_access:
        markup = IMarkup(inline_keyboard=[[IButton(text="🔴 Включить защиту",
                                                   callback_data=cb('security_switch', 'no_access', True, prev))],
                                          [IButton(text="◀️  Назад", callback_data=cb('security', prev))]])
    else:
        markup = IMarkup(inline_keyboard=[[IButton(text="🟢 Выключить защиту",
                                                   callback_data=cb('security_switch', 'no_access', False, prev))],
                                          [IButton(text="◀️  Назад", callback_data=cb('security', prev))]])

    return dict(
        text="📵 <b>Защита от потери доступа</b>\n"
             "<blockquote expandable>🧐 <b>Когда пригодится?</b>\n"
             "    • Вы потеряли доступ к аккаунту (нет доступа к телефону или другое)\n"
             "😔 <b>Что делать тогда?</b>\n"
             "    • Попросите доверенное лицо запустить <b>@MaksogramBot</b>\n"
             "    • Выберите режим восстановления доступа в меню. Если такой кнопки нет, значит пользователь не является доверенным лицом\n"
             "    • Попытайтесь войти в аккаунт на своем новом устройстве (новый телефон или ноутбук). <b>Код для входа придет вашему "
             "доверенному лицу в чате с ботом</b>\n"
             "⚠️ <b>Предупреждение!</b>\n"
             "    • Пока включена Защита от потери доступа и пользователь в списке доверенных лиц, доверенное лицо сможет в любой момент "
             "получить доступ к вашему аккаунту! Вы узнаете об этом, но все равно Будьте осторожны!</blockquote>",
        reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('security_switch')))
@error_notify()
async def _security_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    function, command, prev = cb.deserialize(callback_query.data)
    if prev:
        await callback_query.answer("Чтобы пользоваться Защитой аккаунта, необходимо включить Maksogram", True)
        return

    if function == "no_access" and command:
        settings = await get_security_settings(account_id)
        if not settings.agents:
            await callback_query.answer("Для работы необходимо добавить доверенных лиц (в настройках функции) и почту (по желанию)", True)

    await set_security_function(account_id, function, command)
    menu = security_hack if function == "hack" else security_no_access
    await callback_query.message.edit_text(**await menu(account_id))


@dp.callback_query(F.data.startswith(cb.command('security_agent')))
@error_notify()
async def _security_agent(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    prev = cb.deserialize(callback_query.data)[0] is True
    await callback_query.message.edit_text(**await security_agent_menu(callback_query.from_user.id, prev=prev))


async def security_agent_menu(agent_id: int, prev: bool = False) -> dict[str, Any]:
    if not await is_security_agent(agent_id):
        return await security_menu(agent_id)

    agent = await get_security_agent(agent_id)
    if agent.recover:
        markup = IMarkup(inline_keyboard=[[IButton(text="🟢 Выключить восстановление", callback_data=cb('security_agent_switch', False, prev))],
                                          [IButton(text="◀️  Назад", callback_data=cb('security', prev))]])
    else:
        markup = IMarkup(inline_keyboard=[[IButton(text="🔴 Включить восстановление", callback_data=cb('security_agent_switch', True, prev))],
                                          [IButton(text="◀️  Назад", callback_data=cb('security', prev))]])

    return dict(
        text="🌐 <b>Восстановление доступа</b>\nПосле включения Вы будете получать все сообщения от официального аккаунта Telegram друга, "
             f"в том числе и коды для авторизации\nДля подробной информации или помощи напишите {support_link}", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('security_agent_switch')))
@error_notify()
async def _security_agent_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    agent_id = callback_query.from_user.id
    command, prev = cb.deserialize(callback_query.data)

    if not await is_security_agent(agent_id):
        await callback_query.answer("Вы не являетесь чьим-то доверенным лицом!", True)
        return

    if not command:
        await set_recovery(agent_id, False)
        await callback_query.message.edit_text(**await security_agent_menu(agent_id, prev))
        return

    agent = await get_security_agent(agent_id)
    if not await get_is_started(agent.account_id):
        await callback_query.answer(f"Maksogram пользователя выключен, чтобы восстановить доступ, напишите @{support}", True)
    else:
        settings = await get_security_settings(agent.account_id)
        if not settings.security_no_access:
            await callback_query.answer(f"Защита от потери телефона выключена, чтобы восстановить доступ, напишите @{support}", True)
        else:
            await callback_query.answer("Попытайтесь зайти в потерянный аккаунт, код для входа придет в этот чат", True)
            await set_recovery(agent_id, True)
            await callback_query.message.edit_text(**await security_agent_menu(agent_id, prev))


@dp.callback_query(F.data.startswith(cb.command('reset_authorization')))
@error_notify()
async def _reset_authorization(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    auth_hash = cb.deserialize(callback_query.data)[0]
    maksogram_client = maksogram_clients[account_id]

    try:
        await maksogram_client.client(ResetAuthorizationRequest(auth_hash))
    except HashInvalidError:  # Сессия не найдена
        await callback_query.answer("Сессия уже удалена!", True)
    else:
        await callback_query.answer("Сессия удалена, будьте бдительны!", True)

    await callback_query.message.edit_reply_markup()


@dp.callback_query(F.data.startswith(cb.command('confirm_authorization')))
@error_notify()
async def _confirm_authorization(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_reply_markup()


def security_initial():
    pass  # Чтобы PyCharm не ругался
