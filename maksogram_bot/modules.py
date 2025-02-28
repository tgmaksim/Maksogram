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
from aiogram.types import Message, CallbackQuery
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from .core import (
    dp,
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
                                      [IButton(text="🔗 Генератор QR-кодов", callback_data="qrcode")],
                                      [IButton(text="🗣 Расшифровка ГС", callback_data="audio_transcription")],
                                      [IButton(text="◀️  Назад", callback_data="menu")]])
    return {"text": "💬 <b>Maksogram в чате</b>\nФункции, которые работают прямо из любого чата, не нужно вызывать меня",
            "reply_markup": markup, "parse_mode": html}


@dp.callback_query(F.data == "calculator")
@security()
async def _calculator(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await calculator_menu(callback_query.message.chat.id))


async def calculator_menu(account_id: int) -> dict[str, Any]:
    if await db.fetch_one(f"SELECT calculator FROM modules WHERE account_id={account_id}", one_data=True):  # Вкл/выкл калькулятор
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
        status_button = IButton(text="🔴 Выключить генератор", callback_data="qrcode_off")
    else:
        status_button = IButton(text="🟢 Включить генератор", callback_data="qrcode_on")
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="Как работает генератор?", url=f"{SITE}#генератор-qr")],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "🔗 <b>Генератор QR-кодов</b>\nГенерирует QR-код с нужной ссылкой. "
                    f"Тригеры: создай, создать, qr, сгенерировать\n<blockquote>Создай t.me/{channel}</blockquote>",
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
        status_button = IButton(text="🔴 Выключить расшифровку", callback_data="audio_transcription_off")
    else:
        status_button = IButton(text="🟢 Включить расшифровку", callback_data="audio_transcription_on")
    markup = IMarkup(inline_keyboard=[[status_button],
                                      [IButton(text="Как пользоваться расшифровкой гс?", url=f"{SITE}#расшифровка-гс")],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "🗣 <b>Расшифровка ГС</b>\nНе хотите слушать голосовое? Расшифруйте его в текст. Тригеры: расшифруй, в текст",
            "reply_markup": markup, "parse_mode": html}


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
        status_button_weather = IButton(text="🔴 Выключить погоду", callback_data="weather_off")
    else:
        status_button_weather = IButton(text="🟢 Включить погоду", callback_data="weather_on")
    if await db.fetch_one(f"SELECT morning_weather FROM modules WHERE account_id={account_id}", one_data=True):  # Вкл/выкл погода по утрам
        status_button_morning_weather = IButton(text="🔴 Выключить утреннюю погоду", callback_data="morning_weather_off")
    else:
        status_button_morning_weather = IButton(text="🟢 Включить утреннюю погоду", callback_data="morning_weather_on")
    markup = IMarkup(inline_keyboard=[[status_button_weather],
                                      [status_button_morning_weather],
                                      [IButton(text="Как пользоваться погодой?", url=f"{SITE}#погода")],
                                      [IButton(text="◀️  Назад", callback_data="modules")]])
    return {"text": "🌤 <b>Погода</b>\nЛегко получайте погоду за окном, не выходя из Telegram. Тригеры: какая погода\n"
                    f"Погода по утрам присылается, когда вы первый раз зашли в Telegram с {morning[0]}:00 до {morning[1]}:00",
            "reply_markup": markup, "parse_mode": html}


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


def modules_initial():
    pass  # Чтобы PyCharm не ругался
