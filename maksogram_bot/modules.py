from typing import Any
from core import (
    db,
    html,
    SITE,
    morning,
    channel,
    security,
)

from aiogram import F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from aiogram.types import Message, CallbackQuery, WebAppInfo
from .core import (
    dp,
    Data,
    new_message,
    new_callback_query,
)


@dp.message(Command('menu_chat'))
@security()
async def _menu_chat(message: Message):
    if await new_message(message): return
    await message.answer(**modules_menu())


@dp.callback_query(F.data == "modules")
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
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="Как работает Калькулятор?", url=f"{SITE}#калькулятор")],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "🔢 <b>Калькулятор в чате</b>\nРешает примеры разных уровней сложности от обычного умножения до "
                    "длинных примеров\n<b>Для вызова укажите в конце \"=\"</b>\n<blockquote>10+5*15=</blockquote>",
            "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data.in_(["calculator_on", "calculator_off"]))
@security()
async def _calculator_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET calculator=true WHERE account_id={callback_query.from_user.id}")
        case "off":
            await db.execute(f"UPDATE modules SET calculator=false WHERE account_id={callback_query.from_user.id}")
    await callback_query.message.edit_text(**await calculator_menu(callback_query.message.chat.id))


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
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="Как работает Генератор QR?", url=f"{SITE}#генератор-qr")],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": f"🔗 <b>Генератор QR-кода</b>\nГенерирует обычный QR-код с нужной ссылкой в чате\n<blockquote>Создай t.me/{channel}\n"
                    f"Создать t.me/{channel}\nСгенерировать t.me/{channel}\nСгенерируй t.me/{channel}\nQR t.me/{channel}</blockquote>",
            "reply_markup": markup, "parse_mode": html, "disable_web_page_preview": True}


@dp.callback_query(F.data.in_(["qrcode_on", "qrcode_off"]))
@security()
async def _qrcode_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET qrcode=true WHERE account_id={callback_query.from_user.id}")  # Включение QR
        case "off":
            await db.execute(f"UPDATE modules SET qrcode=false WHERE account_id={callback_query.from_user.id}")  # Выключение QR
    await callback_query.message.edit_text(**await qrcode_menu(callback_query.message.chat.id))


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
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="Как расшифровать ГС?", url=f"{SITE}#расшифровка-гс")],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "🗣 <b>Расшифровка голосовых</b>\nНе хотите слушать голосовое? Расшифруйте его в текст\n"
                    "<blockquote>Расшифруй, расшифровать, в текст</blockquote>", "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data.in_(["audio_transcription_on", "audio_transcription_off"]))
@security()
async def _audio_transcription_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET audio_transcription=true WHERE account_id={callback_query.from_user.id}")  # Включение расшифровки
        case "off":
            await db.execute(f"UPDATE modules SET audio_transcription=false WHERE account_id={callback_query.from_user.id}")  # Выключение расшифровки
    await callback_query.message.edit_text(**await audio_transcription_menu(callback_query.message.chat.id))


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
    if await db.fetch_one(f"SELECT morning_weather FROM modules WHERE account_id={account_id}", one_data=True):  # Вкл/выкл погода по утрам
        status_button_morning_weather = IButton(text="🔴 Выключить утреннюю Погоду", callback_data="morning_weather_off")
    else:
        status_button_morning_weather = IButton(text="🟢 Включить утреннюю Погоду", callback_data="morning_weather_on")
    markup = IMarkup(inline_keyboard=[[status_button_weather],
                                      [status_button_morning_weather],
                                      [IButton(text="Как получить прогноз?", url=f"{SITE}#погода")],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "🌤 <b>Погода</b>\nЛегко получайте погоду за окном, не выходя из Telegram командой 👇\n<blockquote>"
                    "Какая погода</blockquote>\n<blockquote>❗️ Погода по утрам присылается, когда вы первый раз зашли в Telegram "
                    f"с {morning[0]}:00 до {morning[1]}:00</blockquote>", "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data.in_(["weather_on", "weather_off"]))
@security()
async def _weather_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET weather=true WHERE account_id={callback_query.from_user.id}")  # Включение погоды
        case "off":
            await db.execute(f"UPDATE modules SET weather=false WHERE account_id={callback_query.from_user.id}")  # Выключение погоды
    await callback_query.message.edit_text(**await weather_menu(callback_query.message.chat.id))


@dp.callback_query(F.data.in_(["morning_weather_on", "morning_weather_off"]))
@security()
async def _morning_weather_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    account_id = callback_query.from_user.id
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET morning_weather=true WHERE account_id={account_id}")  # Включение погоды по утрам
        case "off":
            await db.execute(f"UPDATE modules SET morning_weather=false WHERE account_id={account_id}")  # Выключение погоды по утрам
    await callback_query.message.edit_text(**await weather_menu(callback_query.message.chat.id))


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
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="Как создать кружок?", url=f"{SITE}#видео-в-кружок")],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "🔄 <b>Конвертер видео в кружок</b>\nПонадобилось сделать из обычного видео кружок? Сделай это командой\n"
                    "<blockquote>Кружок</blockquote>", "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data.in_(["round_video_on", "round_video_off"]))
@security()
async def _round_video_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET round_video=true WHERE account_id={callback_query.from_user.id}")  # Включение конвертера
        case "off":
            await db.execute(f"UPDATE modules SET round_video=false WHERE account_id={callback_query.from_user.id}")  # Выключение конвертера
    await callback_query.message.edit_text(**await round_video_menu(callback_query.message.chat.id))


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
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="Как пользоваться Напоминалкой?", url=f"{SITE}#напоминалка")],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "⏰ <b>Напоминалка в чате</b>\nДля создания напоминания <b>нужно ответить</b> на любое сообщение в чате командой\n"
                    "<blockquote expandable><b>Примеры</b>:\nНапомни через 5 минут\nНапомни через 5 часов\nНапомни через "
                    "5 часов 30 минут\nНапомни в 12:00\nНапомни завтра в 12.00\nНапомни 9 декабря в 12:00</blockquote>",
                    "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data.in_(["reminder_on", "reminder_off"]))
@security()
async def _reminder_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET reminder=true WHERE account_id={callback_query.from_user.id}")  # Включение напоминалки
        case "off":
            await db.execute(f"UPDATE modules SET reminder=false WHERE account_id={callback_query.from_user.id}")  # Выключение напоминалки
    await callback_query.message.edit_text(**await reminder_menu(callback_query.message.chat.id))


@dp.callback_query(F.data == "randomizer")
@security()
async def _randomizer(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await randomizer_menu(callback_query.message.chat.id))


async def randomizer_menu(account_id: int) -> dict[str, Any]:
    if await db.fetch_one(f"SELECT randomizer FROM modules WHERE account_id={account_id}", one_data=True):  # Вкл/выкл напоминалки
        status_button = IButton(text="🔴 Выключить Рандомайзер", callback_data="randomizer_off")
    else:
        status_button = IButton(text="🟢 Включить Рандомайзер", callback_data="randomizer_on")
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="Как пользоваться Рандомайзером?", url=f"{SITE}#рандомайзер")],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "🎲 <b>Рандомайзер в чате</b>\n<blockquote>Выбери да или нет\nВыбери число от 0 до 10\n"
                    "Выбери яблоко, банан или груша</blockquote>", "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data.in_(["randomizer_on", "randomizer_off"]))
@security()
async def _randomizer_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    command = callback_query.data.split("_")[-1]
    match command:
        case "on":
            await db.execute(f"UPDATE modules SET randomizer=true WHERE account_id={callback_query.from_user.id}")  # Включение рандомайзера
        case "off":
            await db.execute(f"UPDATE modules SET randomizer=false WHERE account_id={callback_query.from_user.id}")  # Выключение рандомайзера
    await callback_query.message.edit_text(**await randomizer_menu(callback_query.message.chat.id))


def modules_initial():
    pass  # Чтобы PyCharm не ругался
