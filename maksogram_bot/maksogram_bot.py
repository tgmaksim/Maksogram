import asyncio
import aiohttp

from typing import Literal
from datetime import timedelta
from sys_keys import TOKEN, release
from saving_messages import admin_program, program
from saving_messages.accounts import accounts, Account
from create_chats import create_chats, CreateChatsError
from core import (
    db,
    html,
    SITE,
    OWNER,
    channel,
    time_now,
    security,
    markdown,
    Variables,
    subscribe,
    omsk_time,
    get_users,
    json_encode,
    MaksogramBot,
    zip_int_data,
    resources_path,
    unzip_int_data,
    preview_options,
    get_telegram_client,
)

from telethon import errors
from aiogram import Bot, Dispatcher, F
from telethon.sync import TelegramClient
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from aiogram.filters.command import Command, CommandStart
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
    users = set()


# Класс нужен для определения состояния пользователя в данном боте,
# например: пользователь должен отправить отзыв в следующем сообщении
class UserState(StatesGroup):
    feedback = State('feedback')
    send_phone_number = State('send_phone_number')
    send_code = State('send_code')
    send_password = State('send_password')
    send_user = State('send_user')
    relogin = State('relogin')
    relogin_with_password = State('relogin_with_password')


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
    if await db.execute("SELECT id FROM acquaintances WHERE id=?", (id,)):
        await db.execute("UPDATE acquaintances SET name=? WHERE id=?", (name, id))
        await message.answer("Данные знакомого изменены")
    else:
        await db.execute("INSERT INTO acquaintances VALUES(?, ?)", (id, name))
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
                         "/db - база данных бота и программы\n"
                         "/version - изменить версию бота\n"
                         "/new_acquaintance - добавить знакомого")


@dp.message(Command('reload'))
@security()
async def _reload(message: Message):
    if await developer_command(message): return
    if release:
        await message.answer("*Перезапуск бота*", parse_mode=markdown)
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
    await message.answer("*Остановка бота и программы*", parse_mode=markdown)
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


@dp.message(Command('db'))
@security()
async def _db(message: Message):
    if await developer_command(message): return
    await message.answer_document(FSInputFile(resources_path(db.db_path)))


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


@dp.message(Command('payment'))
@security()
async def _payment(message: Message):
    if await new_message(message): return
    markup = IMarkup(inline_keyboard=[[IButton(text="TON", web_app=WebAppInfo(url="https://tgmaksim.ru/maksogram/payment/ton")),
                                       IButton(text="BTC", web_app=WebAppInfo(url="https://tgmaksim.ru/maksogram/payment/btc"))],
                                      [IButton(text="Перевод на карту (RUB)", web_app=WebAppInfo(url="https://tgmaksim.ru/maksogram/payment/fps"))],
                                      [IButton(text="Я отправил(а)  ✅", callback_data="send_payment")]])
    await bot.send_message(message.chat.id, "Отправляйте деньги, только если я вас попросил\nСпособы оплаты:\n"
                                            "СБП: (150 руб)\n"
                                            "BTC: (0.00002 btc)\n"
                                            "TON: (0.25 ton)",
                           parse_mode=html, reply_markup=markup)


@dp.callback_query(F.data == "send_payment")
@security()
async def _send_payment(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account = accounts[callback_query.from_user.id]
    markup = IMarkup(inline_keyboard=[[IButton(text="Подтвердить! ✅", callback_data=f"confirm_sending_payment{account.id}_{callback_query.message.message_id}")]])
    await bot.send_message(OWNER, f"Пользователь {account.name} отправил оплату, проверь это! Если так, то подтверди, "
                                  "чтобы я продлил подписку на месяц", reply_markup=markup)
    await callback_query.answer("Запрос отправлен. Ожидайте!", True)


@dp.callback_query(F.data.startswith("confirm_sending_payment"))
@security()
async def _confirm_sending_payment(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    if callback_query.from_user.id != OWNER:
        return await callback_query.answer("Ошибка!", True)
    user_id, message_id = map(int, callback_query.data.replace("confirm_sending_payment", "").split("_"))
    account = accounts[user_id]
    await account.set_status_payment(True, timedelta(days=30))
    await bot.edit_message_reply_markup(chat_id=user_id, message_id=message_id)
    await bot.send_message(user_id, f"Ваша оплата подтверждена! Следующий платеж "
                                    f"{account.payment.next_payment.strftime('%Y/%m/%d')}\n/start_prog - запустить программу",
                           reply_to_message_id=message_id)
    await callback_query.message.edit_text(callback_query.message.text + '\n\nУспешно!')


@dp.message(Command('version'))
@security()
async def _version(message: Message):
    if await new_message(message): return
    version = Variables.version
    await message.answer(f"Версия: {version}\n<a href='{SITE}/{version}'>Обновление</a> 👇",
                         parse_mode=html, link_preview_options=preview_options(version))


@dp.callback_query(F.data == 'subscribe')
@security()
async def _check_subscribe(callback_query: CallbackQuery):
    if await new_callback_query(callback_query, check_subscribe=False): return
    if (await bot.get_chat_member(channel, callback_query.message.chat.id)).status == 'left':
        await callback_query.answer("Вы не подписались на наш канал😢", True)
        await callback_query.bot.send_message(OWNER, "Пользователь не подписался на канал")
    else:
        await callback_query.message.delete()
        await callback_query.answer("Спасибо за подписку!❤️ Продолжайте пользоваться ботом", True)
        await callback_query.bot.send_message(OWNER, "Пользователь подписался на канал. Ему предоставлен полный доступ")


@dp.message(CommandStart())
@security('state')
async def _start(message: Message, state: FSMContext):
    if await new_message(message): return
    await state.clear()
    await (await message.answer("...Удаление клавиатурных кнопок...", reply_markup=ReplyKeyboardRemove())).delete()
    markup = IMarkup(inline_keyboard=[[IButton(text="Мои функции", callback_data="help")]])
    await message.answer(f"Привет, {await username_acquaintance(message, 'first_name')}\n"
                         f"[tgmaksim.ru]({SITE})",
                         parse_mode=markdown, reply_markup=markup, link_preview_options=preview_options())
    if message.text.startswith('/start r'):
        friend_id = unzip_int_data(message.text.replace('/start r', ''))
        await bot.send_message(friend_id, "По вашей реферальной ссылке зарегистрировался новый пользователь. Если он "
                                          "оплатит подписку, то вы получите скидку 20% (действует только при оплате по СБП)")
        await bot.send_message(OWNER, f"Регистрация по реферальной ссылке #r{friend_id}")
    elif message.text.startswith('/start du'):
        user_id = int(message.text.replace('/start du', ''))
        request = await accounts[message.chat.id].remove_status_user(user_id)
        match request:
            case 1:
                await message.answer("Такого пользователя нет в отслеживаемых")
            case _:
                await message.answer("Пользователь удален из отслеживаемых #s")


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
    await message.answer("/stop_prog - остановка программы\n"
                         "/start_prog - запуск программы\n"
                         "/check - проверить программу\n"
                         "/feedback - оставить отзыв или предложение\n"
                         "/conditions - условия пользования\n"
                         "/memo - памятка по работе\n"
                         "/friends - реферальная программа\n"
                         f"<a href='{SITE}'>tgmaksim.ru</a>", parse_mode=html, link_preview_options=preview_options())


@dp.message(Command('conditions'))
@security()
async def _conditions(message: Message):
    if await new_message(message): return
    await message.answer("Условия пользования\n")


@dp.message(Command('memo'))
@security()
async def _memo(message: Message):
    if await new_message(message): return
    await message.answer("Памятка по работе\n")


@dp.message(Command('friends'))
@security()
async def _friends(message: Message):
    if await new_message(message): return
    await message.answer(
        "*Реферальная программа\n*"
        "1) ваш друг оплатил подписку на месяц\n"
        "2) вы оплатили подписку на месяц\n"
        "При выполнении всех условий вам возвращается 20% от стоимости. "
        "Пригласить друга можно, отправив сообщение 👇", parse_mode=markdown)
    markup = IMarkup(inline_keyboard=[[IButton(text="Попробовать бесплатно",
                                               url=f"t.me/{MaksogramBot.username}?start={referal_link(message.chat.id)}")]])
    await message.answer_photo(
        FSInputFile(resources_path("logo.jpg")),
        f"Привет! Я хочу тебе посоветовать отличного [бота](t.me/{MaksogramBot.username}?start={referal_link(message.chat.id)}). "
        "Он сохранит все твои сообщения и подскажет, когда кто-то их удалит, изменит, прочитает или поставит реакцию. "
        "Также в нем есть множество других полезных функций", parse_mode=markdown, reply_markup=markup, disable_web_page_preview=True)


@dp.message(Command('status_user'))
@security('state')
async def _status_user(message: Message, state: FSMContext):
    if await new_message(message): return
    request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Выбрать", request_users=request_users)],
                                           [KeyboardButton(text="Отмена")]], resize_keyboard=True)
    await message.answer("Данная функция позволяет следить за статусом вашего друга. Если она включена, то я напишу, "
                         "когда выбранный вами человек появится в сети или выйдет из нее. Не работает, если собеседник "
                         "скрыл для вас время последнего захода...\nОтправьте нужного человека", reply_markup=markup)
    await state.set_state(UserState.send_user)


@dp.message(Command('stop_prog'))
@security()
async def _stop_prog(message: Message):
    if await new_message(message): return
    is_started = await db.execute("SELECT is_started FROM accounts WHERE id=?", (message.chat.id,))
    if not is_started:
        return await message.answer("Вы не подключали программу ранее!\n/start_prog - подключить")
    if is_started[0][0] == 0:
        return await message.answer("Ваша программа и так остановлена\n/start_prog - запустить")


@dp.message(Command('start_prog'))
@security('state')
async def _start_prog(message: Message, state: FSMContext):
    if await new_message(message): return
    is_started = await db.execute("SELECT is_started FROM accounts WHERE id=?", (message.chat.id,))
    if is_started and is_started[0][0] == 1:
        return await message.answer("На вашем аккаунте уже включена программа\n/stop_prog - выключить")
    elif is_started and is_started[0][0] == 0:
        account = accounts[message.chat.id]
        if not account.is_paid:
            await message.answer("Ваш платеж просрочен. Программа остановлена. Отправьте нужную сумму или напишите "
                                 "отзыв, если произошла ошибка. Во всем разберемся!")
            await bot.send_message(OWNER, f"Платеж просрочен. Программа не запущена ({account.name})")
            return
        telegram_client = get_telegram_client(account.phone)
        await telegram_client.connect()
        if not await telegram_client.is_user_authorized():
            await telegram_client.send_code_request(account.phone)
            await bot.send_message(OWNER, "Повторный вход...")
            await state.set_state(UserState.relogin)
            await state.update_data(telegram_client=telegram_client)
            markup = ReplyKeyboardMarkup(keyboard=[[
                KeyboardButton(text="Отправить код", web_app=WebAppInfo(url="https://tgmaksim.ru/maksogram/code"))],
                [KeyboardButton(text="Отмена")]], resize_keyboard=True)
            return await message.answer("Вы удалили сессию Telegram, программа больше не имеет доступа к вашему аккаунту. "
                                        "Пришлите код для повторного входа", reply_markup=markup)
        await account.on()
        await message.answer("Есть контакт! Можете проверить командой /check")
        if message.chat.id == OWNER:
            asyncio.get_running_loop().create_task(admin_program.Program(telegram_client, account.id).run_until_disconnected())
        else:
            asyncio.get_event_loop().create_task(program.Program(telegram_client, account.id).run_until_disconnected())
    else:
        markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отправить номер телефона", request_contact=True)],
                                               [KeyboardButton(text="Отмена")]], resize_keyboard=True)
        await state.set_state(UserState.send_phone_number)
        await message.answer(
            f"Перед тем, как подключить программу, прочитайте [условия пользования](t.me/{MaksogramBot.username}?start=conditions). "
            "Если вы с ними согласны, то можете нажать на кнопку подключить\n\n",
            parse_mode=markdown, reply_markup=markup, disable_web_page_preview=True)


@dp.message(UserState.relogin)
@security('state')
async def _relogin(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer("Если вы считаете, что мы собираем какие-либо данные, то зайдите на наш сайт и "
                                    "посмотрите открытый исходный код программы, который постоянно обновляется в "
                                    "сторону улучшений и безопасности", reply_markup=ReplyKeyboardRemove())
    if message.content_type != "web_app_data":
        await state.clear()
        return await message.answer("Код можно отправлять только через кнопку!", reply_markup=ReplyKeyboardRemove())
    code = unzip_int_data(message.web_app_data.data)
    telegram_client: TelegramClient = (await state.get_data())['telegram_client']
    try:
        await telegram_client.sign_in(phone=accounts[message.chat.id].phone, code=code)
    except errors.SessionPasswordNeededError:
        await state.set_state(UserState.relogin_with_password)
        markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
        await message.answer("Оправьте пароль от вашего аккаунта, он нужен для работы программы!", reply_markup=markup)
    except (errors.PhoneCodeEmptyError,
            errors.PhoneCodeExpiredError,
            errors.PhoneCodeHashEmptyError,
            errors.PhoneCodeInvalidError):
        await message.answer("Неправильный код! Попробуйте еще раз или нажмите Отмена")
        await bot.send_message(OWNER, "Неправильный код")
    else:
        await state.clear()
        await message.answer("Есть контакт! Можете проверить командой /check", reply_markup=ReplyKeyboardRemove())
        account = accounts[message.chat.id]
        await account.on()
        if message.chat.id == OWNER:
            asyncio.get_running_loop().create_task(
                admin_program.Program(telegram_client, account.id).run_until_disconnected())
        else:
            asyncio.get_event_loop().create_task(program.Program(telegram_client, account.id).run_until_disconnected())


@dp.message(UserState.relogin_with_password)
@security('state')
async def _relogin_with_password(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer("Возвращайтесь скорее!", reply_markup=ReplyKeyboardRemove())
    if message.content_type != "text":
        return await message.answer("Отправьте пароль от вашего аккаунта")
    telegram_client: TelegramClient = (await state.get_data())['telegram_client']
    try:
        await telegram_client.sign_in(phone=accounts[message.chat.id].phone, password=message.text)
    except errors.PasswordHashInvalidError:
        await message.answer("Пароль неверный, попробуйте снова!")
    else:
        await state.clear()
        await message.answer("Есть контакт! Можете проверить командой /check", reply_markup=ReplyKeyboardRemove())
        account = accounts[message.chat.id]
        await account.on()
        if message.chat.id == OWNER:
            asyncio.get_running_loop().create_task(
                admin_program.Program(telegram_client, account.id).run_until_disconnected())
        else:
            asyncio.get_event_loop().create_task(program.Program(telegram_client, account.id).run_until_disconnected())


@dp.message(UserState.send_user)
@security('state')
async def _send_user(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer("Как понадобиться, обращайтесь", reply_markup=ReplyKeyboardRemove())
    if message.content_type != 'users_shared':
        return await message.answer("Вы не отправили пользователя! Отправьте или нажмите Отмена")
    user_id = message.users_shared.user_ids[0]
    await state.clear()
    request = await accounts[message.chat.id].add_status_users(user_id)
    match request:
        case 1:
            await message.answer("Себя нельзя!", reply_markup=ReplyKeyboardRemove())
        case 2:
            await message.answer(f"Уже есть! Для удаления [нажмите](t.me/{MaksogramBot.username}?start=du{user_id})",
                                 reply_markup=ReplyKeyboardRemove(), parse_mode=markdown, disable_web_page_preview=True)
        case _:
            await message.answer("Пользователь добавлен! Теперь если друг изменит статус, то я оповещу об этом\n"
                                 f"<a href='t.me/{MaksogramBot.username}?start=du{user_id}'>Отключить для него</a> #s",
                                 parse_mode=html, disable_web_page_preview=True, reply_markup=ReplyKeyboardRemove())


@dp.message(UserState.send_phone_number)
@security('state')
async def _contact(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer("Вы всегда можете подключить программу у меня", reply_markup=ReplyKeyboardRemove())
    if message.content_type != "contact":
        return await message.answer("Вы не отправили контакт!")
    if message.chat.id != message.contact.user_id:
        return await message.answer("Это не ваш номер! Пожалуйста, воспользуйтесь кнопкой")
    await message.reply("Номер принят", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        "*Важно!*\nСим-карта с номером телефона, к которому привязан аккаунт, должна быть у вас в доступе. Иначе вы "
        "можете потерять доступ к Telegram. Если вы владеете данной сим-картой, то никаких рисков нет", parse_mode=markdown)
    await state.set_state(UserState.send_code)
    phone_number = '+' + message.contact.phone_number
    telegram_client = get_telegram_client(phone_number)
    await state.update_data(telegram_client=telegram_client, phone_number=phone_number)
    if not telegram_client.is_connected():
        await telegram_client.connect()
    if await telegram_client.is_user_authorized():
        await telegram_client.log_out()
    await telegram_client.send_code_request(phone_number)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Запустить сохранение сообщений",
                                                           web_app=WebAppInfo(url=f"https://tgmaksim.ru/maksogram/code"))],
                                           [KeyboardButton(text="Отмена")]], resize_keyboard=True)
    await message.answer("Осталось ввести код для входа. Напоминаю, что мы не собираем никаких данных, а исходный "
                         "код открыт и находится в общем доступе", reply_markup=markup)


@dp.message(UserState.send_code)
@security('state')
async def _login(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer("Вы всегда можете подключить программу у меня", reply_markup=ReplyKeyboardRemove())
    if message.content_type != "web_app_data":
        await state.clear()
        return await message.answer("Вы должны отправить код, только используя кнопку снизу...\n"
                                    "/start_prog - начать заново", reply_markup=ReplyKeyboardRemove())
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
        await message.answer("Неправильный код! Попробуйте еще раз или нажмите Отмена")
        await bot.send_message(OWNER, "Неправильный код")
    else:
        await state.clear()
        await message.answer("Началась настройка программы... Пожалуйста, подождите", reply_markup=ReplyKeyboardRemove())
        try:
            await start_program(message.chat.id, message.from_user.username, message.contact.phone_number, telegram_client, None)
        except Exception as e:
            await message.answer("Произошла ошибка, обратитесь в поддержку...")
            await bot.send_message(OWNER, f"⚠️Ошибка⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
        else:
            await message.answer(f"Следующий платеж ({Variables.fee}) руб через неделю")
            await message.answer("Настройка завершена успешно! Вернитесь назад и посмотрите, что изменилось. "
                                 "Можете попросить друга отправить вам сообщение и удалить его, чтобы убедиться, что все работает")
            await bot.send_message(OWNER, "Создание чатов завершено успешно!")


@dp.message(UserState.send_password)
@security('state')
async def _login_with_password(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer(f"Зайдите на наш [сайт]({SITE}) и убедитесь, что исходный код всего проекта открыт. "
                                    "Ждем вас в ближайшее время...", link_preview_options=preview_options())
    if message.content_type != "text":
        return await message.answer("Отправьте ваш облачный пароль (текст)")
    data = await state.get_data()
    telegram_client: TelegramClient = data['telegram_client']
    phone_number = data['phone_number']
    password = message.text
    try:
        await telegram_client.sign_in(phone=phone_number, password=password)
    except errors.PasswordHashInvalidError:
        await state.clear()
        await message.answer("Неправильный пароль\n/start_prog - начать сначала", reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        await state.clear()
        await message.answer("Произошла ошибка, обратитесь в поддержку...")
        await bot.send_message(OWNER, f"⚠️Ошибка⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
    else:
        await state.clear()
        await message.answer("Началась настройка программы... Пожалуйста, подождите", reply_markup=ReplyKeyboardRemove())
        try:
            await start_program(message.chat.id, message.from_user.username, phone_number, telegram_client, password)
        except CreateChatsError:
            pass
        except Exception as e:
            await message.answer("Произошла ошибка, обратитесь в поддержку...")
            await bot.send_message(OWNER, f"⚠️Ошибка⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
        else:
            await message.answer(f"Следующий платеж ({Variables.fee}) руб через неделю")
            await message.answer("Настройка завершена успешно! Вернитесь назад и посмотрите, что изменилось. "
                                 "Можете попросить друга отправить вам сообщение и удалить его, чтобы убедиться, что все работает")
            await bot.send_message(OWNER, "Создание чатов завершено успешно!")


@dp.callback_query()
@security()
async def _other_callback_query(callback_query: CallbackQuery):
    await new_callback_query(callback_query)


@dp.message()
@security()
async def _other_message(message: Message):
    if await new_message(message): return


async def start_program(user_id: int, username: str, phone_number: str, telegram_client: TelegramClient, password):
    request = await create_chats(telegram_client)  # Создаем все нужные чаты, папки, запускаем бота
    if request['result'] != "ok":
        await bot.send_message(user_id, request['message'])
        await bot.send_message(OWNER, f"Произошла ошибка {request['error'].__class__.__name__}: {request['error']}")
        raise CreateChatsError()
    name = '@' + username if username else user_id
    next_payment = {'next_payment': (time_now() + timedelta(days=7)).strftime("%Y/%m/%d"), 'user': 'user', 'fee': Variables.fee}
    await db.execute("INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (name, user_id, password, phone_number, request['my_messages'], request['message_changes'], '[]', '[]', '[]', 1, json_encode(next_payment), 1))
    account = Account(name, user_id, password, phone_number, request['my_messages'],
                      request['message_changes'], [], [], [], '1', next_payment, '1')
    asyncio.get_running_loop().create_task(program.Program(telegram_client, account.id).run_until_disconnected())


def referal_link(user_id: int) -> str:
    return "r" + zip_int_data(user_id)


async def new_user(message: Message):
    if not await db.execute("SELECT id FROM users WHERE id=?", (str(message.chat.id),)):
        await db.execute("INSERT INTO users VALUES(?, ?)", (message.chat.id, ""))
        Data.users.add(message.chat.id)
    await db.execute("UPDATE users SET last_message=? WHERE id=?", (str(omsk_time(message.date)), message.chat.id))


async def username_acquaintance(message: Message, default: Literal[None, 'first_name'] = None):
    id = message.chat.id
    user = await db.execute("SELECT name FROM acquaintances WHERE id=?", (id,))
    if user:
        return user[0][0]
    return message.from_user.first_name if default == 'first_name' else None


async def developer_command(message: Message) -> bool:
    await new_message(message)
    if message.chat.id == OWNER:
        await message.answer("*Команда разработчика активирована!*", parse_mode=markdown)
    else:
        await message.answer("*Команда разработчика НЕ была активирована*", parse_mode=markdown)

    return message.chat.id != OWNER


async def subscribe_to_channel(id: int, text: str = ""):
    if (await bot.get_chat_member(channel, id)).status == 'left' and not text.startswith('/start'):
        markup = IMarkup(
            inline_keyboard=[[IButton(text="Подписаться на канал", url=subscribe)],
                             [IButton(text="Подписался", callback_data="subscribe")]])
        await bot.send_message(id, "Бот работает только с подписчиками моего канала. "
                                   "Подпишитесь и получите полный доступ к боту", reply_markup=markup)
        await bot.send_message(OWNER, "Пользователь не подписан на наш канал, доступ ограничен!")
        return False
    return True


async def new_message(message: Message, /, forward: bool = True) -> bool:
    if message.content_type == "text":
        content = message.text
    elif message.content_type == "web_app_data":
        content = message.web_app_data.data
    elif message.content_type == "contact":
        content = f"contact {message.contact.phone_number}"
    else:
        content = f"'{message.content_type}'"
    id = str(message.chat.id)
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    date = str(omsk_time(message.date))
    acquaintance = await username_acquaintance(message)
    acquaintance = f"<b>Знакомый: {acquaintance}</b>\n" if acquaintance else ""

    await db.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)",
                     (id, username, first_name, last_name, content, date))

    if message.chat.id == OWNER:
        return False

    if forward and message.content_type not in ("text", "web_app_data", "contact"):  # Если сообщение не является текстом, ответом mini app или контактом
        await bot.send_message(
            OWNER,
            text=f"ID: {id}\n"
                 f"{acquaintance}" +
                 (f"USERNAME: @{username}\n" if username else "") +
                 f"Имя: {first_name}\n" +
                 (f"Фамилия: {last_name}\n" if last_name else "") +
                 f"Время: {date}",
            parse_mode=html)
        await message.forward(OWNER)
    elif forward and (message.entities and message.entities[0].type != 'bot_command'):  # Сообщение с форматированием
        await bot.send_message(
            OWNER,
            text=f"ID: {id}\n"
                 f"{acquaintance}" +
                 (f"USERNAME: @{username}\n" if username else "") +
                 f"Имя: {first_name}\n" +
                 (f"Фамилия: {last_name}\n" if last_name else "") +
                 f"Время: {date}",
            parse_mode=html)
        await message.forward(OWNER)
    elif forward:
        try:
            await bot.send_message(
                OWNER,
                text=f"ID: {id}\n"
                     f"{acquaintance}" +
                     (f"USERNAME: @{username}\n" if username else "") +
                     f"Имя: {first_name}\n" +
                     (f"Фамилия: {last_name}\n" if last_name else "") +
                     (f"<code>{content}</code>\n"
                      if not content.startswith("/") or len(content.split()) > 1 else f"{content}\n") +
                     f"Время: {date}",
                parse_mode=html)
        except:
            await bot.send_message(
                OWNER,
                text=f"ID: {id}\n"
                     f"{acquaintance}" +
                     (f"USERNAME: @{username}\n" if username else "") +
                     f"Имя: {first_name}\n" +
                     (f"Фамилия: {last_name}\n" if last_name else "") +
                     f"<code>{content}</code>\n"
                     f"Время: {date}",
                parse_mode=html)
            await message.forward(OWNER)

    if message.chat.id not in Data.users:
        await message.forward(OWNER)
    await new_user(message)

    return not await subscribe_to_channel(message.chat.id, message.text)


async def new_callback_query(callback_query: CallbackQuery, /, check_subscribe: bool = True) -> bool:
    id = str(callback_query.message.chat.id)
    username = callback_query.from_user.username
    first_name = callback_query.from_user.first_name
    last_name = callback_query.from_user.last_name
    callback_data = callback_query.data
    date = str(time_now())
    acquaintance = await username_acquaintance(callback_query.message)
    acquaintance = f"<b>Знакомый: {acquaintance}</b>\n" if acquaintance else ""

    await db.execute("INSERT INTO callbacks_query VALUES (?, ?, ?, ?, ?, ?)",
                     (id, username, first_name, last_name, callback_data, date))

    if callback_query.from_user.id != OWNER:
        await bot.send_message(
            OWNER,
            text=f"ID: {id}\n"
                 f"{acquaintance}" +
                 (f"USERNAME: @{username}\n" if username else "") +
                 f"Имя: {first_name}\n" +
                 (f"Фамилия: {last_name}\n" if last_name else "") +
                 f"CALLBACK_DATA: {callback_data}\n"
                 f"Время: {date}",
            parse_mode=html)

    if check_subscribe and not await subscribe_to_channel(callback_query.from_user.id):
        await callback_query.message.edit_reply_markup()
        return True
    return False


async def check_payment_datetime():
    users: list[Account] = list(map(lambda account: account if account.on else None, Account.get_accounts()))
    for user in users:
        if not user: continue
        if user.is_started and user.payment.user != 'admin' and \
                user.payment.next_payment.strftime("%Y/%m/%d") == (time_now() + timedelta(days=2)).strftime("%Y/%m/%d"):
            markup = IMarkup(
                inline_keyboard=[[IButton(text="TON", web_app=WebAppInfo(url="https://tgmaksim.ru/maksogram/payment/ton")),
                                  IButton(text="BTC", web_app=WebAppInfo(url="https://tgmaksim.ru/maksogram/payment/btc"))],
                                 [IButton(text="Перевод на карту (RUB)", web_app=WebAppInfo(url="https://tgmaksim.ru/maksogram/payment/fps"))],
                                 [IButton(text="Я отправил(а)  ✅", callback_data="send_payment")]])
            await bot.send_message(user.id, "Текущая подписка заканчивается! Произведите следующий платеж до "
                                            "конца завтрашнего дня\nСпособы оплаты:\n"
                                            "СБП: (150 руб)\n"
                                            "BTC: (0.00002 btc)\n"
                                            "TON: (0.25 ton)",
                                   parse_mode=html, reply_markup=markup)


async def start_bot():
    await db.execute("CREATE TABLE IF NOT EXISTS messages (id TEXT, username TEXT, first_name TEXT, last_name TEXT, "
                     "message_text TEXT, datetime TEXT)")
    await db.execute("CREATE TABLE IF NOT EXISTS callbacks_query (id TEXT, username TEXT, first_name TEXT, "
                     "last_name TEXT, callback_data TEXT, datetime TEXT)")
    await db.execute("CREATE TABLE IF NOT EXISTS system_data (key TEXT, value TEXT)")
    await db.execute("CREATE TABLE IF NOT EXISTS acquaintances (id TEXT, username TEXT, first_name TEXT, "
                     "last_name TEXT, name TEXT)")
    await db.execute("CREATE TABLE IF NOT EXISTS users (id TEXT, last_message TEXT)")
    if not await db.execute("SELECT value FROM system_data WHERE key=?", ("version",)):
        await db.execute("INSERT INTO system_data VALUES(?, ?)", ("version", "0.0"))

    Data.users = await get_users()
    await check_payment_datetime()

    await bot.send_message(OWNER, f"*Бот запущен!🚀*", parse_mode=markdown)
    print("Запуск бота")
    await dp.start_polling(bot)
