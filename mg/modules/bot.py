import orjson

from mg.config import WEB_APP, CHANNEL

from aiogram import F

from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from mg.bot.types import dp, bot, CallbackData, UserState
from aiogram.types import WebAppInfo, CallbackQuery, Message
from mg.bot.functions import new_callback_query, new_message, preview_options

from aiogram.types import KeyboardButton as KButton
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton

from typing import Any
from mg.core.functions import error_notify, get_subscription

from mg.modules.currencies import currencies
from . functions import enabled_module, set_status_module, get_main_currency, set_main_currency, set_my_currencies


cb = CallbackData()
modules = {
    'calculator': {
        'name': "Калькулятор",
        'preview': 'калькулятор',
        'text': "🔢 <b>Калькулятор в чате</b>\nРешает примеры разных уровней сложности от обычного умножения до длинных примеров\n"
                "<b>Для вызова укажите в конце \"=\"</b>\n<blockquote>10+5*15=</blockquote>"
    },
    'qr_code': {
        'name': "Генератор QR-кода",
        'preview': "генератор-qr",
        'text': f"🔗 <b>Генератор QR-кода</b>\nГенерирует обычный QR-код с нужной ссылкой в чате\n<blockquote>Создай t.me/{CHANNEL}\n"
                f"Создать t.me/{CHANNEL}\nСгенерировать t.me/{CHANNEL}\nСгенерируй t.me/{CHANNEL}\nQR t.me/{CHANNEL}</blockquote>"
    },
    'audio_transcription': {
        'name': "Конвертер ГС в текст",
        'preview': "расшифровка-гс",
        'text': "🗣 <b>Расшифровка голосовых</b>\nНе хотите слушать голосовое или кружок? Расшифруйте его в текст: "
                "свайпни и отправь команду\n<blockquote>Расшифруй\nРасшифровать\nВ текст</blockquote>"
    },
    'round_video': {
        'name': "Конвертер видео в кружок",
        'preview': "видео-в-кружок",
        'text': "🔄 <b>Конвертер видео в кружок</b>\nПонадобилось сделать из обычного видео кружок? Свайпни и отправь команду в любом чате\n"
                "<blockquote>В кружок</blockquote>"
    },
    'reminder': {
        'name': "Напоминалка",
        'preview': "напоминалка",
        'text': "⏰ <b>Напоминалка в чате</b>\nДля создания напоминания <b>нужно ответить</b> на любое сообщение в чате командой\n"
                "<blockquote expandable>Напомни через 5 минут\nНапомни через 5 часов\nНапомни через 5 часов 30 минут\n"
                "Напомни в 12:00\nНапомни завтра в 12.00\nНапомни 9 декабря в 12:00\n.......... или просто команда ..........\n"
                "Напомни через 5 минут покушать\nНапомни в 12:00 позвонить другу</blockquote>\n"
                "<blockquote>❗️ Для правильной работы Напоминалки выберите часовой пояс в /settings</blockquote>\n"
    },
    'randomizer': {
        'name': "Рандомайзер",
        'preview': "рандомайзер",
        'text': "🎲 <b>Рандомайзер в чате</b>\nMaksogram случайным образом выберет да или нет, число из диапазона или элемент из списка\n"
                "<blockquote>Выбери да или нет\nВыбери число от 0 до 10\nВыбери яблоко, банан или груша</blockquote>"
    },
    'weather': {
        'name': "Прогноз погоды",
        'preview': "погода",
        'text': "🌤 <b>Погода</b>\nЛегко получайте погоду за окном, не выходя из Telegram командой 👇\n<blockquote>"
                "Какая погода</blockquote>\n<blockquote>❗️ Для работы функции выберите город в /settings</blockquote>"
    },
    'currencies': {
        'name': "Курсы валют",
        'preview': "курсы-валют",
        'text': "💱 <b>Конвертер валют в чате</b>\nКонвертирует валюты по запросу в любом чате\n<blockquote>Курс доллара\n"
                "Курс доллара к рублю\n5 долларов\n10 usdt\n15 ton в рублях</blockquote>"
    }
}

# Список доступных валют в формате - RUB (рубль) - по две в строке
currencies_table = ''.join([("" if i == 0 else "\n" if i % 2 == 0 else ",  ") + currency
                            for i, currency in enumerate([f"{currency} ({currencies[currency][0]})" for currency in currencies])])


@dp.message(Command('menu_chat'))
@error_notify()
async def _menu_chat(message: Message):
    if await new_message(message): return
    await message.answer(**modules_menu())


@dp.callback_query(F.data.startswith(cb.command('modules')))
@error_notify()
async def _modules(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    prev = cb.deserialize(callback_query.data).get(0) is True
    await callback_query.message.edit_text(**modules_menu(prev=prev))


def modules_menu(prev: bool = False) -> dict[str, Any]:
    markup = IMarkup(inline_keyboard=[[IButton(text="🔢 Калькулятор", callback_data=cb('module', 'calculator', prev)),
                                       IButton(text="🌤 Погода", callback_data=cb('module', 'weather', prev))],
                                      [IButton(text="🔗 Генератор QR", callback_data=cb('module', 'qr_code', prev)),
                                       IButton(text="🔗 Сканер QR", web_app=WebAppInfo(url=f"{WEB_APP}/main"))],
                                      [IButton(text="🗣 ГС в текст", callback_data=cb('module', 'audio_transcription', prev)),
                                       IButton(text="🔄 Видео в кружок", callback_data=cb('module', 'round_video', prev))],
                                      [IButton(text="⏰ Напоминалка", callback_data=cb('module', 'reminder', prev)),
                                       IButton(text="🎲 Рандомайзер", callback_data=cb('module', 'randomizer', prev))],
                                      [IButton(text="💱 Конвертер валют", callback_data=cb('module', 'currencies', prev))],
                                      [IButton(text="◀️  Назад", callback_data=cb('menu'))]])

    return dict(
        text="💬 <b>Maksogram в чате</b>\nФункции, которые работают прямо из любого чата, не нужно писать мне", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('module')))
@error_notify()
async def _module(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    module, prev = cb.deserialize(callback_query.data)
    await callback_query.message.edit_text(**await module_menu(callback_query.from_user.id, module, prev))


async def module_menu(account_id: int, module: str, prev: bool = False) -> dict[str, Any]:
    module = module.removeprefix('morning_').removeprefix('auto_')
    buttons = []

    if await enabled_module(account_id, module):
        main_currency_button = []
        if module == 'currencies':
            main_currency = await get_main_currency(account_id)
            main_currency_button = [IButton(text=main_currency or "Основная валюта", callback_data=cb('main_currency'))]

        buttons.append([IButton(text=f"🟢 {modules[module]['name']}", callback_data=cb('module_switch', module, False, prev)),
                        *main_currency_button])
    else:
        buttons.append([IButton(text=f"🔴 {modules[module]['name']}", callback_data=cb('module_switch', module, True, prev))])

    if module in ('weather', 'currencies'):
        if await enabled_module(account_id, f"morning_{module}"):
            my_currencies_button = []
            if module == 'currencies':
                my_currencies_button = [IButton(text="Список валют", callback_data=cb('my_currencies'))]

            buttons.append([IButton(text=f"🟢 {modules[module]['name']} по утрам",
                                    callback_data=cb('module_switch', f"morning_{module}", False, prev)),
                            *my_currencies_button])
        else:
            buttons.append([IButton(text=f"🔴 {modules[module]['name']} по утрам",
                                    callback_data=cb('module_switch', f"morning_{module}", True, prev))])

    if module == 'audio_transcription':
        status = await enabled_module(account_id, f"auto_{module}")
        indicator = "🟢" if status else "🔴"
        buttons.append([IButton(text=f"{indicator} Автоматическая расшифровка",
                                callback_data=cb('module_switch', f"auto_{module}", not status, prev))])

    link_preview_options = preview_options(f"{modules[module]['preview']}.mp4", show_above_text=True)
    markup = IMarkup(inline_keyboard=[*buttons,
                                      [IButton(text="◀️  Назад", callback_data=cb('modules', prev))]])

    return dict(text=modules[module]['text'], reply_markup=markup, link_preview_options=link_preview_options)


@dp.callback_query(F.data.startswith(cb('module_switch')))
@error_notify()
async def _module_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    module, command, prev = cb.deserialize(callback_query.data)

    if prev:
        await callback_query.answer("Запустите Maksogram кнопкой в меню", True)
        return

    if module == 'auto_audio_transcription' and await get_subscription(account_id) is None:
        await callback_query.answer("Автоматическая расшифровка доступна только с Maksogram Premium!", True)
        return

    await set_status_module(account_id, module, command)

    await callback_query.message.edit_text(**await module_menu(account_id, module, prev))


@dp.callback_query(F.data.startswith(cb.command('main_currency')))
@error_notify('state')
async def _main_currency_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.main_currency)

    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer(
        "Выберите валюту по умолчанию (например, RUB), в которую будет конвертироваться другие по команде, например:\n"
        f"<blockquote>Курс биткоина</blockquote>\nДоступные валюты:\n<blockquote>{currencies_table}</blockquote>", reply_markup=markup)).message_id

    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.main_currency)
@error_notify('state')
async def _main_currency(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']
    await state.clear()

    if message.text == "Отмена":
        await message.answer(**await module_menu(account_id, 'currencies'))

    elif (currency := message.text.upper()) in currencies:
        await set_main_currency(account_id, currency)
        await message.answer(**await module_menu(account_id, 'currencies'))

    else:
        markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
        new_message_id = (await message.answer(
            f"Выберите валюту по умолчанию\n<blockquote>{currencies_table}</blockquote>", reply_markup=markup)).message_id

        await state.set_state(UserState.main_currency)
        await state.update_data(message_id=new_message_id)

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data.startswith(cb.command('my_currencies')))
@error_notify('state')
async def _my_currencies_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    await state.set_state(UserState.my_currencies)

    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer(
        "Выберите валюты, курсы которых будут присылаться по утрам\nСписок доступных:\n"
        f"<blockquote>{currencies_table}</blockquote>", reply_markup=markup)).message_id

    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.my_currencies)
@error_notify('state')
async def _my_currencies(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']
    await state.clear()

    my_currencies = message.text.upper().replace(' ', '').split(',')

    if message.text == "Отмена":
        await message.answer(**await module_menu(account_id, 'currencies'))

    elif all([currency in currencies for currency in my_currencies]):
        await set_my_currencies(account_id, orjson.dumps(my_currencies).decode())
        await message.answer(**await module_menu(account_id, 'currencies'))

    else:
        markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
        new_message_id = (await message.answer(
            f"Список доступных:\n<blockquote>{currencies_table}</blockquote>", reply_markup=markup)).message_id

        await state.set_state(UserState.my_currencies)
        await state.update_data(message_id=new_message_id)

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


def modules_initial():
    pass  # Чтобы PyCharm не ругался