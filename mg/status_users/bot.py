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

from . statistics import online_statistics
from . functions import (
    add_status_user,
    get_user_settings,
    get_users_settings,
    update_status_user,
    delete_status_user,
    check_count_status_users,
)


cb = CallbackData()


@dp.callback_query(F.data.startswith(cb.command('status_users')))
@error_notify()
async def _status_users(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    prev = cb.deserialize(callback_query.data).get(0) is True
    await callback_query.message.edit_text(**await status_users_menu(callback_query.from_user.id, prev=prev))


async def status_users_menu(account_id: int, prev: bool = False) -> dict[str, Any]:
    users = [] if prev else await get_users_settings(account_id)

    i, buttons = 0, []
    while i < len(users):  # Если длина имен достаточно короткая, то помещаем 2 в ряд, иначе 1
        if i+1 < len(users) and len(users[i].name) <= 15 and len(users[i+1].name) <= 15:
            buttons.append([IButton(text=f"🌐 {users[i].name}", callback_data=cb('status_user', users[i].id)),
                            IButton(text=f"🌐 {users[i+1].name}", callback_data=cb('status_user', users[i+1].id))])
            i += 1
        else:
            buttons.append([IButton(text=f"🌐 {users[i].name}", callback_data=cb('status_user', users[i].id))])
        i += 1

    buttons.append([IButton(text="➕ Добавить нового пользователя", callback_data=cb('new_status_user', prev))])
    buttons.append([IButton(text="◀️  Назад", callback_data=cb('menu'))])

    return dict(
        text="🌐 <b>Друг в сети</b>\nУведомления о входе/выходе из сети, пробуждении, прочтения сообщения, а также статистика онлайн\n"
             "<blockquote>⛔️ Не работает, если собеседник скрыл время последнего захода...</blockquote>", reply_markup=IMarkup(inline_keyboard=buttons),
        link_preview_options=preview_options('друг-в-сети.mp4', show_above_text=True))


@dp.callback_query(F.data.startswith(cb.command('new_status_user')))
@error_notify('state')
async def _new_status_user_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    prev = cb.deserialize(callback_query.data).get(0) is True
    if prev:
        await callback_query.answer("Запустите Maksogram кнопкой в меню", True)
        return

    if not await check_count_status_users(account_id):
        if await get_subscription(account_id) is None:
            await callback_query.answer("Достигнут лимит пользователей, подключите Maksogram Premium", True)
        else:
            await callback_query.answer("Достигнут лимит количества пользователей", True)
        return

    await state.set_state(UserState.new_status_user)

    request = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False, max_quantity=1)
    markup = KMarkup(keyboard=[[KButton(text="Себя"), KButton(text="Выбрать", request_users=request)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте пользователя для отслеживания кнопкой, ID, username или номер телефона",
                                                      reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.new_status_user)
@error_notify('state')
async def _new_status_user(message: Message, state: FSMContext):
    if await new_message(message): return
    account_id = message.chat.id
    message_id = (await state.get_data())['message_id']

    if message.text == "Отмена":
        await state.clear()
        await message.answer(**await status_users_menu(account_id))
    else:
        response = await request_user(message)

        if not response.ok:
            request = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False, max_quantity=1)
            markup = KMarkup(keyboard=[[KButton(text="Себя"), KButton(text="Выбрать", request_users=request)],
                                       [KButton(text="Отмена")]], resize_keyboard=True)
            new_message_id = (await message.answer(response.warning, reply_markup=markup)).message_id
            await state.update_data(message_id=new_message_id)
        else:
            await state.clear()
            name = "Мой аккаунт" if response.user.id == account_id else full_name(response.user)

            maksogram_clients[account_id].add_status_user(response.user.id)
            await add_status_user(account_id, response.user.id, name)

            await message.answer(**await status_user_menu(account_id, response.user.id))

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message_id, message.message_id])


@dp.callback_query(F.data.startswith(cb.command('status_user')))
@error_notify()
async def _status_user(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    data = cb.deserialize(callback_query.data)
    user_id, new = data[0], data.get(1)

    if new:
        await callback_query.answer()
        await callback_query.message.answer(**await status_user_menu(callback_query.from_user.id, user_id))
    else:
        await callback_query.message.edit_text(**await status_user_menu(callback_query.from_user.id, user_id))


async def status_user_menu(account_id: int, user_id: int) -> dict[str, Any]:
    indicator = lambda status: "🟢" if status else "🔴"

    user = await get_user_settings(account_id, user_id)
    if user is None:
        return await status_users_menu(account_id)

    if user_id == account_id:
        markup = IMarkup(inline_keyboard=[[IButton(text=f"Статистика ↙️", callback_data=cb('status_user_statistics', user_id))],
                                          [IButton(text="🚫 Удалить пользователя", callback_data=cb('del_status_user', user_id))],
                                          [IButton(text="◀️  Назад", callback_data=cb('status_users'))]])
        return dict(
            text="🌐 <b>Друг в сети</b>\nЗдесь вы можете посмотреть статистику онлайн для своего аккаунта за день, неделю и месяц\n"
                 "<blockquote>Для других пользователей доступны и другие функции</blockquote>", reply_markup=markup)

    warning = "<blockquote>❗️ Для улучшения точности выберите часовой пояс в /settings</blockquote>" if user.awake else ''
    markup = IMarkup(inline_keyboard=[[IButton(text=f"{indicator(user.online)} Онлайн",
                                               callback_data=cb('status_user_switch', user_id, 'online', not user.online)),
                                       IButton(text=f"{indicator(user.offline)} Оффлайн",
                                               callback_data=cb('status_user_switch', user_id, 'offline', not user.offline))],
                                      [IButton(text=f"{indicator(user.awake)} Проснется 💤",
                                               callback_data=cb('status_user_switch', user_id, 'awake', not user.awake)),
                                       IButton(text="Статистика ↙️",
                                               callback_data=cb('status_user_statistics', user_id))],
                                      [IButton(text=f"{indicator(user.reading)} Чтение моего сообщения",
                                               callback_data=cb('status_user_switch', user_id, 'reading', not user.reading))],
                                      [IButton(text="🚫 Удалить пользователя", callback_data=cb('del_status_user', user_id))],
                                      [IButton(text="◀️  Назад", callback_data=cb('status_users'))]])

    return dict(
        text=f"🌐 <b>Друг в сети</b>\nКогда <b>{user.name}</b> будет онлайн/оффлайн, проснется или прочитает сообщение, придет уведомление. "
             f"В разделе статистика собираются данные об онлайн за день, неделю и месяц\n{warning}", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('status_user_switch')))
@error_notify()
async def _status_user_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    user_id, function, command = cb.deserialize(callback_query.data)

    user = await get_user_settings(account_id, user_id)
    if not user:
        await callback_query.message.edit_text(**await status_users_menu(account_id))
        return

    if command == user.__getattribute__(function) is not None:  # function может быть awake, тогда атрибут будет Optional[datetime]
        await callback_query.answer()
        return

    value = command
    if function == 'awake':
        value = time_now() if command else None
    await update_status_user(account_id, user_id, function, value)

    if function == 'statistics':
        await callback_query.message.edit_text(**await status_user_statistics_menu(account_id, user_id))
    else:
        await callback_query.message.edit_text(**await status_user_menu(account_id, user_id))


@dp.callback_query(F.data.startswith(cb.command('status_user_statistics')))
@error_notify()
async def _status_user_statistics(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    user_id = cb.deserialize(callback_query.data)[0]
    await callback_query.message.edit_text(**await status_user_statistics_menu(callback_query.from_user.id, user_id))


async def status_user_statistics_menu(account_id: int, user_id: int, period: str = None, offset: int = None) -> dict[str, Any]:
    user = await get_user_settings(account_id, user_id)
    if user is None:
        return await status_users_menu(account_id)

    period_buttons = [IButton(text="📊 День", callback_data=cb('status_user_statistics_watch', user_id, 'day', 0)),
                      IButton(text="📊 Неделя", callback_data=cb('status_user_statistics_watch', user_id, 'week', 0)),
                      IButton(text="📊 Месяц", callback_data=cb('status_user_statistics_watch', user_id, 'month', 0))]

    if period:  # Просмотр статистики
        name = "себя" if user_id == account_id else user.name
        left_offset, right_offset = offset + 1, offset - 1
        left_button, right_button = "⬅️", "➡️" if right_offset >= 0 else "🚫"

        markup = IMarkup(inline_keyboard=[
            period_buttons,
            [IButton(text=left_button, callback_data=cb('status_user_statistics_watch', user_id, period, left_offset)),
             IButton(text=right_button, callback_data=cb('status_user_statistics_watch', user_id, period, right_offset))],
            [IButton(text="◀️  Назад", callback_data=cb('status_user', user_id))]])

        return dict(text=f"🌐 <b>Статистика для {name}</b>", reply_markup=markup)

    if user.statistics:
        markup = IMarkup(inline_keyboard=[
            [IButton(text="🟢 Выключить сбор статистики", callback_data=cb('status_user_switch', user_id, 'statistics', False))],
            period_buttons,
            [IButton(text="◀️  Назад", callback_data=cb('status_user', user_id))]])
    else:
        markup = IMarkup(inline_keyboard=[
            [IButton(text="🔴 Включить сбор статистики", callback_data=cb('status_user_switch', user_id, 'statistics', True))],
            [IButton(text="◀️  Назад", callback_data=cb('status_user', user_id))]])

    return dict(
        text="🌐 <b>Статистика друга в сети</b>\nЗдесь вы можете вкл/выкл сбор статистики и посмотреть ее "
             "в виде наглядных графиков и диаграмм за день, неделю или месяц", reply_markup=markup)


@dp.callback_query(F.data.startswith(cb.command('status_user_statistics_watch')))
@error_notify()
async def _status_user_statistics_watch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    user_id, period, offset = cb.deserialize(callback_query.data)

    user = await get_user_settings(account_id, user_id)
    if user is None:
        await callback_query.message.edit_text(**await status_users_menu(account_id))
        return

    if not user.statistics:
        await callback_query.message.edit_text(**await status_user_statistics_menu(account_id, user_id))
        return

    if offset == -1:
        await callback_query.answer("Вы дошли до текущего периода!", True)
        return

    link = await online_statistics(account_id, user, period, offset)
    link_preview_options = preview_options(f"{link}?time={int(time_now().timestamp())}", site=WWW_SITE, show_above_text=True)

    await callback_query.message.edit_text(**await status_user_statistics_menu(account_id, user_id, period, offset),
                                           link_preview_options=link_preview_options)


@dp.callback_query(F.data.startswith(cb.command('del_status_user')))
@error_notify()
async def _del_status_user(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    user_id = cb.deserialize(callback_query.data)[0]

    maksogram_clients[account_id].delete_status_user(user_id)
    await delete_status_user(account_id, user_id)

    await callback_query.message.edit_text(**await status_users_menu(account_id))


def status_users_initial():
    pass  # Чтобы PyCharm не ругался
