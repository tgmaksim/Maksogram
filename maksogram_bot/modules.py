from typing import Any
from modules.currencies import currencies
from core import (
    db,
    html,
    morning,
    channel,
    security,
    json_encode,
    generate_sensitive_link,
)

from aiogram import F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton as KButton
from aiogram.types import ReplyKeyboardMarkup as RMarkup
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from aiogram.types import Message, CallbackQuery, WebAppInfo
from .core import (
    dp,
    bot,
    Data,
    UserState,
    new_message,
    new_callback_query,
)


@dp.message(Command('menu_chat'))
@security()
async def _menu_chat(message: Message):
    if await new_message(message): return
    await message.answer(**modules_menu())


@dp.callback_query((F.data == "modules").__or__(F.data == "modulesPrev"))
@security()
async def _modules(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**modules_menu())


def modules_menu() -> dict[str, Any]:
    markup = IMarkup(inline_keyboard=[[IButton(text="🔢 Калькулятор", callback_data="calculator"),
                                       IButton(text="🌤 Погода", callback_data="weather")],
                                      [IButton(text="🔗 Генератор QR", callback_data="qrcode"),
                                       IButton(text="🔗 Сканер QR", web_app=WebAppInfo(url=f"{Data.web_app}/main"))],
                                      [IButton(text="🗣 ГС в текст", callback_data="audio_transcription"),
                                       IButton(text="🔄 Видео в кружок", callback_data="round_video")],
                                      [IButton(text="⏰ Напоминалка", callback_data="reminder"),
                                       IButton(text="🎲 Рандомайзер", callback_data="randomizer")],
                                      [IButton(text="💱 Конвертер валют", callback_data="currencies")],
                                      [IButton(text="◀️  Назад", callback_data="menu")]])
    return {"text": "💬 <b>Maksogram в чате</b>\nФункции, которые работают прямо из любого чата, не нужно писать мне",
            "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data == "calculator")
@security()
async def _calculator(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await calculator_menu(callback_query.message.chat.id))


async def calculator_menu(account_id: int) -> dict[str, Any]:
    if await db.fetch_one(f"SELECT calculator FROM modules WHERE account_id={account_id}", one_data=True):  # Вкл/выкл калькулятор
        status_button = IButton(text="🔴 Выключить Калькулятор", callback_data="calculator_off")
    else:
        status_button = IButton(text="🟢 Включить Калькулятор", callback_data="calculator_on")
    link = await generate_sensitive_link(account_id, "module-calculator", "калькулятор")
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="Обзор Калькулятора", url=link)],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "🔢 <b>Калькулятор в чате</b>\nРешает примеры разных уровней сложности от обычного умножения до "
                    "длинных примеров\n<b>Для вызова укажите в конце \"=\"</b>\n<blockquote>10+5*15=</blockquote>",
            "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data.in_(["calculator_on", "calculator_off"]))
@security()
async def _calculator_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    account_id = callback_query.from_user.id
    if await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True) is None:
        return await callback_query.answer("Maksogram в чате доступен только пользователям Maksogram", True)
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET calculator=true WHERE account_id={account_id}")
        case "off":
            await db.execute(f"UPDATE modules SET calculator=false WHERE account_id={account_id}")
    await callback_query.message.edit_text(**await calculator_menu(account_id))


@dp.callback_query(F.data == "qrcode")
@security()
async def _qrcode(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await qrcode_menu(callback_query.message.chat.id))


async def qrcode_menu(account_id: int) -> dict[str, Any]:
    if await db.fetch_one(f"SELECT qrcode FROM modules WHERE account_id={account_id}", one_data=True):  # Вкл/выкл генератор QR
        status_button = IButton(text="🔴 Выключить Генератор", callback_data="qrcode_off")
    else:
        status_button = IButton(text="🟢 Включить Генератор", callback_data="qrcode_on")
    link = await generate_sensitive_link(account_id, "module-qr_code", "генератор-qr")
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="Обзор Генератора QR", url=link)],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": f"🔗 <b>Генератор QR-кода</b>\nГенерирует обычный QR-код с нужной ссылкой в чате\n<blockquote>Создай t.me/{channel}\n"
                    f"Создать t.me/{channel}\nСгенерировать t.me/{channel}\nСгенерируй t.me/{channel}\nQR t.me/{channel}</blockquote>",
            "reply_markup": markup, "parse_mode": html, "disable_web_page_preview": True}


@dp.callback_query(F.data.in_(["qrcode_on", "qrcode_off"]))
@security()
async def _qrcode_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    account_id = callback_query.from_user.id
    if await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True) is None:
        return await callback_query.answer("Maksogram в чате доступен только пользователям Maksogram", True)
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET qrcode=true WHERE account_id={account_id}")  # Включение QR
        case "off":
            await db.execute(f"UPDATE modules SET qrcode=false WHERE account_id={account_id}")  # Выключение QR
    await callback_query.message.edit_text(**await qrcode_menu(account_id))


@dp.callback_query(F.data == "audio_transcription")
@security()
async def _audio_transcription(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await audio_transcription_menu(callback_query.message.chat.id))


async def audio_transcription_menu(account_id: int) -> dict[str, Any]:
    if await db.fetch_one(f"SELECT audio_transcription FROM modules WHERE account_id={account_id}", one_data=True):  # Вкл/выкл расшифровка гс
        status_button = IButton(text="🔴 Выключить Расшифровку", callback_data="audio_transcription_off")
    else:
        status_button = IButton(text="🟢 Включить Расшифровку", callback_data="audio_transcription_on")
    link = await generate_sensitive_link(account_id, "module-audio_transcription", "расшифровка-сг")
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="Обзор Расшифровки ГС", url=link)],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "🗣 <b>Расшифровка голосовых</b>\nНе хотите слушать голосовое или кружок? Расшифруйте его в текст: "
                    "свайпни и отправь команду\n<blockquote>Расшифруй\nРасшифровать\nВ текст</blockquote>",
            "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data.in_(["audio_transcription_on", "audio_transcription_off"]))
@security()
async def _audio_transcription_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    account_id = callback_query.from_user.id
    if await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True) is None:
        return await callback_query.answer("Maksogram в чате доступен только пользователям Maksogram", True)
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET audio_transcription=true WHERE account_id={account_id}")  # Включение расшифровки
        case "off":
            await db.execute(f"UPDATE modules SET audio_transcription=false WHERE account_id={account_id}")  # Выключение расшифровки
    await callback_query.message.edit_text(**await audio_transcription_menu(account_id))


@dp.callback_query(F.data == "weather")
@security()
async def _weather(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await weather_menu(callback_query.from_user.id))


async def weather_menu(account_id: int) -> dict[str, Any]:
    if await db.fetch_one(f"SELECT weather FROM modules WHERE account_id={account_id}", one_data=True):  # Вкл/выкл погода
        status_button_weather = IButton(text="🔴 Выключить Погоду", callback_data="weather_off")
    else:
        status_button_weather = IButton(text="🟢 Включить Погоду", callback_data="weather_on")
    if mw := await db.fetch_one(f"SELECT morning_weather FROM modules WHERE account_id={account_id}", one_data=True):  # Вкл/выкл погода по утрам
        status_button_morning_weather = IButton(text="🔴 Выключить утреннюю Погоду", callback_data="morning_weather_off")
    else:
        status_button_morning_weather = IButton(text="🟢 Включить утреннюю Погоду", callback_data="morning_weather_on")
    link = await generate_sensitive_link(account_id, "module-weather", "погода")
    markup = IMarkup(inline_keyboard=[[status_button_weather],
                                      [status_button_morning_weather],
                                      [IButton(text="Обзор функции", url=link)],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    warnings = f"<blockquote>❗️ Погода по утрам присылается, когда вы первый раз зашли в Telegram с {morning[0]}:00 " \
               f"до {morning[1]}:00</blockquote>\n<blockquote>❗️ Для улучшения точности выберите часовой пояс в /settings</blockquote>"
    if not mw: warnings = "<blockquote>❗️ Для работы функции выберите город в /settings</blockquote>"
    return {"text": "🌤 <b>Погода</b>\nЛегко получайте погоду за окном, не выходя из Telegram командой 👇\n<blockquote>"
                    f"Какая погода</blockquote>\n{warnings}", "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data.in_(["weather_on", "weather_off"]))
@security()
async def _weather_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    account_id = callback_query.from_user.id
    if await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True) is None:
        return await callback_query.answer("Maksogram в чате доступен только пользователям Maksogram", True)
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET weather=true WHERE account_id={account_id}")  # Включение погоды
        case "off":
            await db.execute(f"UPDATE modules SET weather=false WHERE account_id={account_id}")  # Выключение погоды
    await callback_query.message.edit_text(**await weather_menu(account_id))


@dp.callback_query(F.data.in_(["morning_weather_on", "morning_weather_off"]))
@security()
async def _morning_weather_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    account_id = callback_query.from_user.id
    if await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True) is None:
        return await callback_query.answer("Maksogram в чате доступен только пользователям Maksogram", True)
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET morning_weather=true WHERE account_id={account_id}")  # Включение погоды по утрам
        case "off":
            await db.execute(f"UPDATE modules SET morning_weather=false WHERE account_id={account_id}")  # Выключение погоды по утрам
    await callback_query.message.edit_text(**await weather_menu(account_id))


@dp.callback_query(F.data == "round_video")
@security()
async def _round_video(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await round_video_menu(callback_query.message.chat.id))


async def round_video_menu(account_id: int) -> dict[str, Any]:
    if await db.fetch_one(f"SELECT round_video FROM modules WHERE account_id={account_id}", one_data=True):  # Вкл/выкл конвертер видео
        status_button = IButton(text="🔴 Выключить Конвертер", callback_data="round_video_off")
    else:
        status_button = IButton(text="🟢 Включить Конвертер", callback_data="round_video_on")
    link = await generate_sensitive_link(account_id, "module-round_video", "видео-в-кружок")
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="Как создать кружок?", url=link)],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "🔄 <b>Конвертер видео в кружок</b>\nПонадобилось сделать из обычного видео кружок? Свайпни и отправь\n"
                    "<blockquote>Кружок</blockquote>", "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data.in_(["round_video_on", "round_video_off"]))
@security()
async def _round_video_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    account_id = callback_query.from_user.id
    if await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True) is None:
        return await callback_query.answer("Maksogram в чате доступен только пользователям Maksogram", True)
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET round_video=true WHERE account_id={account_id}")  # Включение конвертера
        case "off":
            await db.execute(f"UPDATE modules SET round_video=false WHERE account_id={account_id}")  # Выключение конвертера
    await callback_query.message.edit_text(**await round_video_menu(account_id))


@dp.callback_query(F.data == "reminder")
@security()
async def _reminder(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await reminder_menu(callback_query.message.chat.id))


async def reminder_menu(account_id: int) -> dict[str, Any]:
    if await db.fetch_one(f"SELECT reminder FROM modules WHERE account_id={account_id}", one_data=True):  # Вкл/выкл напоминалки
        status_button = IButton(text="🔴 Выключить Напоминалку", callback_data="reminder_off")
    else:
        status_button = IButton(text="🟢 Включить Напоминалку", callback_data="reminder_on")
    link = await generate_sensitive_link(account_id, "module-reminder", "напоминалка")
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="Обзор Напоминалки", url=link)],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "⏰ <b>Напоминалка в чате</b>\nДля создания напоминания <b>нужно ответить</b> на любое сообщение в чате командой\n"
                    "<blockquote>❗️ Для правильной работы Напоминалки выберите часовой пояс в /settings</blockquote>\n"
                    "<blockquote expandable><b>Примеры</b>:\nНапомни через 5 минут\nНапомни через 5 часов\nНапомни через "
                    "5 часов 30 минут\nНапомни в 12:00\nНапомни завтра в 12.00\nНапомни 9 декабря в 12:00</blockquote>",
                    "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data.in_(["reminder_on", "reminder_off"]))
@security()
async def _reminder_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    account_id = callback_query.from_user.id
    if await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True) is None:
        return await callback_query.answer("Maksogram в чате доступен только пользователям Maksogram", True)
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET reminder=true WHERE account_id={account_id}")  # Включение напоминалки
        case "off":
            await db.execute(f"UPDATE modules SET reminder=false WHERE account_id={account_id}")  # Выключение напоминалки
    await callback_query.message.edit_text(**await reminder_menu(account_id))


@dp.callback_query(F.data == "randomizer")
@security()
async def _randomizer(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await randomizer_menu(callback_query.message.chat.id))


async def randomizer_menu(account_id: int) -> dict[str, Any]:
    if await db.fetch_one(f"SELECT randomizer FROM modules WHERE account_id={account_id}", one_data=True):  # Вкл/выкл рандомайзера
        status_button = IButton(text="🔴 Выключить Рандомайзер", callback_data="randomizer_off")
    else:
        status_button = IButton(text="🟢 Включить Рандомайзер", callback_data="randomizer_on")
    link = await generate_sensitive_link(account_id, "module-randomizer", "рандомайзер")
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="Обзор Рандомайзера", url=link)],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "🎲 <b>Рандомайзер в чате</b>\n<blockquote>Выбери да или нет\nВыбери число от 0 до 10\n"
                    "Выбери яблоко, банан или груша</blockquote>", "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data.in_(["randomizer_on", "randomizer_off"]))
@security()
async def _randomizer_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    account_id = callback_query.from_user.id
    if await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True) is None:
        return await callback_query.answer("Maksogram в чате доступен только пользователям Maksogram", True)
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET randomizer=true WHERE account_id={account_id}")  # Включение рандомайзера
        case "off":
            await db.execute(f"UPDATE modules SET randomizer=false WHERE account_id={account_id}")  # Выключение рандомайзера
    await callback_query.message.edit_text(**await randomizer_menu(account_id))


@dp.callback_query(F.data == "currencies")
@security()
async def _currencies(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await currencies_menu(callback_query.message.chat.id))


async def currencies_menu(account_id: int, text: str = None) -> dict[str, Any]:
    buttons = []
    function = await db.fetch_one(f"SELECT currencies, morning_currencies, main_currency FROM modules WHERE account_id={account_id}") or \
               {'currencies': None, 'morning_currencies': None, 'main_currency': None}  # Для незарегистрированных пользователей
    if function['currencies']:  # Вкл/выкл конвертера валют
        buttons.append([IButton(text="🔴 Выключить", callback_data="currencies_off"),
                        IButton(text=function['main_currency'] or "Основная валюта", callback_data="main_currency")])
    else:
        buttons.append([IButton(text="🟢 Включить Конвертер", callback_data="currencies_on")])
    if function['morning_currencies']:
        buttons.append([IButton(text="🔴 Утром", callback_data="morning_currencies_off"),
                        IButton(text="Список валют", callback_data="my_currencies")])
    else:
        buttons.append([IButton(text="🟢 Курсы валют утром", callback_data="morning_currencies_on")])
    link = await generate_sensitive_link(account_id, "module-currencies", "курсы-валют")
    markup = IMarkup(inline_keyboard=[*buttons,
                                      [IButton(text="Как узнать курс?", url=link)],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": text or "💱 <b>Конвертер валют в чате</b>\nКонвертирует валюты по запросу в любом чате\n<blockquote>Курс доллара\n"
                    "Курс доллара к рублю\n5 долларов\n10 usdt\n15 ton в рублях</blockquote>", "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data.in_(["currencies_on", "currencies_off", "morning_currencies_on", "morning_currencies_off"]))
@security()
async def _currencies_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    function = "_".join(callback_query.data.split("_")[:-1])
    account_id = callback_query.from_user.id
    if await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True) is None:
        return await callback_query.answer("Maksogram в чате доступен только пользователям Maksogram", True)
    text = "Теперь по команде в любом чате я буду сообщать о курсе нужной валюты" if function == "currencies" else \
        "Теперь по утрам я буду сообщать о курсах выбранных валют"
    match command:
        case "on":
            await callback_query.answer(text, True)
            await db.execute(f"UPDATE modules SET {function}=true WHERE account_id={account_id}")  # Включение конвертера валют
        case "off":
            await db.execute(f"UPDATE modules SET {function}=false WHERE account_id={account_id}")  # Выключение конвертера валют
    await callback_query.message.edit_text(**await currencies_menu(account_id))


@dp.callback_query(F.data == "main_currency")
@security('state')
async def _main_currency_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.main_currency)
    markup = RMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    currencies_list = ''.join([("" if i == 0 else "\n" if i % 2 == 0 else ",  ") + currency for i, currency in
                               enumerate([f"{currency} ({currencies[currency][0]})" for currency in currencies])])
    message_id = (await callback_query.message.answer(
        "Выберите валюту по умолчанию (например, usd), в которую будет конвертироваться другие по команде, например:\n<blockquote>"
        f"Курс биткоина</blockquote>\nДоступные валюты:\n<blockquote>{currencies_list}</blockquote>", parse_mode=html, reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.main_currency)
@security('state')
async def _main_currency(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']
    await state.clear()
    if message.text == "Отмена":
        await message.answer(**await currencies_menu(account_id))
    elif (currency := message.text.upper()) in currencies:
        await db.execute(f"UPDATE modules SET main_currency='{currency}' WHERE account_id={account_id}")
        await message.answer(**await currencies_menu(account_id))
    else:
        await message.answer(**await currencies_menu(account_id, "<b>Валюта не найдена!</b>"))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data == "my_currencies")
@security('state')
async def _my_currencies_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.my_currencies)
    markup = RMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer(
        "Выберите валюты через запятую, курсы которых будут присылаться по утрам, например:\n"
        "<blockquote>RUB, USD, BTC, ETH</blockquote>", parse_mode=html, reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.my_currencies)
@security('state')
async def _my_currencies(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']
    await state.clear()
    if message.text == "Отмена":
        await message.answer(**await currencies_menu(account_id))
    elif all(map(lambda x: x.upper() in currencies, my_currencies := message.text.replace(" ", "").split(","))):
        await db.execute(f"UPDATE modules SET my_currencies=$1 WHERE account_id={account_id}", json_encode(my_currencies))
        await message.answer(**await currencies_menu(account_id, "Список валют изменен успешно, только их курсы будут утром"))
    else:
        await message.answer(**await currencies_menu(account_id, "<b>Одна из валют не определена! Пожалуйста, перечислите "
                                                                 "нужные валюты через запятую, как в примере</b>"))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


def modules_initial():
    pass  # Чтобы PyCharm не ругался
