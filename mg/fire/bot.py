from mg.config import WWW_SITE

from aiogram import F

from aiogram.fsm.context import FSMContext
from mg.client.types import maksogram_clients
from mg.bot.types import dp, bot, CallbackData, UserState
from aiogram.types import CallbackQuery, Message, KeyboardButtonRequestUsers
from mg.bot.functions import new_callback_query, new_message, request_user, preview_options

from aiogram.types import KeyboardButton as KButton
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton

from typing import Any
from mg.core.functions import error_notify, full_name, time_now, get_subscription


cb = CallbackData()


@dp.callback_query(F.data.startswith(cb.command('fires')))
@error_notify()
async def _fire(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.answer("В разработке!", True)


def fire_initial():
    pass  # Чтобы PyCharm не ругался
