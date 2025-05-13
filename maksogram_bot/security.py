import random

from typing import Any
from asyncpg.exceptions import UniqueViolationError
from core import (
    db,
    html,
    OWNER,
    security,
    support_link,
    send_email_message,
)

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton as KButton
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
from aiogram.types import (
    Message,
    CallbackQuery,
    KeyboardButtonRequestUsers,
)


email_message = """<p>Ваш код: <code>. Его можно использовать, чтобы подтвердить адрес электронной почты и включить защиту аккаунта в Telegram.</p>
<p>Если Вы не запрашивали это сообщение, проигнорируйте его.</p>

<p>С уважением,<br>
Команда Maksogram</p>"""


@dp.callback_query((F.data == "security").__or__(F.data == "securityPrev"))
@security()
async def _security(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    prev = "Prev" if callback_query.data == "securityPrev" else ""
    await callback_query.message.edit_text(**await security_menu(callback_query.from_user.id, prev=prev))


async def security_menu(account_id: int, text: str = None, prev: str = "") -> dict[str, Any]:
    agent = await db.fetch_one(f"SELECT account_id FROM security_agents WHERE agent_id={account_id}", one_data=True)
    if agent:
        buttons = [[IButton(text="🌐 Восстановить доступ", callback_data="security_agent")]]
    else:
        buttons = []
    markup = IMarkup(inline_keyboard=[[IButton(text="💀 Защита от взлома", callback_data=f"security_hack{prev}")],
                                      [IButton(text="📵 Защита от потери телефона", callback_data=f"security_no_access{prev}")],
                                      *buttons,
                                      [IButton(text="⚙️ Настройки функции", callback_data=f"security_settings{prev}")],
                                      [IButton(text="◀️  Назад", callback_data="menu")]])
    return {"text": text or "🛡 <b>Защита аккаунта</b>\nДанная функция поможет защитить аккаунт от взлома, а также помочь "
                            "восстановить доступ, если вы потеряете телефон", "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data == "security_settings")
@security()
async def _security_settings(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await security_settings_menu(callback_query.from_user.id))


@dp.callback_query(F.data == "security_settingsPrev")
@security()
async def _security_settings_prev(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.answer("Настройки не найдены!", True)


async def security_settings_menu(account_id: int) -> dict[str, Any]:
    email = await db.fetch_one(f"SELECT email FROM security WHERE account_id={account_id}", one_data=True)
    agents = await db.fetch_all(f"SELECT agent_id, name FROM security_agents WHERE account_id={account_id}")
    markup = IMarkup(inline_keyboard=[[IButton(text=f"📨 {'Добавить' if not email else 'Изменить'} почту", callback_data="security_email")],
                                      [IButton(text="🫡 Доверенные лица", callback_data="security_agents")],
                                      [IButton(text="◀️  Назад", callback_data="security")]])
    email = email or "не указана"
    agents = "\n".join(map(lambda agent: f"    • <a href='tg://user?id={agent['agent_id']}'>{agent['name']}</a>", agents))
    agents = ('\n' + agents) if agents else "никого"
    return {"text": f"⚙️ <b>Настройки защиты аккаунта</b>\nПочта: {email}\nДоверенные лица: {agents}",
            "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data == "security_agents")
@security()
async def _security_agents(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await security_agents_menu(callback_query.from_user.id))


async def security_agents_menu(account_id: int, text: str = None) -> dict[str, Any]:
    buttons = []
    agents = await db.fetch_all(f"SELECT agent_id, name FROM security_agents WHERE account_id={account_id}")
    i = 0
    while i < len(agents):  # Если длина имен достаточно короткая, то помещаем 2 в ряд, иначе 1
        if i + 1 < len(agents) and all(map(lambda x: len(x['name']) <= 15, agents[i:i+1])):
            buttons.append([IButton(text=f"🚫 {agents[i]['name']}", callback_data=f"security_agent_del{agents[i]['agent_id']}"),
                            IButton(text=f"🚫 {agents[i+1]['name']}", callback_data=f"security_agent_del{agents[i+1]['agent_id']}")])
            i += 1
        else:
            buttons.append([IButton(text=f"🚫 {agents[i]['name']}", callback_data=f"security_agent_del{agents[i]['agent_id']}")])
        i += 1
    buttons.append([IButton(text="➕ Пригласить", callback_data="security_new_agent")])
    buttons.append([IButton(text="◀️  Назад", callback_data="security_settings")])
    return {"text": text or "🫡 <b>Доверенные лица</b>\nЗдесь вы можете удалить доверенное лицо или пригласить нового",
            "parse_mode": html, "reply_markup": IMarkup(inline_keyboard=buttons)}


@dp.callback_query(F.data == "security_new_agent")
@security('state')
async def _security_new_agent_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    if await db.fetch_one(f"SELECT COUNT(*) FROM security_agents WHERE account_id={account_id}", one_data=True) >= 3:
        return await callback_query.answer("У ва максимальное количество доверенных лиц", True)
    await state.set_state(UserState.security_new_agent)
    request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request_users)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте пользователя, которому вы доверяете, кнопкой, ID, username или "
                                                      "номер телефона", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.security_new_agent)
@security('state')
async def _security_new_agent(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    account_id = message.chat.id

    user = await new_user(message, security_agents_menu)
    if user:
        user_id = user.id
        if user_id == account_id:  # Себя нельзя
            await message.answer(**await security_agents_menu(account_id))
        else:
            name = f"{user.first_name} {user.last_name or ''}".strip()
            try:
                await db.execute(f"INSERT INTO security_agents VALUES ({account_id}, {user_id}, $1, false)", name)
            except UniqueViolationError:  # Уже есть agent_id
                await message.answer(**await security_agents_menu(account_id, "<b>Этот пользователь уже является "
                                                                              "чьим-то доверительным лицом</b>"))
            else:
                await message.answer(**await security_agents_menu(account_id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data.startswith("security_agent_del"))
@security()
async def _security_agent_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    agent_id = int(callback_query.data.replace("security_agent_del", ""))
    await db.execute(f"DELETE FROM security_agents WHERE account_id={account_id} AND agent_id={agent_id}")
    await callback_query.message.edit_text(**await security_agents_menu(callback_query.from_user.id))


@dp.callback_query(F.data == "security_email")
@security('state')
async def _security_email_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.security_email)
    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте свою почту для подтверждения", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.security_email)
@security('state')
async def _security_email(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']
    if message.text != "Отмена":
        entities = message.entities
        if message.entities and len(message.entities) == 1 and (entities[0].offset, entities[0].length) == (0, len(message.text)) \
                and entities[0].type == "email":
            code = str(random.randint(10000, 99999))
            try:
                await send_email_message(message.text, "Подтверждение почты", email_message.replace("<code>", code), subtype='html')
            except Exception as e:
                await state.clear()
                await message.answer("Произошла ошибка при подтверждении почты. Возможно вы указали неверную. Проверьте ее, "
                                     "если все в порядке, то дождитесь решения проблемы. Мы вас оповестим")
                await bot.send_message(OWNER, f"⚠️Ошибка (send_email_message)⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
                await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])
            else:
                await db.execute(f"UPDATE confirm_email SET code={code}, email='{message.text}' WHERE account_id={account_id}")
                await state.set_state(UserState.confirm_security_email)
                markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
                new_message_id = (await message.answer(f"На почту {message.text} отправлено сообщение с кодом подтверждения",
                                                       reply_markup=markup)).message_id
                await state.update_data(message_id=new_message_id)
                await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])
        else:
            markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
            new_message_id = (await message.answer("Вы неправильно ввели почту. Попробуйте еще раз", reply_markup=markup)).message_id
            await state.update_data(message_id=new_message_id)
            await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])
    else:
        await state.clear()
        await message.answer(**await security_settings_menu(account_id))
        await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.message(UserState.confirm_security_email)
@security('state')
async def _confirm_security_email(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']
    if message.text != "Отмена":
        code = str(await db.fetch_one(f"SELECT code FROM confirm_email WHERE account_id={account_id}", one_data=True))
        if message.text == code:
            await state.clear()
            email = await db.fetch_one(f"SELECT email FROM confirm_email WHERE account_id={account_id}", one_data=True)
            await db.execute("UPDATE confirm_email SET code=NULL, email=NULL")
            await db.execute(f"UPDATE security SET email='{email}' WHERE account_id={account_id}")
            await message.answer(**await security_settings_menu(account_id))
            await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])
        else:
            markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
            new_message_id = (await message.answer("Код введен неверно!", reply_markup=markup)).message_id
            await state.update_data(message_id=new_message_id)
            await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])
    else:
        await state.clear()
        await db.execute("UPDATE confirm_email SET code=NULL, email=NULL")
        await message.answer(**await security_settings_menu(account_id))
        await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data == "security_hackPrev")
@security()
async def _security_hack_prev(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.answer("Для защиты аккаунта от взлома запустите Maksogram!", True)


@dp.callback_query(F.data == "security_hack")
@security()
async def _security_hack(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.answer("В разработке!", True)


@dp.callback_query(F.data == "security_no_accessPrev")
@security()
async def _security_no_access_prev(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.answer("Для защиты аккаунта от потери телефона запустите Maksogram!", True)


@dp.callback_query(F.data == "security_no_access")
@security()
async def _security_no_access(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await security_no_access_menu(callback_query.from_user.id))


async def security_no_access_menu(account_id: int) -> dict[str, Any]:
    function = await db.fetch_one(f"SELECT security_no_access FROM security WHERE account_id={account_id}", one_data=True)
    if not function:
        markup = IMarkup(inline_keyboard=[[IButton(text="🟢 Включить защиту", callback_data="security_no_access_on")],
                                          [IButton(text="◀️  Назад", callback_data="security")]])
    else:
        markup = IMarkup(inline_keyboard=[[IButton(text="🔴 Выключить защиту", callback_data="security_no_access_off")],
                                          [IButton(text="◀️  Назад", callback_data="security")]])
    return dict(
        text=
        "📵 <b>Защита от потери доступа</b>\n"
        "<blockquote expandable>🧐 <b>Когда пригодится?</b>\n"
        "    • Вы потеряли доступ к аккаунту (нет доступа к телефону или другое)\n"
        "😔 <b>Что делать тогда?</b>\n"
        "    • Попросите доверенное лицо запустить <b>@MaksogramBot</b>\n"
        "    • Выберите режим восстановления доступа в меню. Если такой кнопки нет, значит пользователь не является доверенным лицом\n"
        "    • Попытайтесь войти в аккаунт на своем новом устройстве (новый телефон или ноутбук). <b>Код для входа придет вашему "
        "доверенному лицу в чате с ботом</b>\n"
        "⚠️ <b>Предупреждение!</b>\n"
        "    • Пока включена Защита от потери доступа и пользователь в списке доверенных лиц, доверенное лицо сможет в любой момент"
        "получить доступ к вашему аккаунту! Вы узнаете об этом, но все равно Будьте осторожны!</blockquote>",
        parse_mode=html, reply_markup=markup)


@dp.callback_query((F.data == "security_no_access_on").__or__(F.data == "security_no_access_off"))
@security()
async def _security_no_access_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    command = callback_query.data == "security_no_access_on"
    if not command:
        await db.execute(f"UPDATE security_agents SET recover=false WHERE account_id={account_id}")
    await db.execute(f"UPDATE security SET security_no_access={str(command).lower()} WHERE account_id={account_id}")
    await callback_query.message.edit_text(**await security_no_access_menu(account_id))


@dp.callback_query(F.data == "security_agent")
@security()
async def _security_agent(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await security_agent_menu(callback_query.from_user.id))


async def security_agent_menu(agent_id: int):
    function = await db.fetch_one(f"SELECT account_id, recover FROM security_agents WHERE agent_id={agent_id}")
    buttons = []
    if function['account_id']:
        if function['recover']:
            buttons = [[IButton(text="🔴 Выключить восст-ние", callback_data="security_agent_off")]]
        else:
            buttons = [[IButton(text="🟢 Включить восст-ние", callback_data="security_agent_on")]]
    buttons.append([IButton(text="◀️  Назад", callback_data="menu")])
    return {"text": "🌐 <b>Восстановление доступа</b>\nПосле включения Вы будете получать все сообщения от официального аккаунта "
                    f"Telegram, в том числе и коды для авторизации\nДля подробной информации или помощи напишите {support_link}",
            "parse_mode": html, "reply_markup": IMarkup(inline_keyboard=buttons)}


@dp.callback_query((F.data == "security_agent_on").__or__(F.data == "security_agent_off"))
@security()
async def _security_agent_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    agent_id = callback_query.from_user.id
    command = callback_query.data == "security_agent_on"
    account_id = await db.fetch_one(f"SELECT account_id FROM security_agents WHERE agent_id={agent_id}", one_data=True)
    if not account_id:
        await callback_query.answer("Вы не являетесь чьим-то доверенным лицом...", True)
        return await callback_query.message.edit_text(**await security_agent_menu(agent_id))
    edit = True
    if command:
        is_started = await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True)
        if not is_started:
            edit = False
            await callback_query.answer("Maksogram для аккаунта выключен! Напишите тех. поддержке", True)
        else:
            function = await db.fetch_one(f"SELECT security_no_access FROM security WHERE account_id={account_id}", one_data=True)
            if function:
                await callback_query.answer("Попытайтесь зайти в аккаунт с нового устройства. Код для входа придет здесь", True)
            else:
                edit = False
                await callback_query.answer("Пользователь не включил Защиту от потери доступа, поэтому вы не получите коды", True)
    else:
        await callback_query.answer("Восстановление доступа отключено!", True)
    if edit:
        await db.execute(f"UPDATE security_agents SET recover={str(command).lower()} WHERE agent_id={agent_id}")
        await callback_query.message.edit_text(**await security_agent_menu(agent_id))


def security_initial():
    pass  # Чтобы PyCharm не ругался
