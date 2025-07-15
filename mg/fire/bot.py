from mg.config import OWNER, WWW_SITE

from aiogram import F

from aiogram.fsm.context import FSMContext
from mg.client.functions import get_is_started
from aiogram.exceptions import TelegramBadRequest
from mg.bot.types import dp, bot, CallbackData, UserState
from mg.bot.functions import new_callback_query, new_message, preview_options, new_inline_query, new_inline_result
from aiogram.types import (
    Message,
    InlineQuery,
    CallbackQuery,
    ChosenInlineResult,
    InputTextMessageContent,
    InlineQueryResultArticle,
    SwitchInlineQueryChosenChat,
)

from aiogram.types import KeyboardButton as KButton
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton

from typing import Any
from mg.core.functions import error_notify, get_subscription, format_error

from . types import fire_levels
from . functions import get_fires, check_count_fires, get_fire, edit_fire_name, edit_fire_message, recover_fire, delete_fire


MAX_LENGTH_FIRE_NAME = 64
cb = CallbackData()


@dp.callback_query(F.data.startswith(cb.command('fires')))
@error_notify()
async def _fire(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    prev = cb.deserialize(callback_query.data).get(0) is True
    await callback_query.message.edit_text(**await fires_menu(callback_query.from_user.id, prev=prev))


async def fires_menu(account_id: int, prev: bool = False) -> dict[str, Any]:
    fires = [] if prev else await get_fires(account_id)

    i, buttons = 0, []
    while i < len(fires):  # Если длина имен достаточно короткая, то помещаем 2 в ряд, иначе 1
        if i + 1 < len(fires) and len(fires[i].name) <= 15 and len(fires[i+1].name) <= 15:
            buttons.append([IButton(text=f"🔥 {fires[i].name}", callback_data=cb('fire', fires[i].user_id)),
                            IButton(text=f"🔥 {fires[i+1].name}", callback_data=cb('fire', fires[i+1].user_id))])
            i += 1
        else:
            buttons.append([IButton(text=f"🔥 {fires[i].name}", callback_data=cb('fire', fires[i].user_id))])
        i += 1

    switch = SwitchInlineQueryChosenChat(query="огонек", allow_user_chats=True)
    buttons.append([IButton(text="➕ Создать огонек", switch_inline_query_chosen_chat=switch)])
    buttons.append([IButton(text="◀️  Назад", callback_data=cb('menu'))])

    return dict(text="🔥 <b>Огонек с другом</b>\nСоздайте огонек в чате, чтобы расти его вместе. Увеличивайте счет и достигайте новых уровней",
                reply_markup=IMarkup(inline_keyboard=buttons))


@dp.inline_query(F.query == 'огонек')
@error_notify()
async def _new_fire_start(inline_query: InlineQuery):
    if await new_inline_query(inline_query): return
    await inline_query.answer([InlineQueryResultArticle(
        id="new_fire", title="🔥 Создать огонек с другом", thumbnail_url=f"{WWW_SITE}/{fire_levels[1].photo}", thumbnail_width=640, thumbnail_height=640,
        description = "Создавайте огоньки в чате с друзьями и растите их вместе. Увеличивайте счет и достигайте новых уровней",
        input_message_content=InputTextMessageContent(
            message_text="🔥 Загрузка данных..."
        ),
        reply_markup=IMarkup(inline_keyboard=[[IButton(text="🔥 🔥 🔥", callback_data=cb('inline_fire'))]])
    )], cache_time=0, is_personal=True)


@dp.chosen_inline_result()
@error_notify()
async def _new_fire(inline_result: ChosenInlineResult):
    if await new_inline_result(inline_result): return
    account_id = inline_result.from_user.id
    inline_message_id = inline_result.inline_message_id

    if not await check_count_fires(account_id):
        if await get_subscription(account_id) is None:
            await bot.edit_message_text("Достигнут лимит огоньков с друзьями, подключите Maksogram Premium!", inline_message_id=inline_message_id)
        else:
            await bot.edit_message_text("Достигнут лимит количества огоньков с друзьями!", inline_message_id=inline_message_id)
        return

    if not await get_is_started(account_id):
        await bot.edit_message_text("Включите Maksogram кнопкой в меню бота", inline_message_id=inline_message_id)
        return

    # Ожидаем завершения создания огонька в message_edited (MasogramClient)
    await bot.edit_message_text(f"🔥 Создание огонька...\n<tg-spoiler>{inline_message_id}</tg-spoiler>", inline_message_id=inline_message_id,
                                reply_markup=IMarkup(inline_keyboard=[[IButton(text="🔥", callback_data=cb('inline_fire'))]]))


@dp.callback_query(F.data.startswith(cb.command('inline_fire')))
@error_notify()
async def _inline_fire(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    fire = await get_fire(inline_message_id=callback_query.inline_message_id)
    if fire is None:
        await callback_query.answer("Огонек с другом не найден...", True)
        return

    if fire.reset:
        await callback_query.answer("Восстановить огонек с другом может его создатель в меню бота", True)
    elif not fire.active:
        await callback_query.answer("Чтобы огонек не погас, напишите друг другу сообщения", True)
    else:
        await callback_query.answer("Чтобы управлять огоньком, нажмите на ссылку в сообщении", True)


@dp.callback_query(F.data.startswith(cb.command('fire')))
@error_notify()
async def _fire(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    user_id = cb.deserialize(callback_query.data)[0]
    await callback_query.message.edit_text(**await fire_menu(account_id, user_id))


async def fire_menu(account_id: int, user_id: int, from_link: bool = False) -> dict[str, Any]:
    fire = await get_fire(account_id, user_id)
    if fire is None:
        if from_link:
            return dict(text="🔥 Огонек с другом не найден...")
        return await fires_menu(account_id)

    back = [] if from_link else [[IButton(text="◀️  Назад", callback_data=cb('fires'))]]
    recovery = [] if from_link or not fire.reset else [[IButton(text="🔄 Восстановить", callback_data=cb('recovery_fire', user_id))]]
    markup = IMarkup(inline_keyboard=[[IButton(text="✏️ Изменить имя", callback_data=cb('edit_fire_name', account_id, user_id))],
                                      [IButton(text="🚫 Удалить огонек", callback_data=cb('del_fire', account_id, user_id))],
                                      *recovery,
                                      *back])

    return dict(
        text=f"🔥 <b>Огонек с другом</b>\nИмя: {fire.name}\nСерия: {fire.days} 🔥\nСчет: {fire.score} 💥\nОтправляйте друг другу голосовые и кружки "
             f"(>30сек), чтобы увеличить счет огонька", reply_markup=markup,
        link_preview_options=preview_options(fire.photo, site=WWW_SITE, show_above_text=True))


@dp.callback_query(F.data.startswith(cb.command('edit_fire_name')))
@error_notify('state')
async def _edit_fire_name_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    account_id, user_id = cb.deserialize(callback_query.data)

    markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("🔥 Как будут звать вашего огонька?", reply_markup=markup)).message_id

    await state.set_state(UserState.edit_fire_name)
    await state.update_data(account_id=account_id, user_id=user_id, message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.edit_fire_name)
@error_notify('state')
async def _edit_fire_name(message: Message, state: FSMContext):
    if await new_message(message): return
    data = await state.get_data()
    account_id = data['account_id']
    user_id = data['user_id']
    message_id = data['message_id']
    warning = None

    if message.text == "Отмена":
        await state.clear()
        await message.answer(**await fire_menu(account_id, user_id, from_link=message.chat.id != account_id))
    elif not (fire := await get_fire(account_id, user_id)):
        await state.clear()
        if message.chat.id == account_id:
            await message.answer(**await fires_menu(account_id))
        else:
            await message.answer("🔥 Огонек с другом не найден...")
    elif not message.text:
        warning = "Отправьте текстовое имя"
    elif len(message.text) > MAX_LENGTH_FIRE_NAME:
        warning = "Имя огонька слишком длинное"
    elif not await get_is_started(account_id):
        await state.clear()
        if message.chat.id == account_id:
            await message.answer("Включите Maksogram кнопкой в меню")
        else:
            await message.answer("Maksogram создателя огонька выключен...")
    elif message.text == fire.name:
        warning = "Имя огонька с другом уже названо так"
    else:
        await state.clear()

        await edit_fire_name(account_id, user_id, message.text)
        fire.name = message.text
        await message.answer(**await fire_menu(account_id, user_id, from_link=message.chat.id != account_id))

        try:
            await edit_fire_message(fire)
        except TelegramBadRequest:
            if account_id == message.chat.id:
                switch = SwitchInlineQueryChosenChat(query='огонек', allow_user_chats=True)
                await message.answer("Сообщение огонька в чате с другом удалено. Чтобы восстановить его, нажмите на кнопку и выберите чат",
                                     reply_markup=IMarkup(inline_keyboard=[[IButton(text="🔥 Восстановить", switch_inline_query_chosen_chat=switch)]]))
            else:
                await message.answer("Сообщение огонька в чате с другом удалено. Чтобы восстановить его, попросите друга создать его заново. "
                                     "При этом все данные с серией и счетом не будут потеряны")
        except Exception as e:
            await bot.send_message(OWNER, format_error(e))

    if warning:
        markup = KMarkup(keyboard=[[KButton(text="Отмена")]], resize_keyboard=True)
        new_message_id = (await message.answer(warning, reply_markup=markup)).message_id
        await state.update_data(message_id=new_message_id)

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data.startswith(cb.command('recovery_fire')))
@error_notify()
async def _recovery_fire(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    user_id = cb.deserialize(callback_query.data)[0]

    fire = await get_fire(account_id, user_id)
    if fire is None:
        await callback_query.message.answer(**await fires_menu(account_id))
        return

    if not fire.reset:
        await callback_query.message.edit_text(**await fire_menu(account_id, user_id))
        return

    if await get_subscription(account_id) is None:
        await callback_query.answer("Огонек можно восстановить только с Maksogram Premium", True)
        return

    await recover_fire(account_id, user_id)
    fire.reset = False

    await edit_fire_message(fire)
    await callback_query.answer("Огонек восстановлен! Больше не теряйте его...", True)
    await callback_query.message.edit_text(**await fire_menu(account_id, user_id))


@dp.callback_query(F.data.startswith(cb('del_fire')))
@error_notify()
async def _del_fire(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id, user_id = cb.deserialize(callback_query.data)

    fire = await get_fire(account_id, user_id)
    if fire is None:
        await callback_query.message.edit_text(**await fires_menu(account_id))
        return

    await delete_fire(account_id, user_id)
    if callback_query.from_user.id == account_id:
        await callback_query.message.edit_text(**await fires_menu(account_id))
    else:
        await callback_query.message.edit_text("🔥 Огонек с другом удален!")


def fire_initial():
    pass  # Чтобы PyCharm не ругался
