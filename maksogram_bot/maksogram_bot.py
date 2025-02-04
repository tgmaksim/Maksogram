import time
import asyncio
import aiohttp

from html import escape
from datetime import timedelta
from typing import Literal, Any
from sys_keys import TOKEN, release
from saving_messages import admin_program, program
from create_chats import create_chats, CreateChatsError
from core import (
    s1,  # "{"
    s2,  # "}"
    db,
    html,
    SITE,
    OWNER,
    support,
    time_now,
    security,
    Variables,
    omsk_time,
    account_on,
    account_off,
    json_encode,
    MaksogramBot,
    zip_int_data,
    count_avatars,
    resources_path,
    unzip_int_data,
    preview_options,
    telegram_clients,
    UserIsNotAuthorized,
    new_telegram_client,
)

from telethon import errors
from telethon import TelegramClient
from aiogram import Bot, Dispatcher, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from aiogram.filters.command import Command, CommandStart
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import (
    Message,
    WebAppInfo,
    FSInputFile,
    CallbackQuery,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButtonRequestUsers,
)

bot = Bot(TOKEN)
dp = Dispatcher()


# Класс с глобальными переменными для удобного пользования
class Data:
    web_app = "https://tgmaksim.ru/maksogram"


# Класс нужен для определения состояния пользователя в данном боте,
# например: пользователь должен отправить отзыв в следующем сообщении
class UserState(StatesGroup):
    class Admin(StatesGroup):
        mailing = State('mailing')
        confirm_mailing = State('confirm_mailing')

    feedback = State('feedback')
    send_phone_number = State('send_phone_number')
    send_code = State('send_code')
    send_password = State('send_password')
    relogin = State('relogin')
    relogin_with_password = State('relogin_with_password')
    status_user = State('status_user')
    answering_machine = State('answering_machine')
    answering_machine_edit = State('answering_machine_edit')
    avatar = State('avatar')


# Метод для добавления и изменения "знакомых"
@dp.message(Command('new_acquaintance'))
@security()
async def _new_acquaintance(message: Message):
    if await developer_command(message): return
    if message.reply_to_message and message.reply_to_message.text:
        id = int(message.reply_to_message.text.split('\n', 1)[0].replace("ID: ", ""))
        name = message.text.split(maxsplit=1)[1]
    else:
        id, name = message.text.split(maxsplit=2)[1:]
    if await db.fetch_one(f"SELECT id FROM acquaintances WHERE id={id}"):
        await db.execute(f"UPDATE acquaintances SET name='{name}' WHERE id={id}")
        await message.answer("Данные знакомого изменены")
    else:
        await db.execute(f"INSERT INTO acquaintances VALUES({id}, '{name}')")
        await message.answer("Добавлен новый знакомый!")


# Метод для отправки сообщения от имени бота
@dp.message(F.reply_to_message.__and__(F.chat.id == OWNER).__and__(F.reply_to_message.text.startswith("ID")))
@security()
async def _sender(message: Message):
    user_id = int(message.reply_to_message.text.split('\n', 1)[0].replace("ID: ", ""))
    try:
        copy_message = await bot.copy_message(user_id, OWNER, message.message_id)
    except Exception as e:
        await message.answer(f"Сообщение не отправлено из-за ошибки {e.__class__.__name__}: {e}")
    else:
        await message.answer("Сообщение отправлено")
        await bot.forward_message(OWNER, user_id, copy_message.message_id)


@dp.message(Command('admin'))
@security()
async def _admin(message: Message):
    if await developer_command(message): return
    await message.answer("Команды разработчика:\n"
                         "/reload - перезапустить программу\n"
                         "/stop - остановить программу\n"
                         "/version - изменить версию бота\n"
                         "/new_acquaintance - добавить знакомого\n"
                         "/mailing - рассылка")


@dp.message(Command('reload'))
@security()
async def _reload(message: Message):
    if await developer_command(message): return
    if release:
        await message.answer("<b>Перезапуск бота</b>", parse_mode=html)
        print("Перезапуск бота")
        async with aiohttp.ClientSession() as session:
            async with session.post("https://panel.netangels.ru/api/gateway/token/",
                                    data={"api_key": Variables.ApiKey}) as response:
                token = (await response.json())['token']
                await session.post(f"https://api-ms.netangels.ru/api/v1/hosting/background-processes/{Variables.ProcessId}/restart",
                                   headers={"Authorization": f"Bearer {token}"})
    else:
        await message.answer("В тестовом режиме перезапуск бота программно не предусмотрен!")
        print("В тестовом режиме перезапуск бота программно не предусмотрен!")


@dp.message(Command('stop'))
@security()
async def _stop(message: Message):
    if await developer_command(message): return
    await message.answer("<b>Остановка бота и программы</b>", parse_mode=html)
    print("Остановка бота и программы")
    if release:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://panel.netangels.ru/api/gateway/token/",
                                    data={"api_key": Variables.ApiKey}) as response:
                token = (await response.json())['token']
                await session.post(f"https://api-ms.netangels.ru/api/v1/hosting/background-processes/{Variables.ProcessId}/stop",
                                   headers={"Authorization": f"Bearer {token}"})
    else:
        await dp.stop_polling()
        asyncio.get_event_loop().stop()


@dp.message(Command('mailing'))
@security('state')
async def _start_mailing(message: Message, state: FSMContext):
    if await developer_command(message): return
    await state.set_state(UserState.Admin.mailing)
    await message.answer("Отправь сообщение, которое я разошлю все активным пользователям бота")


@dp.message(UserState.Admin.mailing)
@security('state')
async def _mailing(message: Message, state: FSMContext):
    if await developer_command(message): return
    await state.update_data(message_id=message.message_id)
    markup = IMarkup(inline_keyboard=[[IButton(text="Переслать 💬", callback_data="mailing_forward"),
                                       IButton(text="Отправить 🔐", callback_data="mailing_send")],
                                      [IButton(text="❌ Отмена ❌", callback_data="stop_mailing")]])
    await message.answer("Выбери способ рассылки сообщения 👇", reply_markup=markup)


@dp.callback_query(F.data.in_(["mailing_forward", "mailing_send", "stop_mailing"]))
@security('state')
async def _confirm_mailing(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    match callback_query.data:
        case "mailing_forward":
            await callback_query.message.edit_text(f"{callback_query.message.text}\nПересылка")
            message_id = (await state.get_data())['message_id']
            await state.clear()
            fun = lambda user_id: bot.forward_message(user_id, callback_query.from_user.id, message_id)
        case "mailing_send":
            await callback_query.message.edit_text(f"{callback_query.message.text}\nОтправка")
            message_id = (await state.get_data())['message_id']
            await state.clear()
            fun = lambda user_id: bot.copy_message(user_id, callback_query.from_user.id, message_id)
        case _:
            await state.clear()
            return await callback_query.message.edit_text("Операция отменена!")
    result = [await db.fetch_one("SELECT COUNT(*) FROM accounts", one_data=True), 0, 0, 0]
    for account in await db.fetch_all("SELECT id, is_started FROM accounts"):
        if account['is_started']:
            result[1] += 1  # Количество активных пользователей
            try:
                await fun(account['id'])
            except (TelegramBadRequest, TelegramForbiddenError):
                result[2] += 1  # Количество ошибок
            else:
                result[3] += 1  # Количество доставленных сообщений
            await asyncio.sleep(1)
    await callback_query.message.answer(f"Рассылка завершена!\nВсего пользователей: {result[0]}\n"
                                        f"Активные пользователи: {result[1]}\nДоставлено сообщений: {result[3]}\n"
                                        f"Произошло ошибок: {result[2]}")


@dp.message(Command('feedback'))
@security('state')
async def _start_feedback(message: Message, state: FSMContext):
    if await new_message(message): return
    await state.set_state(UserState.feedback)
    markup = IMarkup(inline_keyboard=[[IButton(text="❌", callback_data="stop_feedback")]])
    await message.answer("Отправьте текст вопроса или предложения. Любое следующее сообщение будет считаться отзывом",
                         reply_markup=markup)


@dp.message(UserState.feedback)
@security('state')
async def _feedback(message: Message, state: FSMContext):
    if await new_message(message, forward=False): return
    await state.clear()
    acquaintance = await username_acquaintance(message)
    acquaintance = f"<b>Знакомый: {acquaintance}</b>\n" if acquaintance else ""
    await bot.send_photo(OWNER,
                         photo=FSInputFile(resources_path("feedback.png")),
                         caption=f"ID: {message.chat.id}\n"
                                 f"{acquaintance}" +
                                 (f"USERNAME: @{message.from_user.username}\n" if message.from_user.username else "") +
                                 f"Имя: {message.from_user.first_name}\n" +
                                 (f"Фамилия: {message.from_user.last_name}\n" if message.from_user.last_name else "") +
                                 f"Время: {omsk_time(message.date)}",
                         parse_mode=html)
    await message.forward(OWNER)
    await message.answer("Большое спасибо за отзыв!❤️❤️❤️")


@dp.callback_query(F.data == "stop_feedback")
@security('state')
async def _stop_feedback(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.clear()
    await callback_query.message.edit_text("Отправка отзыва отменена")


@dp.callback_query(F.data == "send_payment")
@security()
async def _send_payment(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    name = await db.fetch_one(f"SELECT name FROM accounts WHERE id={account_id}", one_data=True)
    markup = IMarkup(inline_keyboard=[[
        IButton(text="Подтвердить! ✅", callback_data=f"confirm_sending_payment{account_id}_{callback_query.message.message_id}")]])
    await bot.send_message(OWNER, f"Пользователь {name} отправил оплату, проверь это! Если так, то подтверди, "
                                  "чтобы я продлил подписку на месяц", reply_markup=markup)
    await callback_query.answer("Запрос отправлен. Ожидайте!", True)


async def payment(account_id: int) -> dict[str, Any]:
    fee = await db.fetch_one(f"SELECT payment['fee'] FROM accounts WHERE id={account_id}", one_data=True)
    markup = IMarkup(inline_keyboard=[[IButton(text="TON", web_app=WebAppInfo(url=f"{Data.web_app}/payment/ton")),
                                       IButton(text="BTC", web_app=WebAppInfo(url=f"{Data.web_app}/payment/btc"))],
                                      [IButton(text="Перевод по номеру", web_app=WebAppInfo(url=f"{Data.web_app}/payment/fps"))],
                                      [IButton(text="Я отправил(а)  ✅", callback_data="send_payment")]])
    return {"text": f"Способы оплаты:\nСбер: ({fee} руб)\nBTC: (0.00002 btc)\nTON: (0.25 ton)",
            "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data.startswith("confirm_sending_payment"))
@security()
async def _confirm_sending_payment(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    if callback_query.from_user.id != OWNER:
        return await callback_query.answer("Ошибка!", True)
    account_id, message_id = map(int, callback_query.data.replace("confirm_sending_payment", "").split("_"))
    await db.execute(f"""UPDATE accounts SET payment['next_payment']=to_jsonb(extract(epoch FROM ((CASE WHEN 
                     to_timestamp(payment['next_payment']::int) > CURRENT_TIMESTAMP THEN 
                     to_timestamp(payment['next_payment']::int) ELSE CURRENT_TIMESTAMP END) + INTERVAL '32 days'))::int), 
                     is_paid=true WHERE id=7302572022;""")  # перемещение даты следующей оплаты на 30 дней вперед
    await bot.edit_message_reply_markup(chat_id=account_id, message_id=message_id)
    await bot.send_message(account_id, f"Ваша оплата подтверждена! Следующий платеж через 32 дня", reply_to_message_id=message_id)
    await callback_query.message.edit_text(callback_query.message.text + '\n\nУспешно!')


@dp.message(Command('version'))
@security()
async def _version(message: Message):
    if await new_message(message): return
    version = Variables.version
    await message.answer(f"Версия: {version}\n<a href='{SITE}/{version}'>Обновление</a> 👇",
                         parse_mode=html, link_preview_options=preview_options(version))


@dp.message(CommandStart())
@security('state')
async def _start(message: Message, state: FSMContext):
    if await new_message(message): return
    await state.clear()
    service_message = await message.answer("...", reply_markup=ReplyKeyboardRemove())
    if message.text.startswith('/start r'):
        friend_id = unzip_int_data(message.text.replace('/start r', ''))
        if message.chat.id == friend_id:
            return await message.answer("Вы не можете зарегистрироваться по своей реферальной ссылке!")
        await bot.send_message(friend_id, "По вашей реферальной ссылке зарегистрировался новый пользователь. Если он "
                                          "оплатит подписку, то вы получите скидку 20% (действует только при оплате по СБП)")
        await bot.send_message(OWNER, f"Регистрация по реферальной ссылке #r{friend_id}")
    else:
        markup = IMarkup(inline_keyboard=[[IButton(text="🚀 Мои функции", callback_data="help")],
                                          [IButton(text="⚙️ Меню и настройки", callback_data="settings")]])
        await message.answer(f"Привет, {escape(await username_acquaintance(message, 'first_name'))} 👋\n"
                             f"<a href='{SITE}'>Обзор всех функций</a> 👇",
                             parse_mode=html, reply_markup=markup, link_preview_options=preview_options())
    await service_message.delete()


@dp.message(Command('help'))
@security()
async def _help(message: Message):
    if await new_message(message): return
    await help(message)


@dp.callback_query(F.data == "help")
@security()
async def _help_button(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_reply_markup()
    await help(callback_query.message)


async def help(message: Message):
    await message.answer("/settings - настройки (меню)\n"
                         "/feedback - оставить отзыв или предложение\n"
                         "/friends - реферальная программа\n", parse_mode=html)


@dp.message(Command('settings'))
@security()
async def _settings(message: Message):
    if await new_message(message): return
    await message.answer(**await settings(message.chat.id))


@dp.callback_query(F.data == "settings")
async def _settings_button(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await settings(callback_query.message.chat.id))


async def settings(account_id: int) -> dict[str, Any]:
    status = await db.fetch_one(f"SELECT is_started FROM accounts WHERE id={account_id}", one_data=True)
    if status is None:
        markup = IMarkup(inline_keyboard=[[IButton(text="🟢 Включить Maksogram", callback_data="registration")],
                                          [IButton(text="ℹ️ Узнать все возможности", url=SITE)]])
    elif status is False:
        markup = IMarkup(inline_keyboard=[[IButton(text="🟢 Включить Maksogram", callback_data="on")],
                                          [IButton(text="ℹ️ Памятка по функциям", url=SITE)]])
    else:
        markup = IMarkup(inline_keyboard=[[IButton(text="🔴 Выключить Maksogram", callback_data="off")],
                                          [IButton(text="🌐 Друг в сети", callback_data="status_users"),
                                           IButton(text="🤖 Автоответчик", callback_data="answering_machine")],
                                          [IButton(text="📸 Новая аватарка", callback_data="avatars")],
                                          [IButton(text="💬 Maksogram в чате", callback_data="modules")],
                                          [IButton(text="ℹ️ Памятка по функциям", url=SITE)]])
    return {"text": "⚙️ Maksogram — настройки ⚙️", "reply_markup": markup}


@dp.message(Command('friends'))
@security()
async def _friends(message: Message):
    if await new_message(message): return
    url = f"tg://resolve?domain={MaksogramBot.username}&start={referal_link(message.chat.id)}"
    await message.answer(
        "<b>Реферальная программа\n</b>"
        "Приглашайте своих знакомых и получайте скидку 20% при оплате по СПБ рублями за каждого друга. "
        "Пригласить друга можно, отправив сообщение 👇", parse_mode=html)
    markup = IMarkup(inline_keyboard=[[IButton(text="Попробовать бесплатно", url=url)]])
    await message.answer_photo(
        FSInputFile(resources_path("logo.jpg")),
        f"Привет! Я хочу тебе посоветовать отличного <a href='{url}'>бота</a>. "
        "Он сохранит все твои сообщения и подскажет, когда кто-то их удалит, изменит, прочитает или поставит реакцию. "
        "Также в нем есть множество других полезных функций", parse_mode=html, reply_markup=markup, disable_web_page_preview=True)


@dp.callback_query(F.data == "modules")
@security()
async def _modules(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**modules_menu())


def modules_menu() -> dict[str, Any]:
    markup = IMarkup(inline_keyboard=[[IButton(text="🔢 Калькулятор", callback_data="calculator")],
                                      [IButton(text="◀️  Назад", callback_data="settings")]])
    return {"text": "💬 <b>Maksogram в чате</b>\nФункции, которые работают прямо из любого чата, не нужно вызывать меня",
            "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data == "calculator")
@security()
async def _calculator(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await calculator_menu(callback_query.message.chat.id))


async def calculator_menu(account_id: int) -> dict[str, Any]:
    if await db.fetch_one(f"SELECT modules['calculator'] FROM accounts WHERE id={account_id}", one_data=True):
        status_button = IButton(text="🔴 Выключить калькулятор", callback_data="calculator_off")
    else:
        status_button = IButton(text="🟢 Включить калькулятор", callback_data="calculator_on")
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="Как работает калькулятор?", url=f"{SITE}#калькулятор")],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "🔢 <b>Калькулятор в чате</b>\nРешает примеры разных уровней сложности от обычного умножения до "
                    "длинных примеров. Для срабатывания укажите в конце \"=\"\n<blockquote>10+5*15=</blockquote>",
            "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data.in_(["calculator_on", "calculator_off"]))
@security()
async def _calculator_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[1]
    match command:
        case "on":
            await db.execute(f"UPDATE accounts SET modules['calculator']='true' WHERE id={callback_query.from_user.id}")
        case "off":
            await db.execute(f"UPDATE accounts SET modules['calculator']='false' WHERE id={callback_query.from_user.id}")
    await callback_query.message.edit_text(**await calculator_menu(callback_query.message.chat.id))


@dp.callback_query(F.data == "avatars")
@security()
async def _avatars(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await avatars_menu(callback_query.message.chat.id))


async def avatars_menu(account_id: int) -> dict[str, Any]:
    buttons = []
    users = await db.fetch_all(f"SELECT key.k AS id, avatars -> key.k ->> 'name' AS name "
                               f"FROM (SELECT jsonb_object_keys(avatars) AS k FROM accounts WHERE id={account_id}) AS key, "
                               f"(SELECT avatars FROM accounts WHERE id={account_id}) AS avatars;")
    for user in users:
        buttons.append([IButton(text=f"📸 {user['name']}", callback_data=f"avatar_menu{user['id']}")])
    buttons.append([IButton(text="➕ Добавить пользователя", callback_data="new_avatar")])
    buttons.append([IButton(text="◀️  Назад", callback_data="settings")])
    return {"text": "📸 <b>Новая аватарка</b>\nКогда кто-то из выбранных пользователей изменит или добавит аватарку, я сообщу вам",
            "parse_mode": html, "reply_markup": IMarkup(inline_keyboard=buttons)}


@dp.callback_query(F.data.startswith("new_avatar"))
@security('state')
async def _new_avatar_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    if await db.fetch_one(f"SELECT COUNT(*) FROM (SELECT jsonb_object_keys(avatars) FROM accounts WHERE id="
                          f"{callback_query.from_user.id}) AS count", one_data=True) >= 2:
        return await callback_query.answer("У вас максимальное количество \"новых аватарок\"")
    await state.set_state(UserState.avatar)
    request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Выбрать", request_users=request_users)],
                                           [KeyboardButton(text="Отмена")]], resize_keyboard=True)
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
        if user_id != account_id:
            user = await telegram_clients[account_id].get_entity(user_id)
            user = json_encode({"name": user.first_name + (f" {user.last_name}" if user.last_name else ""),
                                "count": await count_avatars(account_id, user_id)})
            await db.execute(f"UPDATE accounts SET avatars['{user_id}']=$1 WHERE id={account_id}", user)
            await message.answer(**await avatar_menu(message.chat.id, user_id))
    else:
        await message.answer(**await avatars_menu(message.chat.id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


async def avatar_menu(account_id: int, user_id: int) -> dict[str, Any]:
    name = await db.fetch_one(f"SELECT avatars['{user_id}']['name'] FROM accounts WHERE id={account_id}", one_data=True)
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
    await db.execute(f"UPDATE accounts SET avatars=avatars-'{user_id}' WHERE id={callback_query.from_user.id}")
    await callback_query.message.edit_text(**await avatars_menu(callback_query.message.chat.id))


@dp.callback_query(F.data.startswith("avatar_menu"))
@security()
async def _avatar_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    user_id = int(callback_query.data.replace("avatar_menu", ""))
    await callback_query.message.edit_text(**await avatar_menu(callback_query.message.chat.id, user_id))


@dp.callback_query(F.data == "status_users")
@security()
async def _status_users(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await status_users_menu(callback_query.message.chat.id))


async def status_users_menu(account_id: int) -> dict[str, Any]:
    buttons = []
    users = await db.fetch_all(f"SELECT key.k AS id, status_users -> key.k ->> 'name' AS name "
                               f"FROM (SELECT jsonb_object_keys(status_users) AS k FROM accounts WHERE id={account_id}) AS key, "
                               f"(SELECT status_users FROM accounts WHERE id={account_id}) AS status_users;")
    for user in users:
        buttons.append([IButton(text=f"🌐 {user['name']}", callback_data=f"status_user_menu{user['id']}")])
    buttons.append([IButton(text="➕ Добавить нового пользователя", callback_data="new_status_user")])
    buttons.append([IButton(text="◀️  Назад", callback_data="settings")])
    return {"text": "🌐 <b>Друг в сети</b>\nЯ уведомлю вас, если пользователь будет онлайн/офлайн. Не работает, если собеседник "
                    "скрыл время последнего захода...", "reply_markup": IMarkup(inline_keyboard=buttons), "parse_mode": html}


@dp.callback_query(F.data.startswith("status_user_menu"))
@security()
async def _status_user_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    user_id = int(callback_query.data.replace("status_user_menu", ""))
    await callback_query.message.edit_text(**await status_user_menu(callback_query.message.chat.id, user_id))


async def status_user_menu(account_id: int, user_id: int) -> dict[str, Any]:
    def status(parameter: bool):
        return "🟢" if parameter else "🔴"

    def command(parameter: bool):
        return "off" if parameter else "on"

    user = await db.fetch_one(f"SELECT status_users['{user_id}'] FROM accounts WHERE id={account_id}", one_data=True)
    if user is None:
        return await status_users_menu(account_id)
    markup = IMarkup(inline_keyboard=[
        [IButton(text=f"{status(user['online'])} Появление в сети",
                 callback_data=f"status_user_online_{command(user['online'])}_{user_id}")],
        [IButton(text=f"{status(user['offline'])} Выход из сети",
                 callback_data=f"status_user_offline_{command(user['offline'])}_{user_id}")],
        [IButton(text=f"{status(user['reading'])} Чтение моего сообщения",
                 callback_data=f"status_user_reading_{command(user['reading'])}_{user_id}")],
        [IButton(text="🚫 Удалить пользователя", callback_data=f"status_user_del{user_id}")],
        [IButton(text="◀️  Назад", callback_data="status_users")]])
    return {"text": f"🌐 <b>Друг в сети</b>\nКогда <b>{user['name']}</b> выйдет/зайдет в сеть или прочитает сообщение, я сообщу",
            "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data.startswith("status_user_online_on").__or__(F.data.startswith("status_user_online_off")).__or__(
                   F.data.startswith("status_user_offline_on")).__or__(F.data.startswith("status_user_offline_off")).__or__(
                   F.data.startswith("status_user_reading_on")).__or__(F.data.startswith("status_user_reading_off")))
@security()
async def _status_user_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    function_status_user, command, user_id = callback_query.data.replace("status_user_", "").split("_")
    user = await db.fetch_one(f"SELECT status_users['{user_id}']['online'] FROM accounts WHERE id={account_id}", one_data=True)
    if user is None:
        return await callback_query.message.edit_text(**await status_users_menu(account_id))
    await db.execute(
        f"UPDATE accounts SET status_users['{user_id}']['{function_status_user}']="
        f"'{'true' if command == 'on' else 'false'}' WHERE id={account_id}")
    await callback_query.message.edit_text(**await status_user_menu(account_id, int(user_id)))


@dp.callback_query(F.data == "new_status_user")
@security('state')
async def _new_status_user_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    if await db.fetch_one(f"SELECT COUNT(*) FROM (SELECT jsonb_object_keys(status_users) FROM accounts WHERE id="
                          f"{callback_query.from_user.id}) AS count", one_data=True) >= 2:
        return await callback_query.answer("У вас максимальное количество!", True)
    await state.set_state(UserState.status_user)
    request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Выбрать", request_users=request_users)],
                                           [KeyboardButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте пользователя для отслеживания", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.status_user)
@security('state')
async def _new_status_user(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    if message.content_type == "users_shared":
        user_id = message.users_shared.user_ids[0]
        account_id = message.chat.id
        user = await telegram_clients[message.chat.id].get_entity(user_id)
        name = user.first_name + (f" {user.last_name}" if user.last_name else "")
        name = (name[:30] + "...") if len(name) > 30 else name
        telegram_clients[account_id].list_event_handlers()[5][1].chats.add(user_id)
        status_user = json_encode({"name": name, "online": False, "offline": False, "reading": False})
        await db.execute(f"UPDATE accounts SET status_users['{user_id}']=$1 WHERE id={account_id}", status_user)
        await message.answer(**await status_user_menu(message.chat.id, user_id))
    else:
        await message.answer(**await status_users_menu(message.chat.id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data.startswith("status_user_del"))
@security()
async def _status_user_del(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    user_id = int(callback_query.data.replace("status_user_del", ""))
    account_id = callback_query.from_user.id
    telegram_clients[account_id].list_event_handlers()[5][1].chats.remove(user_id)
    await db.execute(f"UPDATE accounts SET status_users=status_users - '{user_id}' WHERE id={account_id}")
    await callback_query.message.edit_text(**await status_users_menu(callback_query.message.chat.id))


@dp.callback_query(F.data == "answering_machine")
@security()
async def _answering_machine(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await answering_machine_menu(callback_query.message.chat.id))


async def answering_machine_menu(account_id: int) -> dict[str, Any]:
    buttons = []
    main, answers = (await db.fetch_one(f"SELECT answering_machine['main'] AS main, answering_machine['variants'] AS variants "
                                         f"FROM accounts WHERE id={account_id}")).values()
    for answer_id in answers:
        text = (answers[answer_id]['text'][:30] + "...") if len(answers[answer_id]['text']) > 30 else answers[answer_id]['text']
        indicator = "🟢 " if main == int(answer_id) else ""
        buttons.append([IButton(text=f"{indicator}{text}", callback_data=f"answering_machine_menu{answer_id}")])
    buttons.append([IButton(text="➕ Создать новый ответ", callback_data="new_answering_machine")])
    buttons.append([IButton(text="◀️  Назад", callback_data="settings")])
    markup = IMarkup(inline_keyboard=buttons)
    return {"text": "🤖 <b>Автоответчик</b>\nЗдесь хранятся все ваши автоматические ответы. Вы можете включить нужный, "
                    "удалить, изменить или добавить новый", "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data == "new_answering_machine")
@security('state')
async def _new_answering_machine_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    if await db.fetch_one("SELECT COUNT(*) FROM (SELECT jsonb_object_keys(answering_machine['variants']) "
                          f"FROM accounts WHERE id={callback_query.from_user.id}) AS count", one_data=True) >= 5:
        return await callback_query.answer("У вас максимальное количество автоответов", True)
    await state.set_state(UserState.answering_machine)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Напишите <b>текст</b>, который я отправлю в случае необходимости",
                                                      parse_mode=html, reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.answering_machine)
@security('state')
async def _new_answering_machine(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    if message.content_type != "text":
        await message.answer("<b>Ваше сообщение не является текстом</b>", parse_mode=html,
                             reply_markup=(await answering_machine_menu(message.chat.id))['reply_markup'])
    elif len(message.text) > 512:
        await message.answer("<b>Ваше сообщение слишком длинное</b>", parse_mode=html,
                             reply_markup=(await answering_machine_menu(message.chat.id))['reply_markup'])
    elif message.text != "Отмена":
        answer_id = int(time.time()) - 1737828000  # 1737828000 - 2025/01/26 00:00 (день активного обновления автоответчика)
        answer = json_encode({"text": message.text, "entities": [entity.model_dump() for entity in message.entities or []]})
        await db.execute(f"UPDATE accounts SET answering_machine['variants']['{answer_id}']=$1::jsonb WHERE id={message.chat.id}", answer)
        await message.answer(**await auto_answer_menu(message.chat.id, answer_id))
    else:
        await message.answer(**await answering_machine_menu(message.chat.id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data.startswith("answering_machine_menu"))
@security()
async def _answering_machine_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_menu", ""))
    await callback_query.message.edit_text(**await auto_answer_menu(callback_query.message.chat.id, answer_id))


async def auto_answer_menu(account_id: int, answer_id: int):
    data = (await db.fetch_one(f"SELECT answering_machine['main'] AS main, answering_machine['variants']['{answer_id}'] AS answer "
                               f"FROM accounts WHERE id={account_id}")).values()
    if data is None:
        return await answering_machine_menu(account_id)
    main, answer = data
    status = main == int(answer_id)
    status_button = IButton(text="🔴 Выключить автоответ", callback_data=f"answering_machine_off_{answer_id}") if status else \
        IButton(text="🟢 Включить автоответ", callback_data=f"answering_machine_on_{answer_id}")
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="✏️ Изменить текст", callback_data=f"answering_machine_edit{answer_id}")],
                                      [IButton(text="🚫 Удалить автоответ", callback_data=f"answering_machine_del{answer_id}")],
                                      [IButton(text="◀️  Назад", callback_data="answering_machine")]])
    return {"text": answer['text'], "entities": answer['entities'], "reply_markup": markup}


@dp.callback_query(F.data.startswith("answering_machine_del"))
@security()
async def _answering_machine_del(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_del", ""))
    account_id = callback_query.from_user.id
    await db.execute(f"UPDATE accounts SET answering_machine['variants']=answering_machine['variants'] - '{answer_id}' "
                     f"WHERE id={account_id}")
    if await db.fetch_one(f"SELECT answering_machine['main'] FROM accounts WHERE id={account_id}", one_data=True) == answer_id:
        await db.execute(f"UPDATE accounts SET answering_machine['main']='0' WHERE id={account_id}")
    await callback_query.message.edit_text(**await answering_machine_menu(callback_query.message.chat.id))


@dp.callback_query(F.data.startswith("answering_machine_on").__or__(F.data.startswith("answering_machine_off")))
@security()
async def _answering_machine_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command, answer_id = callback_query.data.replace("answering_machine_", "").split("_")
    account_id = callback_query.from_user.id
    answer = await db.fetch_one(f"SELECT answering_machine['variants']['{answer_id}'] "
                                f"FROM accounts WHERE id={account_id}", one_data=True)
    if answer is None:
        await callback_query.answer("Автоответ был удалено ранее!", True)
        return await callback_query.message.edit_text(**await answering_machine_menu(account_id))
    await db.execute(f"UPDATE accounts SET answering_machine['main']='{0 if command == 'off' else answer_id}', "
                     f"answering_machine['sending']='[]' WHERE id={account_id}")
    await callback_query.message.edit_text(**await auto_answer_menu(account_id, answer_id))


@dp.callback_query(F.data.startswith("answering_machine_edit"))
@security('state')
async def _answering_machine_edit_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_edit", ""))
    await state.set_state(UserState.answering_machine_edit)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Напишите <b>текст</b>, который я отправлю в случае необходимости",
                                                      parse_mode=html, reply_markup=markup)).message_id
    await state.update_data(message_id=message_id, answer_id=answer_id)
    await callback_query.message.delete()


@dp.message(UserState.answering_machine_edit)
@security('state')
async def _answering_machine_edit(message: Message, state: FSMContext):
    if await new_message(message): return
    data = await state.get_data()
    message_id = data['message_id']
    answer_id = data['answer_id']
    await state.clear()
    account_id = message.chat.id
    if not await db.fetch_one(f"SELECT answering_machine['variants'] ? '{answer_id}' FROM accounts WHERE id={account_id}"):
        await message.answer(**await answering_machine_menu(account_id))
    elif message.content_type != "text":
        await message.answer("<b>Ваше сообщение не является текстом</b>", parse_mode=html,
                             reply_markup=(await auto_answer_menu(message.chat.id, answer_id))['reply_markup'])
    elif len(message.text) > 512:
        await message.answer("<b>Ваше сообщение слишком длинное</b>", parse_mode=html,
                             reply_markup=(await auto_answer_menu(message.chat.id, answer_id))['reply_markup'])
    elif message.text != "Отмена":
        text = '"' + message.text.replace("\n", "\\n") + '"'
        await db.execute(f"UPDATE accounts SET answering_machine['variants']['{answer_id}']['text']=$1::jsonb, "
                         f"answering_machine['variants']['{answer_id}']['entities']=$2 WHERE id={account_id}",
                         text, json_encode([entity.model_dump() for entity in message.entities or []]))
        await message.answer(**await auto_answer_menu(message.chat.id, answer_id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data == "registration")
@security('state')
async def _registration(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.send_phone_number)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отправить номер телефона", request_contact=True)],
                                           [KeyboardButton(text="Отмена")]], resize_keyboard=True)
    await callback_query.message.answer("Начнем настройку Maksogram для твоего аккаунта. Отправь свой номер телефона",
                                        reply_markup=markup)
    await callback_query.message.delete()


@dp.callback_query(F.data == "off")
@security()
async def _off(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    phone_number = await db.fetch_one(f"SELECT phone_number FROM accounts WHERE id={account_id}", one_data=True)
    await account_off(account_id, f"+{phone_number}")
    await callback_query.message.edit_text(**await settings(callback_query.message.chat.id))


@dp.callback_query(F.data == "on")
@security('state')
async def _on(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    account = await db.fetch_one(f"SELECT name, is_started, is_paid, phone_number FROM accounts WHERE id={account_id}")
    if account is not None and account['is_started'] is False:  # Зарегистрирован, но отключен
        if not account['is_paid']:  # Просрочен платеж
            payment_message = await payment(account_id)
            await callback_query.message.edit_text("Ваша подписка истекла. Продлите ее, чтобы пользоваться Maksogram\n"
                                                   f"{payment_message['text']}", reply_markup=payment_message['reply_markup'])
            return await bot.send_message(OWNER, f"Платеж просрочен. Программа не запущена ({account['name']})")
        try:
            await account_on(account_id, (admin_program if callback_query.message.chat.id == OWNER else program).Program)
        except UserIsNotAuthorized:  # Удалена сессия
            await state.set_state(UserState.relogin)
            await callback_query.answer("Удалена Telegram-сессия!")
            markup = ReplyKeyboardMarkup(keyboard=[[
                KeyboardButton(text="Отправить код", web_app=WebAppInfo(url="https://tgmaksim.ru/maksogram/code"))],
                [KeyboardButton(text="Отмена")]], resize_keyboard=True)
            await callback_query.message.answer("Вы удалили сессию Telegram, Maksogram больше не имеет доступа "
                                                "к вашему аккаунту. Пришлите код для повторного входа (<b>только кнопкой!</b>)",
                                                parse_mode=html, reply_markup=markup)
            await callback_query.message.delete()
            await telegram_clients[account_id].send_code_request(account['phone_number'])
            return await bot.send_message(OWNER, "Повторный вход...")
    await callback_query.message.edit_text(**await settings(callback_query.message.chat.id))


@dp.message(UserState.relogin)
@security('state')
async def _relogin(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer("Если вы считаете, что мы собираем какие-либо данные, то зайдите на наш сайт и "
                                    "посмотрите открытый исходный код бота, который постоянно обновляется в "
                                    "сторону улучшений и безопасности", reply_markup=ReplyKeyboardRemove())
    if message.content_type != "web_app_data":
        await state.clear()
        return await message.answer("Код можно отправлять только через кнопку! Telegram блокирует вход при отправке кода "
                                    "кому-либо. Попробуйте еще раз сначала (возможно придется подождать)",
                                    reply_markup=ReplyKeyboardRemove())
    code = unzip_int_data(message.web_app_data.data)
    account_id = message.chat.id
    phone_number = await db.fetch_one(f"SELECT phone_number FROM accounts WHERE id={account_id}", one_data=True)
    try:
        await telegram_clients[account_id].sign_in(phone=phone_number, code=code)
    except errors.SessionPasswordNeededError:
        await state.set_state(UserState.relogin_with_password)
        markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
        await message.answer("Оправьте пароль от вашего аккаунта, он нужен для работы Maksogram!", reply_markup=markup)
        await bot.send_message(OWNER, "Установлен облачный пароль")
    except (errors.PhoneCodeEmptyError,
            errors.PhoneCodeExpiredError,
            errors.PhoneCodeHashEmptyError,
            errors.PhoneCodeInvalidError):
        await message.answer("Неправильный код! Попробуйте еще раз (только кнопкой!) 👇")
        await bot.send_message(OWNER, "Неправильный код")
    except Exception as e:
        await message.answer("Произошла ошибка при попытке входа. Мы уже работает над ее решением!")
        await bot.send_message(OWNER, f"⚠️ Ошибка (sign_in) ⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
    else:
        await state.clear()
        await account_on(account_id, (admin_program if message.chat.id == OWNER else program).Program)
        await message.answer("Maksogram запущен!", reply_markup=ReplyKeyboardRemove())


@dp.message(UserState.relogin_with_password)
@security('state')
async def _relogin_with_password(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer("Если вы считаете, что мы собираем какие-либо данные, то зайдите на наш сайт и "
                                    "посмотрите открытый исходный код бота, который постоянно обновляется в "
                                    "сторону улучшений и безопасности", reply_markup=ReplyKeyboardRemove())
    if message.content_type != "text":
        return await message.answer("Отправьте пароль от вашего аккаунта")
    account_id = message.chat.id
    phone_number = await db.fetch_one(f"SELECT phone_number FROM accounts WHERE id={account_id}", one_data=True)
    try:
        await telegram_clients[account_id].sign_in(phone=phone_number, password=message.text)
    except errors.PasswordHashInvalidError:
        await message.answer("Пароль неверный, попробуйте снова!")
    except Exception as e:
        await message.answer("Произошла ошибка при попытке входа. Мы уже работает над ее решением!")
        await bot.send_message(OWNER, f"⚠️ Ошибка (sign_in) ⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
    else:
        await state.clear()
        await account_on(account_id, (admin_program if message.chat.id == OWNER else program).Program)
        await message.answer("Maksogram запущен!", reply_markup=ReplyKeyboardRemove())


@dp.message(UserState.send_phone_number)
@security('state')
async def _contact(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer("Если вы считаете, что мы собираем какие-либо данные, то зайдите на наш сайт и "
                                    "посмотрите открытый исходный код бота, который постоянно обновляется в "
                                    "сторону улучшений и безопасности", reply_markup=ReplyKeyboardRemove())
    if message.content_type != "contact":
        return await message.reply("Вы не отправили контакт!")
    if message.chat.id != message.contact.user_id:
        return await message.reply("Это не ваш номер! Пожалуйста, воспользуйтесь кнопкой")
    await state.set_state(UserState.send_code)
    phone_number = '+' + message.contact.phone_number
    telegram_client = new_telegram_client(phone_number)
    await state.update_data(telegram_client=telegram_client, phone_number=phone_number)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отправить код", web_app=WebAppInfo(url=f"https://tgmaksim.ru/maksogram/code"))],
                                           [KeyboardButton(text="Отмена")]], resize_keyboard=True)
    await message.answer("Осталось отправить код для входа (<b>только кнопкой!</b>). Напоминаю, что мы не собираем "
                         f"никаких данных, а по любым вопросам можете обращаться в @{support}", reply_markup=markup, parse_mode=html)
    await telegram_client.connect()
    await telegram_client.send_code_request(phone_number)


@dp.message(UserState.send_code)
@security('state')
async def _login(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer("Если вы считаете, что мы собираем какие-либо данные, то зайдите на наш сайт и "
                                    "посмотрите открытый исходный код бота, который постоянно обновляется в "
                                    "сторону улучшений и безопасности", reply_markup=ReplyKeyboardRemove())
    if message.content_type != "web_app_data":
        await state.clear()
        return await message.answer("Код можно отправлять только через кнопку! Telegram блокирует вход при отправке "
                                    "кому-либо. Попробуйте еще раз сначала (возможно придется подождать)",
                                    reply_markup=ReplyKeyboardRemove())
    code = unzip_int_data(message.web_app_data.data)
    data = await state.get_data()
    telegram_client: TelegramClient = data['telegram_client']
    phone_number: str = data['phone_number']
    try:
        await telegram_client.sign_in(phone=phone_number, code=code)
    except errors.SessionPasswordNeededError:
        await state.set_state(UserState.send_password)
        markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
        await message.answer("У вас установлен облачный пароль (двухфакторная аутентификация). Отправьте его мне", reply_markup=markup)
        await bot.send_message(OWNER, "Установлен облачный пароль")
    except (errors.PhoneCodeEmptyError,
            errors.PhoneCodeExpiredError,
            errors.PhoneCodeHashEmptyError,
            errors.PhoneCodeInvalidError):
        await message.answer("Неправильный код! Попробуйте еще раз (только кнопкой!) 👇")
        await bot.send_message(OWNER, "Неправильный код")
    except Exception as e:
        await message.answer("Произошла ошибка при попытке входа. Мы уже работает над ее решением!")
        await bot.send_message(OWNER, f"⚠️ Ошибка (sign_in) ⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
    else:
        await state.clear()
        loading = await message.answer_sticker("CAACAgIAAxkBAAIyQWeUrH2jAUkcqHGYerWNT3ySuFwbAAJBAQACzRswCPHwYhjf9pZYNgQ", reply_markup=ReplyKeyboardRemove())
        try:
            await start_program(message.chat.id, message.from_user.username, int(phone_number), telegram_client)
        except CreateChatsError as e:
            await loading.delete()
            await message.answer(e.args[0])
            await bot.send_message(OWNER, e.args[1])
        except Exception as e:
            await loading.delete()
            await message.answer("Произошла ошибка при создании необходимых чатов. Мы уже работает над ее решением")
            await bot.send_message(OWNER, f"⚠️ Ошибка (start_program) ⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
        else:
            await loading.delete()
            await message.answer("Maksogram запущен 🚀\nВ канале \"Мои сообщения\" будут храниться все ваши сообщения, в "
                                 "комментариях будет информация о прочтении, изменении и удалении. "
                                 "Можете попросить друга отправить вам сообщение и удалить его, чтобы убедиться, что все работает")
            await message.answer("Пробная подписка заканчивается через неделю, у вас есть время все опробовать")
            await bot.send_message(OWNER, "Создание чатов завершено успешно!")


@dp.message(UserState.send_password)
@security('state')
async def _login_with_password(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer("Если вы считаете, что мы собираем какие-либо данные, то зайдите на наш сайт и "
                                    "посмотрите открытый исходный код бота, который постоянно обновляется в "
                                    "сторону улучшений и безопасности", reply_markup=ReplyKeyboardRemove())
    if message.content_type != "text":
        return await message.answer("Отправьте пароль от вашего аккаунта")
    data = await state.get_data()
    telegram_client: TelegramClient = data['telegram_client']
    phone_number: str = data['phone_number']
    try:
        await telegram_client.sign_in(phone=phone_number, password=message.text)
    except errors.PasswordHashInvalidError:
        await message.answer("Пароль неверный, попробуйте снова!")
    except Exception as e:
        await state.clear()
        await message.answer("Произошла ошибка, обратитесь в поддержку...")
        await bot.send_message(OWNER, f"⚠️Ошибка⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
    else:
        await state.clear()
        loading = await message.answer_sticker("CAACAgIAAxkBAAIyQWeUrH2jAUkcqHGYerWNT3ySuFwbAAJBAQACzRswCPHwYhjf9pZYNgQ", reply_markup=ReplyKeyboardRemove())
        try:
            await start_program(message.chat.id, message.from_user.username, int(phone_number), telegram_client)
        except CreateChatsError as e:
            await loading.delete()
            await message.answer(e.args[0])
            await bot.send_message(OWNER, e.args[1])
        except Exception as e:
            await loading.delete()
            await message.answer("Произошла ошибка при создании необходимых чатов. Мы уже работает над ее решением")
            await bot.send_message(OWNER, f"⚠️ Ошибка (start_program) ⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
        else:
            await loading.delete()
            await message.answer("Maksogram запущен 🚀\nВ канале \"Мои сообщения\" будут храниться все ваши сообщения, в "
                                 "комментариях будет информация о прочтении, изменении и удалении. "
                                 "Можете попросить друга отправить вам сообщение и удалить его, чтобы убедиться, что все работает")
            await message.answer("Пробная подписка заканчивается через неделю, у вас есть время все опробовать")
            await message.answer(**await settings(message.chat.id))
            await bot.send_message(OWNER, "Создание чатов завершено успешно!")


@dp.callback_query()
@security()
async def _other_callback_query(callback_query: CallbackQuery):
    await new_callback_query(callback_query)


@dp.message()
@security()
async def _other_message(message: Message):
    if await new_message(message): return
    if await db.fetch_one(f"SELECT modules['calculator'] FROM accounts WHERE id={message.chat.id}", one_data=True) and \
            message.content_type == "text" and message.text[-1] == "=" and message.text.find("\n") == -1:
        return await message.answer("Калькулятор здесь не работает, вы можете пользоваться им в Избранном")


async def start_program(account_id: int, username: str, phone_number: int, telegram_client: TelegramClient):
    request = await create_chats(telegram_client)  # Создаем все нужные чаты, папки
    if request['result'] != "ok":
        raise CreateChatsError(request['message'], f"Произошла ошибка {request['error'].__class__.__name__}: {request['error']}")
    name = ('@' + username) if username else account_id
    next_payment = {'next_payment': int((time_now() + timedelta(days=7)).timestamp()), 'user': 'user', 'fee': Variables.fee}
    await db.execute(
        f"INSERT INTO accounts VALUES ({account_id}, '{name}', {phone_number}, {request['my_messages']}, "
        f"{request['message_changes']}, '[]', '[]', '{s1}{s2}', true, '{json_encode(next_payment)}', true, "
        f"'{s1}\"main\": 0, \"variants\": {s1}{s2}{s2}', '{s1}{s2}', '{s1}\"calculator\": false{s2}')")
    status_users = await db.fetch_all(f"SELECT key FROM accounts, jsonb_each(status_users) WHERE id={account_id} AND "
                                      "(value['online'] = 'true' OR value['offline'] = 'true');", one_data=True)
    telegram_clients[account_id] = telegram_client
    asyncio.get_running_loop().create_task(program.Program(telegram_client, account_id, status_users).run_until_disconnected())


def referal_link(user_id: int) -> str:
    return "r" + zip_int_data(user_id)


async def username_acquaintance(message: Message, default: Literal[None, 'first_name'] = None):
    id = message.chat.id
    user = await db.fetch_one(f"SELECT name FROM acquaintances WHERE id={id}", one_data=True)
    if user is not None or default != 'first_name':
        return user
    return message.from_user.first_name


async def developer_command(message: Message) -> bool:
    await new_message(message)
    if message.chat.id == OWNER:
        await message.answer("<b>Команда разработчика активирована!</b>", parse_mode=html)
    else:
        await message.answer("<b>Команда разработчика НЕ была активирована</b>", parse_mode=html)

    return message.chat.id != OWNER


async def new_message(message: Message, /, forward: bool = True) -> bool:
    if message.content_type == "text":
        content = message.text
    elif message.content_type == "web_app_data":
        content = message.web_app_data.data
    elif message.content_type == "contact":
        content = f"contact {message.contact.phone_number}"
    elif message.content_type == "users_shared":
        content = f"user {message.users_shared.user_ids[0]}"
    else:
        content = f"'{message.content_type}'"
    id = str(message.chat.id)
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    date = str(omsk_time(message.date))
    acquaintance = await username_acquaintance(message)
    acquaintance = f"<b>Знакомый: {acquaintance}</b>\n" if acquaintance else ""

    if message.chat.id == OWNER:
        return False

    if forward and message.content_type not in ("text", "web_app_data", "contact", "users_shared"):  # Если сообщение не является текстом, ответом mini app или контактом
        await bot.send_message(
            OWNER,
            text=f"ID: {id}\n"
                 f"{acquaintance}" +
                 (f"USERNAME: @{username}\n" if username else "") +
                 f"Имя: {escape(first_name)}\n" +
                 (f"Фамилия: {escape(last_name)}\n" if last_name else "") +
                 f"Время: {date}",
            parse_mode=html)
        await message.forward(OWNER)
    elif forward and (message.entities and message.entities[0].type != 'bot_command'):  # Сообщение с форматированием
        await bot.send_message(
            OWNER,
            text=f"ID: {id}\n"
                 f"{acquaintance}" +
                 (f"USERNAME: @{username}\n" if username else "") +
                 f"Имя: {escape(first_name)}\n" +
                 (f"Фамилия: {escape(last_name)}\n" if last_name else "") +
                 f"Время: {date}",
            parse_mode=html)
        await message.forward(OWNER)
    elif forward:
        await bot.send_message(
            OWNER,
            text=f"ID: {id}\n"
                 f"{acquaintance}" +
                 (f"USERNAME: @{username}\n" if username else "") +
                 f"Имя: {escape(first_name)}\n" +
                 (f"Фамилия: {escape(last_name)}\n" if last_name else "") +
                 (f"<code>{escape(content)}</code>\n"
                  if not content.startswith("/") or len(content.split()) > 1 else f"{escape(content)}\n") +
                 f"Время: {date}",
            parse_mode=html)

    return False


async def new_callback_query(callback_query: CallbackQuery) -> bool:
    id = str(callback_query.message.chat.id)
    username = callback_query.from_user.username
    first_name = callback_query.from_user.first_name
    last_name = callback_query.from_user.last_name
    callback_data = callback_query.data
    date = str(time_now())
    acquaintance = await username_acquaintance(callback_query.message)
    acquaintance = f"<b>Знакомый: {acquaintance}</b>\n" if acquaintance else ""

    if callback_query.from_user.id == OWNER:
        return False

    await bot.send_message(
        OWNER,
        text=f"ID: {id}\n"
             f"{acquaintance}" +
             (f"USERNAME: @{username}\n" if username else "") +
             f"Имя: {escape(first_name)}\n" +
             (f"Фамилия: {escape(last_name)}\n" if last_name else "") +
             f"CALLBACK_DATA: {callback_data}\n"
             f"Время: {date}",
        parse_mode=html)

    return False


async def check_payment_datetime():
    for account in await db.fetch_all("SELECT id, is_started, payment FROM accounts"):
        if not account['is_started'] or account['payment']['user'] != 'user': continue
        if account['payment']['next_payment'] <= (time_now() + timedelta(days=2)).timestamp():
            await bot.send_message(account['id'], "Текущая подписка заканчивается! Произведите следующий "
                                               "платеж до конца завтрашнего дня")
            await bot.send_message(account['id'], **await payment(account['id']))


async def start_bot():
    await check_payment_datetime()

    await bot.send_message(OWNER, f"<b>Бот запущен!🚀</b>", parse_mode=html)
    print("Запуск бота")
    await dp.start_polling(bot)
