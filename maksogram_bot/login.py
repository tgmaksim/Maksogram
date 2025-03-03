import asyncio

from datetime import timedelta
from core import (
    db,
    html,
    SITE,
    OWNER,
    support,
    security,
    time_now,
    Variables,
    account_on,
    account_off,
    support_link,
    feedback_link,
    unzip_int_data,
    telegram_clients,
    UserIsNotAuthorized,
    new_telegram_client,
    telegram_client_connect,
)

from telethon import TelegramClient
from telethon import errors as telethon_errors
from saving_messages import admin_program, program
from create_chats import CreateChatsError, create_chats

from aiogram import F
from . menu import menu
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton as KButton
from aiogram.types import ReplyKeyboardRemove as KRemove
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from aiogram.types import Message, CallbackQuery, WebAppInfo
from .core import (
    dp,
    bot,
    UserState,
    new_message,
    payment_menu,
    new_callback_query,
)


@dp.callback_query(F.data == "registration")
@security('state')
async def _registration(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.send_phone_number)
    markup = KMarkup(keyboard=[[KButton(text="Отправить номер телефона", request_contact=True)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    await callback_query.message.answer("Чтобы Maksogram уведомлял об удалении и изменении сообщения, нужно войти в аккаунт",
                                        reply_markup=markup)
    await callback_query.message.delete()


@dp.callback_query(F.data == "off")
@security()
async def _off(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    await account_off(account_id)
    await callback_query.message.edit_text(**await menu(callback_query.message.chat.id))


@dp.callback_query(F.data == "on")
@security('state')
async def _on(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    phone_number = await db.fetch_one(f"SELECT phone_number FROM accounts WHERE account_id={account_id}", one_data=True)
    is_started = await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True)
    is_paid = await db.fetch_one(f"SELECT is_paid FROM payment WHERE account_id={account_id}", one_data=True)
    if is_started is False:  # Зарегистрирован, но не запущен
        if is_paid is False:  # Просрочен платеж
            payment_message = await payment_menu(account_id)
            await callback_query.message.edit_text("Ваша подписка истекла. Продлите ее, чтобы пользоваться Maksogram\n"
                                                   f"{payment_message['text']}", reply_markup=payment_message['reply_markup'])
            name = await db.fetch_one(f"SELECT name FROM accounts WHERE account_id={account_id}", one_data=True)
            return await bot.send_message(OWNER, f"Платеж просрочен. Программа не запущена ({name})")
        try:
            await account_on(account_id, (admin_program if callback_query.message.chat.id == OWNER else program).Program)
        except ConnectionError as e:  # Соединение не установлено
            await callback_query.answer("Произошла ошибка... Попробуйте еще раз или дождитесь исправления неполадки")
            raise e
        except UserIsNotAuthorized:  # Удалена сессия
            await state.set_state(UserState.relogin)
            await callback_query.answer("Вы удалили Maksogram из списка устройств")
            markup = KMarkup(keyboard=[[
                KButton(text="Отправить код", web_app=WebAppInfo(url="https://tgmaksim.ru/maksogram/code"))],
                [KButton(text="Отмена")]], resize_keyboard=True)
            await callback_query.message.answer("Вы удалили сессию Telegram, Maksogram больше не имеет доступа "
                                                "к вашему аккаунту. Пришлите код для повторного входа (<b>только кнопкой!</b>)",
                                                parse_mode=html, reply_markup=markup)
            await callback_query.message.delete()
            await telegram_clients[account_id].send_code_request(phone_number)
            return await bot.send_message(OWNER, "Повторный вход...")
    await callback_query.message.edit_text(**await menu(callback_query.message.chat.id))


@dp.message(UserState.relogin)
@security('state')
async def _relogin(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer("Почему вы больше не хотите пользоваться Maksogram? Если у вас есть вопрос, то вы можете "
                                    f"задать его {support_link}", reply_markup=KRemove(), disable_web_page_preview=True)
    if message.content_type != "web_app_data":
        await state.clear()
        return await message.answer("Код можно отправлять только через кнопку! Telegram блокирует вход при отправке кода "
                                    "кому-либо. Попробуйте еще раз сначала (возможно придется подождать)",
                                    reply_markup=KRemove())
    code = unzip_int_data(message.web_app_data.data)
    account_id = message.chat.id
    phone_number = await db.fetch_one(f"SELECT phone_number FROM accounts WHERE account_id={account_id}", one_data=True)
    try:
        await telegram_clients[account_id].sign_in(phone=phone_number, code=code)
    except telethon_errors.SessionPasswordNeededError:
        await state.set_state(UserState.relogin_with_password)
        markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
        await message.answer("Оправьте пароль от вашего аккаунта, он нужен для работы Maksogram!", reply_markup=markup)
        await bot.send_message(OWNER, "Установлен облачный пароль")
    except (telethon_errors.PhoneCodeEmptyError,
            telethon_errors.PhoneCodeExpiredError,
            telethon_errors.PhoneCodeHashEmptyError,
            telethon_errors.PhoneCodeInvalidError):
        await message.answer("Неправильный код! Попробуйте еще раз (только кнопкой!) 👇")
        await bot.send_message(OWNER, "Неправильный код")
    except Exception as e:
        await message.answer("Произошла ошибка при попытке входа. Мы уже работает над ее решением!", reply_markup=KRemove())
        await bot.send_message(OWNER, f"⚠️ Ошибка (sign_in) ⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
    else:
        await state.clear()
        try:
            await account_on(account_id, (admin_program if message.chat.id == OWNER else program).Program)
        except (ConnectionError, UserIsNotAuthorized) as e:
            await message.answer("Произошла ошибка... Дождитесь ее решения, и желательно ничего не трогайте :)",
                                 reply_markup=KRemove())
            raise e
        else:
            await message.answer("Maksogram запущен!", reply_markup=KRemove())


@dp.message(UserState.relogin_with_password)
@security('state')
async def _relogin_with_password(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer("Почему вы больше не хотите пользоваться Maksogram? Если у вас есть вопрос, то вы можете "
                                    f"задать его {support_link}>", reply_markup=KRemove(), disable_web_page_preview=True)
    if message.content_type != "text":
        return await message.answer("Отправьте пароль от вашего аккаунта")
    account_id = message.chat.id
    phone_number = await db.fetch_one(f"SELECT phone_number FROM accounts WHERE account_id={account_id}", one_data=True)
    try:
        await telegram_clients[account_id].sign_in(phone=phone_number, password=message.text)
    except telethon_errors.PasswordHashInvalidError:
        await message.answer("Пароль неверный, попробуйте снова!")
    except Exception as e:
        await message.answer("Произошла ошибка при попытке входа. Мы уже работает над ее решением!", reply_markup=KRemove())
        await bot.send_message(OWNER, f"⚠️ Ошибка (sign_in) ⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
    else:
        await state.clear()
        try:
            await account_on(account_id, (admin_program if message.chat.id == OWNER else program).Program)
        except (ConnectionError, UserIsNotAuthorized) as e:
            await message.answer("Произошла ошибка... Дождитесь ее решения, и желательно ничего не трогайте :)", reply_markup=KRemove())
            raise e
        else:
            await message.answer("Maksogram запущен!", reply_markup=KRemove())


@dp.message(UserState.send_phone_number)
@security('state')
async def _contact(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer(f"Мы понимаем ваши опасения по поводу безопасности. Вы можете почитать {feedback_link}, "
                                    f"чтобы убедиться в том, что с вашим аккаунтом все будет в порядке. Если есть вопрос, можете "
                                    f"задать его {support_link}", parse_mode=html, reply_markup=KRemove(), disable_web_page_preview=True)
    if message.content_type != "contact":
        return await message.reply("Вы не отправили контакт!")
    if message.chat.id != message.contact.user_id:
        return await message.reply("Это не ваш номер! Пожалуйста, воспользуйтесь кнопкой")
    phone_number = f'+{message.contact.phone_number}'
    telegram_client = new_telegram_client(phone_number)
    if not await telegram_client_connect(telegram_client):
        await state.clear()
        await message.answer("Произошла ошибка... Попробуйте начать сначала :)", reply_markup=KRemove())
        raise ConnectionError("За десять попыток соединение не установлено")
    await telegram_client.send_code_request(phone_number)
    await state.set_state(UserState.send_code)
    await state.update_data(telegram_client=telegram_client, phone_number=phone_number)
    markup = KMarkup(keyboard=[[KButton(text="Отправить код", web_app=WebAppInfo(url=f"https://tgmaksim.ru/maksogram/code"))],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    await message.answer("Осталось отправить код для входа (<b>только кнопкой!</b>). Напоминаю, что мы не собираем "
                         f"никаких данных, а по любым вопросам можете обращаться в @{support}", reply_markup=markup, parse_mode=html)


@dp.message(UserState.send_code)
@security('state')
async def _login(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer(f"Мы понимаем ваши опасения по поводу безопасности. Вы можете почитать {feedback_link}, "
                                    f"чтобы убедиться в том, что с вашим аккаунтом все будет в порядке. Если есть вопрос, можете "
                                    f"задать его {support_link}", parse_mode=html, reply_markup=KRemove(), disable_web_page_preview=True)
    if message.content_type != "web_app_data":
        await state.clear()
        return await message.answer("Код можно отправлять только через кнопку! Telegram блокирует вход при отправке "
                                    "кому-либо. Попробуйте еще раз сначала (возможно придется подождать)",
                                    reply_markup=KRemove())
    code = unzip_int_data(message.web_app_data.data)
    data = await state.get_data()
    telegram_client: TelegramClient = data['telegram_client']
    phone_number: str = data['phone_number']
    try:
        await telegram_client.sign_in(phone=phone_number, code=code)
    except telethon_errors.SessionPasswordNeededError:
        await state.set_state(UserState.send_password)
        markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
        await message.answer("У вас установлен облачный пароль (двухфакторная аутентификация). Отправьте его мне", reply_markup=markup)
        await bot.send_message(OWNER, "Установлен облачный пароль")
    except (telethon_errors.PhoneCodeEmptyError,
            telethon_errors.PhoneCodeExpiredError,
            telethon_errors.PhoneCodeHashEmptyError,
            telethon_errors.PhoneCodeInvalidError):
        await message.answer("Неправильный код! Попробуйте еще раз (только кнопкой!) 👇")
        await bot.send_message(OWNER, "Неправильный код")
    except Exception as e:
        await message.answer("Произошла ошибка при попытке входа. Мы уже работает над ее решением!", reply_markup=KRemove())
        await bot.send_message(OWNER, f"⚠️ Ошибка (sign_in) ⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
    else:
        await state.clear()
        loading = await message.answer_sticker("CAACAgIAAxkBAAIyQWeUrH2jAUkcqHGYerWNT3ySuFwbAAJBAQACzRswCPHwYhjf9pZYNgQ", reply_markup=KRemove())
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
            referal: int = await db.fetch_one(f"SELECT account_id FROM referals WHERE referal_id={message.chat.id}", one_data=True)
            if referal:
                await db.execute(f"""UPDATE payment SET next_payment=((CASE WHEN 
                                 next_payment > CURRENT_TIMESTAMP THEN 
                                 next_payment ELSE CURRENT_TIMESTAMP END) + INTERVAL '30 days'), 
                                 is_paid=true WHERE account_id={referal}""")  # перемещение даты оплаты на 30 дней вперед
                await bot.send_message(referal, "По вашей реферальной ссылке зарегистрировался пользователь. "
                                                "Вы получили месяц подписки в подарок!")
            await loading.delete()
            await message.answer("Maksogram запущен 🚀\nВ канале <b>Мои сообщения</b> будут храниться все ваши сообщения, в "
                                 "комментариях будет информация о изменении, реакциях и удалении\n"
                                 f"Полный обзор функция доступен на <b><a href='{SITE}'>сайте</a></b>\n"
                                 "Пробная подписка заканчивается через неделю", parse_mode=html, disable_web_page_preview=True)
            await message.answer("<b>Меню функций и настройки</b>", parse_mode=html,
                                 reply_markup=IMarkup(inline_keyboard=[[IButton(text="⚙️ Меню и настройки", callback_data="menu")]]))
            await bot.send_message(OWNER, "Создание чатов завершено успешно!")


@dp.message(UserState.send_password)
@security('state')
async def _login_with_password(message: Message, state: FSMContext):
    if await new_message(message): return
    if message.text == "Отмена":
        await state.clear()
        return await message.answer(f"Мы понимаем ваши опасения по поводу безопасности. Вы можете почитать {feedback_link}, "
                                    f"чтобы убедиться в том, что с вашим аккаунтом все будет в порядке. Если есть вопрос, можете "
                                    f"задать его {support_link}", parse_mode=html, reply_markup=KRemove(), disable_web_page_preview=True)
    if message.content_type != "text":
        return await message.answer("Отправьте пароль от вашего аккаунта")
    data = await state.get_data()
    telegram_client: TelegramClient = data['telegram_client']
    phone_number: str = data['phone_number']
    try:
        await telegram_client.sign_in(phone=phone_number, password=message.text)
    except telethon_errors.PasswordHashInvalidError:
        await message.answer("Пароль неверный, попробуйте снова!")
    except Exception as e:
        await state.clear()
        await message.answer("Произошла ошибка при попытке входа. Мы уже работает над ее решением!", reply_markup=KRemove())
        await bot.send_message(OWNER, f"⚠️Ошибка⚠️\n\nПроизошла ошибка {e.__class__.__name__}: {e}")
    else:
        await state.clear()
        loading = await message.answer_sticker("CAACAgIAAxkBAAIyQWeUrH2jAUkcqHGYerWNT3ySuFwbAAJBAQACzRswCPHwYhjf9pZYNgQ", reply_markup=KRemove())
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
            referal: int = await db.fetch_one(f"SELECT account_id FROM referals WHERE referal_id={message.chat.id}", one_data=True)
            if referal:
                await db.execute(f"""UPDATE payment SET next_payment=((CASE WHEN 
                                 next_payment > CURRENT_TIMESTAMP THEN 
                                 next_payment ELSE CURRENT_TIMESTAMP END) + INTERVAL '30 days'), 
                                 is_paid=true WHERE account_id={referal}""")  # перемещение даты оплаты на 30 дней вперед
                await bot.send_message(referal, "По вашей реферальной ссылке зарегистрировался пользователь. "
                                                "Вы получили месяц подписки в подарок!")
            await loading.delete()
            await message.answer("Maksogram запущен 🚀\nВ канале <b>Мои сообщения</b> будут храниться все ваши сообщения, в "
                                 "комментариях будет информация о изменении, реакциях и удалении\n"
                                 f"Полный обзор функция доступен на <b><a href='{SITE}'>сайте</a></b>\n"
                                 "Пробная подписка заканчивается через неделю", parse_mode=html, disable_web_page_preview=True)
            await message.answer("<b>Меню функций и настройки</b>", parse_mode=html,
                                 reply_markup=IMarkup(inline_keyboard=[[IButton(text="⚙️ Меню и настройки", callback_data="menu")]]))
            await bot.send_message(OWNER, "Создание чатов завершено успешно!")


async def start_program(account_id: int, username: str, phone_number: int, telegram_client: TelegramClient):
    request = await create_chats(telegram_client)  # Создаем все нужные чаты, папки
    if request['result'] != "ok":
        raise CreateChatsError(request['message'], f"Произошла ошибка {request['error'].__class__.__name__}: {request['error']}")
    name = ('@' + username) if username else account_id
    next_payment = time_now() + timedelta(days=7)
    await db.execute(f"INSERT INTO accounts VALUES ({account_id}, '{name}', {phone_number}, "
                     f"{request['my_messages']}, {request['message_changes']}, now(), now())")
    await db.execute(f"INSERT INTO settings VALUES ({account_id}, '[]', '[]', true, 6, 'Омск')")
    await db.execute(f"INSERT INTO payment VALUES ({account_id}, 'user', {Variables.fee}, '{next_payment}', true, now(), now())")
    await db.execute(f"INSERT INTO functions VALUES ({account_id}, '[]')")
    await db.execute(f"INSERT INTO modules VALUES ({account_id}, false, false, false, false, false)")
    await db.execute(f"INSERT INTO statistics VALUES ({account_id}, now(), now(), now())")
    telegram_clients[account_id] = telegram_client
    asyncio.get_running_loop().create_task(program.Program(telegram_client, account_id, [], time_now()).run_until_disconnected())


def login_initial():
    pass  # Чтобы PyCharm не ругался
