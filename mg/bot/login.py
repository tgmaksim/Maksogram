import asyncio

from mg.config import OWNER, WEB_APP, FEE

from aiogram import F

from mg.menu.bot import menu
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, WebAppInfo
from mg.bot.functions import new_callback_query, new_message, get_referral, generate_sensitive_link
from mg.bot.types import dp, bot, CallbackData, UserState, feedback_link, support_link, sticker_loading

from aiogram.types import KeyboardButton as KButton
from aiogram.types import ReplyKeyboardRemove as KRemove
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton

from telethon import TelegramClient
from telethon.errors.rpcerrorlist import (
    PhoneCodeEmptyError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneCodeHashEmptyError,
    PasswordHashInvalidError,
    SessionPasswordNeededError,
)

from datetime import timedelta
from mg.core.database import Database
from mg.client import MaksogramClient
from mg.client.types import maksogram_clients
from mg.client.create_chats import create_chats
from mg.client.types import CreateChatsError, UserIsNotAuthorized
from mg.core.functions import time_now, error_notify, unzip_int_data, format_error, renew_subscription
from mg.client.functions import new_telegram_client, client_connect, get_is_started, get_phone_number


cb = CallbackData()


@dp.callback_query(F.data.startswith(cb.command('on')))
@error_notify('state')
async def _on(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    is_started = await get_is_started(account_id)

    if is_started is False:
        try:
            await MaksogramClient.on_account(account_id)
        except UserIsNotAuthorized:
            await state.set_state(UserState.relogin_code)
            markup = KMarkup(keyboard=[[KButton(text="Войти в аккаунт", web_app=WebAppInfo(url=f"{WEB_APP}/code"))],
                                       [KButton(text="Отмена")]], resize_keyboard=True)
            await callback_query.message.answer(
                "Чтобы Maksogram уведомлял об удалении и изменении сообщений, нужно войти в аккаунт. Понимаем ваши опасения по поводу безопасности: "
                f"вы можете почитать {feedback_link} или написать {support_link}", reply_markup=markup, disable_web_page_preview=True)
            await callback_query.message.delete()

            phone_number = await get_phone_number(account_id)
            await maksogram_clients[account_id].client.send_code_request(phone_number)
            await bot.send_message(OWNER, "Повторный вход")
        except ConnectionError:
            await callback_query.answer("Произошла временная ошибка, попробуйте еще раз", True)
            await bot.send_message(OWNER, "Произошла ошибка ConnectionError, пользователю предложено попробовать еще раз")
        except Exception as e:
            print(e.__class__.__name__, e)
            await callback_query.answer("Произошла ошибка при запуске Maksogram, попробуйте еще раз или дождитесь решения проблемы", True)
            await bot.send_message(OWNER, format_error(e), parse_mode=None)
        else:
            await callback_query.message.edit_text(**await menu(account_id))


@dp.callback_query(F.data.startswith(cb.command('off')))
@error_notify()
async def _off(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id

    await MaksogramClient.off_account(account_id)
    await callback_query.message.edit_text(**await menu(account_id))


@dp.callback_query(F.data.startswith(cb.command('registration')))
@error_notify('state')
async def _registration(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.phone_number)

    markup = KMarkup(keyboard=[[KButton(text="Начать регистрацию", request_contact=True)],
                                      [KButton(text="Отмена")]], resize_keyboard=True)
    await callback_query.message.answer(
        "Чтобы Maksogram уведомлял об удалении и изменении сообщений, нужно войти в аккаунт. Понимаем ваши опасения по поводу безопасности: "
        f"вы можете почитать {feedback_link} или написать {support_link}", reply_markup=markup, disable_web_page_preview=True)
    await callback_query.message.delete()


@dp.message(UserState.phone_number)
@error_notify('state')
async def _phone_number(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id

    if message.text == "Отмена":
        await state.clear()
        await message.answer(
            f"Мы понимаем ваши опасения по поводу безопасности. Вы можете почитать {feedback_link}, чтобы убедиться в том, что с вашим аккаунтом "
            f"все будет в порядке. Если есть вопрос, можете задать его {support_link}", reply_markup=KRemove(), disable_web_page_preview=True)
        return
    if not message.contact:
        await message.answer("Вы не отправили контакт")
        return
    if message.contact.user_id != account_id:
        await message.answer("Это не Ваш контакт, пожалуйста, воспользуйтесь кнопкой")
        return

    telegram_client = new_telegram_client(account_id)
    if not await client_connect(telegram_client):
        await state.clear()
        await message.answer("Произошла временная ошибка, начните сначала :)", reply_markup=KRemove())
        await bot.send_message(OWNER, "Не удалось соединиться с сервером, пользователю предложено попробовать еще раз")
        return

    phone_number = f"+{int(message.contact.phone_number)}"
    try:
        await telegram_client.send_code_request(phone_number)
    except ConnectionError:
        await message.answer("Произошла временная ошибка, начните сначала :)", reply_markup=KRemove())
        await bot.send_message(OWNER, "Произошла ошибка ConnectionError, пользователю предложено попробовать еще раз")
        return

    await state.set_state(UserState.code)
    await state.update_data(telegram_client=telegram_client, phone_number=phone_number)

    markup = KMarkup(keyboard=[[KButton(text="Войти в аккаунт", web_app=WebAppInfo(url=f"{WEB_APP}/code"))],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    await message.answer(
        "Осталось отправить код для входа (❗️ <b>только кнопкой</b> ❗️). Напоминаю, что мы не собираем никаких данных, а по любым вопросам можете "
        f"обращаться к {support_link}", reply_markup=markup, disable_web_page_preview=True)


@dp.message(UserState.code)
@error_notify('state')
async def _code(message: Message, state: FSMContext):
    if await new_message(message): return

    if message.text == "Отмена":
        await state.clear()
        await message.answer(
            f"Мы понимаем ваши опасения по поводу безопасности. Вы можете почитать {feedback_link}, чтобы убедиться в том, что с вашим аккаунтом "
            f"все будет в порядке. Если есть вопрос, можете задать его {support_link}", reply_markup=KRemove(), disable_web_page_preview=True)
        return
    if not message.web_app_data:
        await state.clear()
        await message.answer(
            "Код можно отправлять только через кнопку! Telegram блокирует вход при отправке кода кому-либо. "
            "Попробуйте еще раз сначала через несколько минут", reply_markup=KRemove())
        return

    data = await state.get_data()
    telegram_client: TelegramClient = data['telegram_client']
    phone_number: str = data['phone_number']
    code = unzip_int_data(message.web_app_data.data)

    try:
        await telegram_client.sign_in(phone_number, code)
    except SessionPasswordNeededError:  # Установлен облачный пароль
        await state.set_state(UserState.password)
        markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
        await message.answer("Ваш аккаунт защищен облачным паролем! Он нужен для работы Maksogram. Отправьте его", reply_markup=markup)
        await bot.send_message(OWNER, "Установлен облачный пароль")
    except (PhoneCodeHashEmptyError, PhoneCodeInvalidError, PhoneCodeExpiredError, PhoneCodeEmptyError) as e:
        print(e.__class__.__name__, e)
        await message.answer("Неправильный код! Попробуйте еще раз (❗️ <b>только кнопкой</b> ❗️)")
        await bot.send_message(OWNER, f"Неверный код ({e.__class__.__name__}: {e})")
    except Exception as e:
        await state.clear()
        await bot.send_message(OWNER, format_error(e), parse_mode=None)
        await message.answer("Произошла ошибка при попытке входа. Скоро она будет решена, а пока что подождите...", reply_markup=KRemove())
    else:
        await state.clear()
        await account_initial(message.chat.id, telegram_client, message.from_user.username, int(phone_number))


@dp.message(UserState.password)
@error_notify('state')
async def _password(message: Message, state: FSMContext):
    if await new_message(message): return

    if message.text == "Отмена":
        await state.clear()
        await message.answer(
            f"Мы понимаем ваши опасения по поводу безопасности. Вы можете почитать {feedback_link}, чтобы убедиться в том, что с вашим аккаунтом "
            f"все будет в порядке. Если есть вопрос, можете задать его {support_link}", reply_markup=KRemove(), disable_web_page_preview=True)
        return
    if not message.text:
        await message.answer("Отправьте облачный пароль от аккаунта Telegram")
        return

    data = await state.get_data()
    telegram_client: TelegramClient = data['telegram_client']
    phone_number: str = data['phone_number']

    try:
        await telegram_client.sign_in(phone_number, password=message.text)
    except PasswordHashInvalidError as e:
        print(e.__class__.__name__, e)
        await message.answer("Неверный облачный пароль, попробуйте еще раз")
        await bot.send_message(OWNER, "Неверный облачный пароль")
    except Exception as e:
        await state.clear()
        await bot.send_message(OWNER, format_error(e), parse_mode=None)
        await message.answer("Произошла ошибка при попытке входа. Скоро она будет решена, а пока что подождите...", reply_markup=KRemove())
    else:
        await state.clear()
        await account_initial(message.chat.id, telegram_client, message.from_user.username, int(phone_number))


async def account_initial(account_id: int, telegram_client: TelegramClient, username: str, phone_number: int):
    """Завершает настройку после успешного входа в аккаунт"""

    sticker = await bot.send_sticker(account_id, sticker_loading)

    try:
        await start_maksogram_client(account_id, username, phone_number, telegram_client)
    except CreateChatsError as e:
        await bot.send_message(account_id, e.args[0], reply_markup=KRemove())
        await sticker.delete()
        await bot.send_message(OWNER, format_error(e.args[1]), parse_mode=None)
    except Exception as e:
        await bot.send_message(account_id, "Произошла неизвестная ошибка при необходимых чатов. Подождите ее решения", reply_markup=KRemove())
        await sticker.delete()
        await bot.send_message(OWNER, format_error(e), parse_mode=None)
    else:
        referral = await get_referral(account_id)
        if referral:  # Нового пользователя кто-то пригласил
            await renew_subscription(referral, 30)  # Продлеваем подписку на 30 дней
            await bot.send_message(referral, "По реферальной ссылке зарегистрировался новый пользователь, подписка продлилась на 30 дней. Поздравляем!")

        link = await generate_sensitive_link(account_id, "run_link")
        await bot.send_message(
            account_id, "Maksogram запущен 🚀\nВ канале <b>Мои сообщения</b> будут храниться все ваши сообщения, в комментариях будет информация об "
                        f"изменении и удалении\n<b><a href='{link}'>Полный обзор функций</a></b>\nMaksogram Premium на неделю",
            reply_markup=KRemove(), disable_web_page_preview=True)
        await bot.send_message(account_id, "<b>Меню функций и настройки</b>",
                               reply_markup=IMarkup(inline_keyboard=[[IButton(text="⚙️ Меню и настройки", callback_data=cb('menu'))]]))
        await sticker.delete()
        await bot.send_message(OWNER, "Создание чатов завершено успешно")


@dp.message(UserState.relogin_code)
@error_notify('state')
async def _relogin_code(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id

    if message.text == "Отмена":
        await state.clear()
        await message.answer(
            f"Почему вы больше не хотите пользоваться Maksogram?. Вы можете почитать {feedback_link}, чтобы убедиться в том, что с вашим аккаунтом "
            f"все будет в порядке. Если есть вопрос, можете задать его {support_link}", reply_markup=KRemove(), disable_web_page_preview=True)
        return
    if not message.web_app_data:
        await state.clear()
        await message.answer(
            "Код можно отправлять только через кнопку! Telegram блокирует вход при отправке кода кому-либо. "
            "Попробуйте еще раз сначала через несколько минут", reply_markup=KRemove())
        return

    telegram_client = maksogram_clients[account_id].client
    phone_number = await get_phone_number(account_id)
    code = unzip_int_data(message.web_app_data.data)

    try:
        await telegram_client.sign_in(phone_number, code)
    except SessionPasswordNeededError:  # Установлен облачный пароль
        await state.set_state(UserState.relogin_password)
        markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
        await message.answer("Ваш аккаунт защищен облачным паролем! Он нужен для работы Maksogram. Отправьте его", reply_markup=markup)
        await bot.send_message(OWNER, "Установлен облачный пароль")
    except (PhoneCodeHashEmptyError, PhoneCodeInvalidError, PhoneCodeExpiredError, PhoneCodeEmptyError) as e:
        print(e.__class__.__name__, e)
        await message.answer("Неправильный код! Попробуйте еще раз (❗️ <b>только кнопкой</b> ❗️)")
        await bot.send_message(OWNER, f"Неверный код ({e.__class__.__name__}: {e})")
    except Exception as e:
        await state.clear()
        await bot.send_message(OWNER, format_error(e), parse_mode=None)
        await message.answer("Произошла ошибка при попытке входа. Скоро она будет решена, а пока что подождите...", reply_markup=KRemove())
    else:
        await state.clear()

        try:
            await MaksogramClient.on_account(account_id)
        except (UserIsNotAuthorized, ConnectionError) as e:
            print(e.__class__.__name__, e)
            await bot.send_message(OWNER, format_error(e), parse_mode=None)
            await message.answer("Произошла неизвестная ошибка при попытке запуска Maksogram, дождитесь ее решения", reply_markup=KRemove())
        else:
            await (await message.answer("Maksogram запущен!", reply_markup=KRemove())).delete()
            await message.answer(**await menu(account_id))


@dp.message(UserState.relogin_password)
@error_notify('state')
async def _relogin_password(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id

    if message.text == "Отмена":
        await state.clear()
        await message.answer(
            f"Мы понимаем ваши опасения по поводу безопасности. Вы можете почитать {feedback_link}, чтобы убедиться в том, что с вашим аккаунтом "
            f"все будет в порядке. Если есть вопрос, можете задать его {support_link}", reply_markup=KRemove(), disable_web_page_preview=True)
        return
    if not message.text:
        await message.answer("Отправьте облачный пароль от аккаунта Telegram")
        return

    telegram_client = maksogram_clients[account_id].client
    phone_number = await get_phone_number(account_id)

    try:
        await telegram_client.sign_in(phone_number, password=message.text)
    except PasswordHashInvalidError as e:
        print(e.__class__.__name__, e)
        await message.answer("Неверный облачный пароль, попробуйте еще раз")
        await bot.send_message(OWNER, "Неверный облачный пароль")
    except Exception as e:
        await state.clear()
        await bot.send_message(OWNER, format_error(e), parse_mode=None)
        await message.answer("Произошла ошибка при попытке входа. Скоро она будет решена, а пока что подождите...", reply_markup=KRemove())
    else:
        await state.clear()

        try:
            await MaksogramClient.on_account(account_id)
        except (UserIsNotAuthorized, ConnectionError) as e:
            print(e.__class__.__name__, e)
            await bot.send_message(OWNER, format_error(e), parse_mode=None)
            await message.answer("Произошла неизвестная ошибка при попытке запуска Maksogram, дождитесь ее решения", reply_markup=KRemove())
        else:
            await (await message.answer("Maksogram запущен!", reply_markup=KRemove())).delete()
            await message.answer(**await menu(account_id))


async def start_maksogram_client(account_id: int, username: str, phone_number: int, telegram_client: TelegramClient):
    """Создает необходимые чаты, добавляет данные в БД и запускает MaksogramClient"""

    response = await create_chats(telegram_client)
    if not response.ok:
        raise CreateChatsError(response.error_message, response.error)

    name = f"@{username}" if username else str(account_id)
    end = time_now() + timedelta(days=7)  # неделя premium подписки

    await Database.execute(
        "INSERT INTO accounts (account_id, name, phone_number, my_messages, message_changes, registration_date, awake_time) "
        "VALUES($1, $2, $3, $4, $5, now(), now())", account_id, name, phone_number, response.my_messages, response.message_changes)
    await Database.execute("INSERT INTO settings (account_id, is_started, time_zone, city) VALUES($1, true, 6, 'Омск')", account_id)
    await Database.execute(
        "INSERT INTO payment (account_id, subscription, fee, ending, first_notification, second_notification) "
        "VALUES($1, 'premium', $2, $3, now(), now())", account_id, FEE, end)
    await Database.execute("INSERT INTO modules (account_id) VALUES($1)", account_id)
    await Database.execute("INSERT INTO statistics (account_id, answering_machine, audio_transcription, weather) VALUES ($1, now(), now(), now())", account_id)
    await Database.execute("INSERT INTO security (account_id, security_hack, security_no_access, email) VALUES ($1, false, false, NULL)", account_id)
    await Database.execute("INSERT INTO limits (account_id, reset_time) VALUES ($1, now())", account_id)

    maksogram_client = MaksogramClient(account_id, telegram_client)
    maksogram_clients[account_id] = maksogram_client
    asyncio.create_task(maksogram_client.run_until_disconnected())


def login_initial():
    pass  # Чтобы PyCharm не ругался
