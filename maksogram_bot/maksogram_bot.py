import asyncio
import aiohttp

from html import escape
from datetime import timedelta
from typing import Literal, Any
from sys_keys import TOKEN, release
from saving_messages import admin_program, program
from create_chats import create_chats, CreateChatsError
from saving_messages.accounts import accounts, Account, UserIsNotAuthorized
from core import (
    db,
    html,
    SITE,
    OWNER,
    channel,
    support,
    time_now,
    security,
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
    users = set()
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
    send_user = State('send_user')
    relogin = State('relogin')
    relogin_with_password = State('relogin_with_password')
    answering_machine = State('answering_machine')
    answering_machine_edit = State('answering_machine_edit')


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


@dp.message(Command('db'))
@security()
async def _db(message: Message):
    if await developer_command(message): return
    await message.answer_document(FSInputFile(resources_path(db.db_path)))


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
    result = [len(accounts), 0, 0, 0]
    for account in accounts.values():
        if account.is_started:
            result[1] += 1  # Количество активных пользователей
            try:
                await fun(account.id)
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
    account = accounts[callback_query.from_user.id]
    markup = IMarkup(inline_keyboard=[[IButton(text="Подтвердить! ✅", callback_data=f"confirm_sending_payment{account.id}_{callback_query.message.message_id}")]])
    await bot.send_message(OWNER, f"Пользователь {account.name} отправил оплату, проверь это! Если так, то подтверди, "
                                  "чтобы я продлил подписку на месяц", reply_markup=markup)
    await callback_query.answer("Запрос отправлен. Ожидайте!", True)


def payment(user_id: int) -> dict[str, Any]:
    account = accounts[user_id]
    markup = IMarkup(inline_keyboard=[[IButton(text="TON", web_app=WebAppInfo(url=f"{Data.web_app}/payment/ton")),
                                       IButton(text="BTC", web_app=WebAppInfo(url=f"{Data.web_app}/payment/btc"))],
                                      [IButton(text="Перевод по номеру", web_app=WebAppInfo(url=f"{Data.web_app}/payment/fps"))],
                                      [IButton(text="Я отправил(а)  ✅", callback_data="send_payment")]])
    return {"text": f"Способы оплаты:\nСбер: ({account.payment.fee} руб)\nBTC: (0.00002 btc)\nTON: (0.25 ton)",
            "parse_mode": html, "reply_markup": markup}


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
                                    f"{account.payment.next_payment.strftime('%Y/%m/%d')}", reply_to_message_id=message_id)
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
    service_message = await message.answer("...", reply_markup=ReplyKeyboardRemove())
    if message.text.startswith('/start r'):
        friend_id = unzip_int_data(message.text.replace('/start r', ''))
        if message.chat.id == friend_id:
            return await message.answer("Вы не можете зарегистрироваться по своей реферальной ссылке!")
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
    await message.answer(**settings(message.chat.id))


@dp.callback_query(F.data == "settings")
async def _settings_button(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**settings(callback_query.message.chat.id))


def settings(user_id: int) -> dict[str, Any]:
    status = accounts[user_id].is_started if accounts.get(user_id) else None
    if status is None:
        markup = IMarkup(inline_keyboard=[[IButton(text="🟢 Включить Maksogram", callback_data="registration")],
                                          [IButton(text="ℹ️ Узнать все возможности", url=SITE)]])
    elif status is False:
        markup = IMarkup(inline_keyboard=[[IButton(text="🟢 Включить Maksogram", callback_data="on")],
                                          [IButton(text="ℹ️ Памятка по всем функциям", url=SITE)]])
    else:
        markup = IMarkup(inline_keyboard=[[IButton(text="🔴 Выключить Maksogram", callback_data="off")],
                                          [IButton(text="⏳ Отложенное сообщение", callback_data="delayed_message")],
                                          [IButton(text="🌐 Друг в сети", callback_data="update_friend_status"),
                                           IButton(text="🤖 Автоответчик", callback_data="answering_machine"),
                                           ],  # IButton(text="📸 Аватарка", callback_data="update_profile_avatar")
                                          [IButton(text="ℹ️ Узнать все возможности", url=SITE)]])
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


@dp.callback_query(F.data == "delayed_message")
@security()
async def _delayed_message(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.answer("Функция в разработке", True)


@dp.callback_query(F.data == "update_friend_status")
@security('state')
async def _update_friend_status(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Выбрать", request_users=request_users)],
                                           [KeyboardButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer(
        "🌐 <b>Друг в сети</b>\nДанная функция позволяет следить за статусом вашего знакомого. Если она включена, "
        "то я напишу, когда пользователь появится в сети или выйдет из нее. Не работает, если собеседник "
        "скрыл для вас время последнего захода...\nОтправьте нужного человека", reply_markup=markup, parse_mode=html)).message_id
    await state.set_state(UserState.send_user)
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.send_user)
@security('state')
async def _send_user(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    if message.text == "Отмена":
        await message.answer(**settings(message.chat.id))
        return await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])
    if message.content_type != 'users_shared':
        return await message.answer("Вы не отправили пользователя! Отправьте или нажмите Отмена")
    user_id = message.users_shared.user_ids[0]
    request = await accounts[message.chat.id].add_status_users(user_id)
    match request:
        case 1:
            await message.answer("Себя нельзя!", reply_markup=ReplyKeyboardRemove())
        case 2:
            await message.answer(f"Уже есть! Для удаления <a href='tg://resolve?domain={MaksogramBot.username}&start=du{user_id}'>"
                                 "нажмите</a>", reply_markup=ReplyKeyboardRemove(), parse_mode=html, disable_web_page_preview=True)
        case _:
            await message.answer("Пользователь добавлен! Теперь если пользователь изменит статус, то я оповещу об этом\n"
                                 f"<a href='tg://resolve?domain={MaksogramBot.username}&start=du{user_id}'>Отключить для него</a> #s",
                                 parse_mode=html, disable_web_page_preview=True, reply_markup=ReplyKeyboardRemove())


@dp.callback_query(F.data == "answering_machine")
@security()
async def _answering_machine(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**answering_machine(callback_query.message.chat.id))


def answering_machine(user_id: int) -> dict[str, Any]:
    buttons = []
    main = accounts[user_id].answering_machine.main
    for answer in accounts[user_id].answering_machine:
        text = (answer.text[:30] + "...") if len(answer.text) > 30 else answer.text
        indicator = "🟢" if main == answer.id else ""
        buttons.append([IButton(text=f"{indicator} {text}", callback_data=f"answering_machine_menu{answer.id}")])
    buttons.append([IButton(text="Создать новый ответ", callback_data="new_answering_machine")])
    buttons.append([IButton(text="◀️  Назад", callback_data="settings")])
    markup = IMarkup(inline_keyboard=buttons)
    return {"text": "🤖 <b>Автоответчик</b>\nЗдесь хранятся все ваши автоматические ответы. Вы можете включить нужный, "
                    "удалить, изменить или добавить новый", "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data == "new_answering_machine")
@security('state')
async def _new_answering_machine(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    if len(accounts[callback_query.message.chat.id].answering_machine) >= 5:
        return await callback_query.answer("У вас максимальное количество автоответов", True)
    await state.set_state(UserState.answering_machine)
    markup = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Напишите <b>текст</b>, который я отправлю в случае необходимости",
                                                      parse_mode=html, reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.answering_machine)
@security('state')
async def _answering_machine(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    if message.text != "Отмена":
        accounts[message.chat.id].answering_machine.append(message.text, message.entities or [])
        await db.execute("UPDATE accounts SET answering_machine=? WHERE id=?",
                         (accounts[message.chat.id].answering_machine.json(), message.chat.id))
    await message.answer(**answering_machine(message.chat.id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data.startswith("answering_machine_menu"))
@security()
async def _answering_machine_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_menu", ""))
    await callback_query.message.edit_text(**auto_answer(callback_query.message.chat.id, answer_id))


def auto_answer(user_id: int, answer_id: int):
    account = accounts[user_id]
    answer = account.answering_machine[answer_id]
    if answer is None:
        return answering_machine(user_id)
    status = account.answering_machine.main == answer_id
    status_button = IButton(text="🔴 Выключить автоответ", callback_data=f"answering_machine_off{answer_id}") if status else \
        IButton(text="🟢 Включить автоответ", callback_data=f"answering_machine_on{answer_id}")
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="✏️ Изменить текст", callback_data=f"answering_machine_edit{answer_id}")],
                                      [IButton(text="🚫 Удалить автоответ", callback_data=f"answering_machine_del{answer_id}")],
                                      [IButton(text="◀️  Назад", callback_data="answering_machine")]])
    entities = [entity for entity in answer.entities if entity.type != "custom_emoji"]
    return {"text": answer.text, "entities": entities, "reply_markup": markup}


@dp.callback_query(F.data.startswith("answering_machine_del"))
@security()
async def _answering_machine_del(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_del", ""))
    account = accounts[callback_query.message.chat.id]
    if account.answering_machine[answer_id] is not None:
        account.answering_machine.delete(answer_id)
        await db.execute("UPDATE accounts SET answering_machine=? WHERE id=?",
                         (accounts[callback_query.message.chat.id].answering_machine.json(), callback_query.message.chat.id))
    await callback_query.message.edit_text(**answering_machine(callback_query.message.chat.id))


@dp.callback_query(F.data.startswith("answering_machine_on"))
@security()
async def _answering_machine_on(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_on", ""))
    account = accounts[callback_query.message.chat.id]
    if account.answering_machine[answer_id] is None:
        await callback_query.answer("Автоответ был удалено ранее!", True)
        await callback_query.message.edit_text(**answering_machine(callback_query.message.chat.id))
    account.answering_machine.main = answer_id
    await db.execute("UPDATE accounts SET answering_machine=? WHERE id=?",
                     (accounts[callback_query.message.chat.id].answering_machine.json(), callback_query.message.chat.id))
    await callback_query.message.edit_text(**auto_answer(callback_query.message.chat.id, answer_id))


@dp.callback_query(F.data.startswith("answering_machine_off"))
@security()
async def _answering_machine_off(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_off", ""))
    account = accounts[callback_query.message.chat.id]
    if account.answering_machine[answer_id] is None:
        await callback_query.answer("Автоответ был удалено ранее!", True)
        await callback_query.message.edit_text(**answering_machine(callback_query.message.chat.id))
    account.answering_machine.main = 0
    await db.execute("UPDATE accounts SET answering_machine=? WHERE id=?",
                     (accounts[callback_query.message.chat.id].answering_machine.json(), callback_query.message.chat.id))
    await callback_query.message.edit_text(**auto_answer(callback_query.message.chat.id, answer_id))


@dp.callback_query(F.data.startswith("answering_machine_edit"))
@security('state')
async def _answering_machine_edit_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    answer_id = int(callback_query.data.replace("answering_machine_edit", ""))
    account = accounts[callback_query.message.chat.id]
    if account.answering_machine[answer_id] is None:
        await callback_query.answer("Автоответ был удалено ранее!", True)
        return await callback_query.message.edit_text(**answering_machine(callback_query.message.chat.id))
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
    account = accounts[message.chat.id]
    answer = account.answering_machine[answer_id]
    if answer is None:
        await message.answer(**answering_machine(message.chat.id))
    else:
        if message.text != "Отмена":
            answer.text = message.text
            answer.entities = message.entities or []
            await db.execute("UPDATE accounts SET answering_machine=? WHERE id=?",
                             (accounts[message.chat.id].answering_machine.json(), message.chat.id))
        await message.answer(**auto_answer(message.chat.id, answer_id))
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
    await accounts[callback_query.message.chat.id].off()
    await callback_query.message.edit_text(**settings(callback_query.message.chat.id))


@dp.callback_query(F.data == "on")
@security('state')
async def _on(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    status = accounts[callback_query.message.chat.id].is_started if accounts.get(callback_query.message.chat.id) else None
    if status is False:  # Зарегистрирован, но отключен
        account = accounts[callback_query.message.chat.id]
        if not account.is_paid:  # Просрочен платеж
            payment_message = payment(callback_query.message.chat.id)
            await callback_query.message.edit_text("Ваша подписка истекла. Продлите ее, чтобы пользоваться Maksogram\n"
                                                   f"{payment_message['text']}", reply_markup=payment_message['reply_markup'])
            return await bot.send_message(OWNER, f"Платеж просрочен. Программа не запущена ({account.name})")
        try:
            await account.on((admin_program if callback_query.message.chat.id == OWNER else program).Program)
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
            await account.telegram_client.send_code_request(account.phone_number)
            return await bot.send_message(OWNER, "Повторный вход...")
    await callback_query.message.edit_text(**settings(callback_query.message.chat.id))


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
        return await message.answer("Код можно отправлять только через кнопку! Telegram блокирует вход при отправке "
                                    "кому-либо. Попробуйте еще раз сначала (возможно придется подождать)",
                                    reply_markup=ReplyKeyboardRemove())
    account = accounts[message.chat.id]
    code = unzip_int_data(message.web_app_data.data)
    try:
        await account.telegram_client.sign_in(phone=account.phone_number, code=code)
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
        await account.on((admin_program if message.chat.id == OWNER else program).Program)
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
    account = accounts[message.chat.id]
    try:
        await account.telegram_client.sign_in(phone=account.phone_number, password=message.text)
    except errors.PasswordHashInvalidError:
        await message.answer("Пароль неверный, попробуйте снова!")
    except Exception as e:
        await message.answer("Произошла ошибка при попытке входа. Мы уже работает над ее решением!")
        await bot.send_message(OWNER, f"⚠️ Ошибка (sign_in) ⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
    else:
        await state.clear()
        await account.on((admin_program if message.chat.id == OWNER else program).Program)
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
            await start_program(message.chat.id, message.from_user.username, phone_number, telegram_client)
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
            await start_program(message.chat.id, message.from_user.username, phone_number, telegram_client)
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
            await message.answer(**settings(message.chat.id))
            await bot.send_message(OWNER, "Создание чатов завершено успешно!")


@dp.callback_query()
@security()
async def _other_callback_query(callback_query: CallbackQuery):
    await new_callback_query(callback_query)


@dp.message()
@security()
async def _other_message(message: Message):
    if await new_message(message): return


async def start_program(user_id: int, username: str, phone_number: str, telegram_client: TelegramClient):
    request = await create_chats(telegram_client)  # Создаем все нужные чаты, папки
    if request['result'] != "ok":
        raise CreateChatsError(request['message'], f"Произошла ошибка {request['error'].__class__.__name__}: {request['error']}")
    name = ('@' + username) if username else user_id
    next_payment = {'next_payment': (time_now() + timedelta(days=7)).strftime("%Y/%m/%d"), 'user': 'user', 'fee': Variables.fee}
    await db.execute("INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (name, user_id, phone_number, request['my_messages'], request['message_changes'], '[]', '[]',
                      '[]', 1, json_encode(next_payment), 1))
    account = Account(name, user_id, phone_number, request['my_messages'], request['message_changes'], [], [], [],
                      '1', next_payment, '1')
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
        await message.answer("<b>Команда разработчика активирована!</b>", parse_mode=html)
    else:
        await message.answer("<b>Команда разработчика НЕ была активирована</b>", parse_mode=html)

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

    await db.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)",
                     (id, username, first_name, last_name, content, date))

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

    if check_subscribe and not await subscribe_to_channel(callback_query.from_user.id):
        await callback_query.message.edit_reply_markup()
        return True
    return False


async def check_payment_datetime():
    for account in accounts.values():
        if not account.is_started or account.payment.user == 'admin': continue
        if account.payment.next_payment.strftime("%Y/%m/%d") == (time_now() + timedelta(days=2)).strftime("%Y/%m/%d"):
            await bot.send_message(account.id, "Текущая подписка заканчивается! Произведите следующий "
                                               "платеж до конца завтрашнего дня")
            await bot.send_message(account.id, **payment(account.id))


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

    await bot.send_message(OWNER, f"<b>Бот запущен!🚀</b>", parse_mode=html)
    print("Запуск бота")
    await dp.start_polling(bot)
