import random

from typing import Any
from core import (
    s1,
    s2,
    db,
    html,
    OWNER,
    security,
    telegram_clients,
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


@dp.callback_query(F.data == "security")
@security()
async def _security(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    if callback_query.from_user.id != OWNER:
        return await callback_query.answer("Функция в разработке!", True)
    await callback_query.message.edit_text(**security_menu())


def security_menu() -> dict[str, Any]:
    markup = IMarkup(inline_keyboard=[[IButton(text="💀 Защита от взлома", callback_data="security_hack")],
                                      [IButton(text="📵 Защита от потери телефона", callback_data="security_no_access")],
                                      [IButton(text="⚙️ Настройки функции", callback_data="security_settings")],
                                      [IButton(text="◀️  Назад", callback_data="menu")]])
    return {"text": "🛡 <b>Защита аккаунта</b>\nДанная функция поможет защитить аккаунт от взлома, а также помочь восстановить "
                    "доступ, если вы потеряете телефон", "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data == "security_settings")
@security()
async def _security_settings(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await security_settings_menu(callback_query.from_user.id))


async def security_settings_menu(account_id: int) -> dict[str, Any]:
    function = await db.fetch_one(f"SELECT email, agents FROM security WHERE account_id={account_id}")
    markup = IMarkup(inline_keyboard=[[IButton(text=f"📨 {'Добавить' if not function['email'] else 'Изменить'} почту",
                                               callback_data="security_email")],
                                      [IButton(text="🫡 Доверенные лица", callback_data="security_agents")],
                                      [IButton(text="◀️  Назад", callback_data="security")]])
    email = function['email'] or "не указана"
    agents = "\n".join(map(lambda user: f"{' '*4}• <a href='tg://user?id={user[0]}'>{user[1]}</a>", function['agents'].items()))
    agents = ('\n' + agents) if agents else "никого"
    return {"text": f"⚙️ <b>Настройки защиты аккаунта</b>\nПочта: {email}\nДоверенные лица: {agents}",
            "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data == "security_agents")
@security()
async def _security_agents(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await security_agents_menu(callback_query.from_user.id))


async def security_agents_menu(account_id: int) -> dict[str, Any]:
    agents = await db.fetch_one(f"SELECT agents FROM security WHERE account_id={account_id}", one_data=True)
    buttons = []
    for agent in agents.items():
        name = (str(agent[1])[:30] + "...") if len(str(agent[1])) > 30 else agent[1]
        buttons.append([IButton(text=f"🚫 {name}", callback_data=f"security_agent_del{agent[0]}")])
    buttons.append([IButton(text="➕ Пригласить", callback_data="security_new_agent")])
    buttons.append([IButton(text="◀️  Назад", callback_data="security_settings")])
    return {"text": "🫡 <b>Доверенные лица</b>\nЗдесь вы можете удалить доверенное лицо или пригласить нового",
            "parse_mode": html, "reply_markup": IMarkup(inline_keyboard=buttons)}


@dp.callback_query(F.data == "security_new_agent")
@security('state')
async def _security_new_agent_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    if await db.fetch_one(f"SELECT COUNT(*) FROM jsonb_object_keys(("
                          f"SELECT agents FROM security WHERE account_id={account_id}))", one_data=True) >= 3:
        return await callback_query.answer("У ва максимальное количество доверенных лиц", True)
    await state.set_state(UserState.security_new_agent)
    request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request_users)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте человека, которому вы доверяет", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.security_new_agent)
@security('state')
async def _security_new_agent(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    if message.content_type == "users_shared":
        user_id = message.users_shared.user_ids[0]
        account_id = message.chat.id
        if user_id == account_id:  # Себя нельзя
            await message.answer(**await security_agents_menu(account_id))
        else:
            user = await telegram_clients[message.chat.id].get_entity(user_id)
            name = user.first_name + (f" {user.last_name}" if user.last_name else "")
            name = (name[:30] + "...") if len(name) > 30 else name
            await db.execute(f"UPDATE security SET agents=agents || '{s1}\"{user_id}\": \"{name}\"{s2}' WHERE account_id={account_id}")
            await message.answer(**await security_agents_menu(message.chat.id))
    else:
        await message.answer(**await security_agents_menu(message.chat.id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data.startswith("security_agent_del"))
@security()
async def _security_agent_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    agent_id = int(callback_query.data.replace("security_agent_del", ""))
    await db.execute(f"UPDATE security SET agents=agents - '{agent_id}' WHERE account_id={account_id}")
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
                await bot.delete_messages(message.chat.id, [message_id, message.message_id])
            else:
                await db.execute(f"UPDATE confirm_email SET code={code}, email='{message.text}' WHERE account_id={account_id}")
                await state.set_state(UserState.confirm_security_email)
                markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
                new_message_id = (await message.answer(f"На почту {message.text} отправлено сообщение с кодом подтверждения",
                                                       reply_markup=markup)).message_id
                await state.update_data(message_id=new_message_id)
                await bot.delete_messages(message.chat.id, [message_id, message.message_id])
        else:
            markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
            new_message_id = (await message.answer("Вы неправильно ввели почту. Попробуйте еще раз", reply_markup=markup)).message_id
            await state.update_data(message_id=new_message_id)
            await bot.delete_messages(message.chat.id, [message_id, message.message_id])
    else:
        await state.clear()
        await message.answer(**await security_settings_menu(account_id))
        await bot.delete_messages(message.chat.id, [message_id, message.message_id])


@dp.message(UserState.confirm_security_email)
@security('state')
async def _confirm_security_email(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']
    if message.text != "Отмена":
        code = str(await db.fetch_one(f"SELECT code FROM confirm_email WHERE account_id={account_id}", one_data=True))
        if message.text == code:
            email = await db.fetch_one(f"SELECT email FROM confirm_email WHERE account_id={account_id}", one_data=True)
            await db.execute("UPDATE confirm_email SET code=NULL, email=NULL")
            await db.execute(f"UPDATE security SET email='{email}' WHERE account_id={account_id}")
            await state.clear()
            await message.answer(**await security_settings_menu(account_id))
            await bot.delete_messages(message.chat.id, [message_id, message.message_id])
        else:
            markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
            new_message_id = (await message.answer("Код введен неверно!", reply_markup=markup)).message_id
            await state.update_data(message_id=new_message_id)
            await bot.delete_messages(message.chat.id, [message_id, message.message_id])
    else:
        await state.clear()
        await message.answer(**await security_settings_menu(account_id))
        await bot.delete_messages(message.chat.id, [message_id, message.message_id])
        await db.execute("UPDATE confirm_email SET code=NULL, email=NULL")


def security_initial():
    pass  # Чтобы PyCharm не ругался
