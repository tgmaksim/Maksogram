import matplotlib.pyplot as plt

from math import ceil
from typing import Any
from datetime import timedelta
from asyncpg.exceptions import UniqueViolationError
from core import (
    db,
    html,
    OWNER,
    security,
    time_now,
    www_path,
    WWW_SITE,
    preview_options,
    telegram_clients,
)

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from aiogram.types import KeyboardButton as KButton
from aiogram.types import KeyboardButtonRequestUsers
from aiogram.types import ReplyKeyboardMarkup as KMarkup
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton
from .core import (
    dp,
    bot,
    UserState,
    new_message,
    new_callback_query,
)


@dp.callback_query(F.data == "status_users")
@security()
async def _status_users(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await status_users_menu(callback_query.message.chat.id))


async def status_users_menu(account_id: int) -> dict[str, Any]:
    buttons = []
    users = await db.fetch_all(f"SELECT user_id, name FROM status_users WHERE account_id={account_id}")  # Список друзей в сети
    for user in users:
        buttons.append([IButton(text=f"🌐 {user['name']}", callback_data=f"status_user_menu{user['user_id']}")])
    buttons.append([IButton(text="➕ Добавить нового пользователя", callback_data="new_status_user")])
    buttons.append([IButton(text="◀️  Назад", callback_data="menu")])
    return {"text": "🌐 <b>Друг в сети</b>\nЯ уведомлю вас, если пользователь будет онлайн/офлайн. Вы также можете "
                    "посмотреть статистику онлайн\nНе работает, если собеседник скрыл время последнего захода...",
            "reply_markup": IMarkup(inline_keyboard=buttons), "parse_mode": html}


@dp.callback_query(F.data.startswith("status_user_menu"))
@security()
async def _status_user_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    params = callback_query.data.replace("status_user_menu", "").split("|")
    user_id = int(params[0])
    if len(params) >= 2:
        if params[1] == "new":
            await callback_query.message.edit_reply_markup()
            return await callback_query.message.answer(**await status_user_menu(callback_query.from_user.id, user_id))
    await callback_query.message.edit_text(**await status_user_menu(callback_query.from_user.id, user_id))


async def status_user_menu(account_id: int, user_id: int) -> dict[str, Any]:
    def status(parameter: bool):
        return "🟢" if parameter else "🔴"

    def command(parameter: bool):
        return "off" if parameter else "on"

    user = await db.fetch_one(f"SELECT name, online, offline, reading, awake, statistics FROM status_users "
                              f"WHERE account_id={account_id} AND user_id={user_id}")  # Данные о друге в сети
    if user is None:
        return await status_users_menu(account_id)
    markup = IMarkup(inline_keyboard=[
        [IButton(text=f"{status(user['online'])} Онлайн", callback_data=f"status_user_online_{command(user['online'])}_{user_id}"),
         IButton(text=f"{status(user['offline'])} Оффлайн", callback_data=f"status_user_offline_{command(user['offline'])}_{user_id}")],
        [IButton(text=f"{status(user['awake'])} Проснется 💤", callback_data=f"status_user_awake_{command(user['awake'])}_{user_id}"),
         IButton(text=f"Статистика ↙️", callback_data=f"status_user_statistics_menu{user_id}")],
        [IButton(text=f"{status(user['reading'])} Чтение моего сообщения", callback_data=f"status_user_reading_{command(user['reading'])}_{user_id}")],
        [IButton(text="🚫 Удалить пользователя", callback_data=f"status_user_del{user_id}")],
        [IButton(text="◀️  Назад", callback_data="status_users")]])
    return {"text": f"🌐 <b>Друг в сети</b>\nКогда <b>{user['name']}</b> будет онлайн/оффлайн, проснется или прочитает сообщение, "
                    "я сообщу. Также можно получить статистику онлайн за день", "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data.startswith("status_user_online_on").__or__(F.data.startswith("status_user_online_off")).__or__(
                   F.data.startswith("status_user_offline_on")).__or__(F.data.startswith("status_user_offline_off")).__or__(
                   F.data.startswith("status_user_reading_on")).__or__(F.data.startswith("status_user_reading_off")).__or__(
                   F.data.startswith("status_user_awake_on")).__or__(F.data.startswith("status_user_awake_off")).__or__(
                   F.data.startswith("status_user_statistics_on")).__or__(F.data.startswith("status_user_statistics_off")))
@security()
async def _status_user_switch(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    function_status_user, command, user_id = callback_query.data.replace("status_user_", "").split("_")
    user = await db.fetch_one(f"SELECT {function_status_user} FROM status_users WHERE account_id={account_id} AND user_id={user_id}")
    if user is None:  # Пользователь удален из списка друзей в сети
        return await callback_query.message.edit_text(**await status_users_menu(account_id))
    if (command == "on") == user[function_status_user]:  # Статус совпадает с нужным
        return await status_user_statistics_menu(account_id, int(user_id)) if function_status_user == "statistics" \
            else await status_user_menu(account_id, int(user_id))
    if function_status_user == "awake":
        await db.execute(f"UPDATE status_users SET {function_status_user}={'now()' if command == 'on' else 'NULL'} WHERE "
                         f"account_id={account_id} AND user_id={user_id}")  # Вкл/выкл функции
    else:
        await db.execute(f"UPDATE status_users SET {function_status_user}={'true' if command == 'on' else 'false'} WHERE "
                         f"account_id={account_id} AND user_id={user_id}")  # Вкл/выкл нужной функции друга в сети
        if function_status_user == "statistics":
            return await callback_query.message.edit_text(**await status_user_statistics_menu(account_id, int(user_id)))
    await callback_query.message.edit_text(**await status_user_menu(account_id, int(user_id)))


@dp.callback_query(F.data.startswith("status_user_statistics_menu"))
@security()
async def _status_user_statistics_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    user_id = int(callback_query.data.replace("status_user_statistics_menu", ""))
    await callback_query.message.edit_text(**await status_user_statistics_menu(account_id, user_id))


async def status_user_statistics_menu(account_id: int, user_id: int) -> dict[str, Any]:
    user = await db.fetch_one(f"SELECT statistics FROM status_users WHERE account_id={account_id} AND user_id={user_id}")
    if user is None:
        return await status_users_menu(account_id)
    if user['statistics']:  # Сбор статистики включен
        markup = IMarkup(inline_keyboard=[[IButton(text="🔴 Выключить", callback_data=f"status_user_statistics_off_{user_id}"),
                                           IButton(text="📊 Посмотреть", callback_data=f"status_user_statistics_watch_menu{user_id}")],
                                          [IButton(text="◀️  Назад", callback_data=f"status_user_menu{user_id}")]])
    else:  # Сбор статистики выключен
        markup = IMarkup(inline_keyboard=[[IButton(text="🟢 Включить сбор статистики", callback_data=f"status_user_statistics_on_{user_id}")],
                                           [IButton(text="◀️  Назад", callback_data=f"status_user_menu{user_id}")]])
    return {"text": "🌐 <b>Статистика друга в сети</b>\nЗдесь вы можете вкл/выкл сбор статистики и посмотреть ее "
                    "в виде наглядных графиков и диаграмм", "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data.startswith("status_user_statistics_watch_menu"))
@security()
async def _status_user_statistics_watch_menu(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    user_id = int(callback_query.data.replace("status_user_statistics_watch_menu", ""))
    await callback_query.message.edit_text(**await status_user_statistics_watch_menu(account_id, user_id))


async def status_user_statistics_watch_menu(account_id: int, user_id: int) -> dict[str, Any]:
    user = await db.fetch_one(f"SELECT statistics, name FROM status_users WHERE account_id={account_id} AND user_id={user_id}")
    if user is None:
        return await status_users_menu(account_id)
    if user['statistics'] is False:
        return await status_user_statistics_menu(account_id, user_id)
    markup = IMarkup(inline_keyboard=[[IButton(text="День", callback_data=f"status_user_statistics_watch_day_{user_id}"),
                                       IButton(text="Неделя", callback_data=f"status_user_statistics_watch_week_{user_id}")],
                                      [IButton(text="◀️  Назад", callback_data=f"status_user_statistics_menu{user_id}")]])
    return {"text": f"🌐 <b>Статистика онлайн</b>\nЗа какой период показать статистику онлайн у <b>{user['name']}</b>",
            "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data.startswith("status_user_statistics_watch_"))
@security()
async def _status_user_statistics_watch_period(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    period, user_id = callback_query.data.replace("status_user_statistics_watch_", "").split("_", 2)
    user = await db.fetch_one(f"SELECT name, statistics FROM status_users WHERE account_id={account_id} AND user_id={user_id}")
    if user is None:
        return await status_users_menu(account_id)
    if user['statistics'] is False:
        return await status_user_statistics_menu(account_id, user_id)
    time_zone: int = await db.fetch_one(f"SELECT time_zone FROM settings WHERE account_id={account_id}", one_data=True)
    time = time_now() + timedelta(hours=time_zone)
    if period == "day":
        all_time = time.hour*3600 + time.minute*60 + time.second  # Количество секунд, прошедших с полуночи
        data = list(map(lambda x: list(x.values()),
                        await db.fetch_all("SELECT online_time, offline_time FROM statistics_status_users "
                                           f"WHERE account_id={account_id} AND user_id={user_id} "
                                           f"AND offline_time IS NOT NULL AND (now() - offline_time) < INTERVAL '{all_time} seconds'")))
    else:
        all_time = time.weekday()*24*3600 + time.hour*3600 + time.minute*60 + time.second  # Количество секунд, прошедших с полуночи прошлого понедельника
        data = map(lambda x: list(x.values()),
                   await db.fetch_all(f"SELECT online_time, offline_time FROM statistics_status_users "
                                      f"WHERE account_id={account_id} AND user_id={user_id} "
                                      f"AND offline_time IS NOT NULL AND (now() - offline_time) < INTERVAL '{all_time} days'"))
    online = sum(map(lambda x: abs((x[1] - x[0]).total_seconds()), data))
    offline = all_time - online
    labels = ["Онлайн", "Офлайн"]
    fig, ax = plt.subplots(figsize=(10, 7))
    wedges, texts, auto_texts = ax.pie([online, offline], labels=labels, colors=("#006e4a", "#60d4ae"), explode=(0.2, 0),
                                        autopct=lambda pct: f"{int(pct/100*all_time / 3600)}ч {ceil(pct/100*all_time % 3600 / 60)}мин")
    ax.legend(wedges, labels, title="Статистика онлайн", loc="center left", bbox_to_anchor=(0.8, -0.3, 0.5, 1), fontsize=20)
    plt.setp(auto_texts, size=20, weight="bold")
    plt.setp(texts, size=20)
    ax.set_title(f"Статистика онлайн для {user['name']}", fontsize=25, fontweight="bold")
    path = f"statistics_status_users/{account_id}.{user_id}.png"
    plt.savefig(www_path(path))
    await callback_query.message.edit_text(
        f"Статистика онлайн за {'день' if period == 'day' else 'неделю'}",
        link_preview_options=preview_options(f"{path}?time={time.timestamp()}", WWW_SITE, show_above_text=True),
        reply_markup=IMarkup(inline_keyboard=[[IButton(text="День", callback_data=f"status_user_statistics_watch_day_{user_id}"),
                                               IButton(text="Неделя", callback_data=f"status_user_statistics_watch_week_{user_id}")],
                                              [IButton(text="◀️  Назад", callback_data=f"status_user_statistics_menu{user_id}")]]))


@dp.callback_query(F.data == "new_status_user")
@security('state')
async def _new_status_user_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    if await db.fetch_one(f"SELECT COUNT(*) FROM status_users WHERE account_id={callback_query.from_user.id}", one_data=True) >= 3:
        # Количество друзей в сети уже достигло максимума
        if callback_query.from_user.id != OWNER:
            return await callback_query.answer("У вас максимальное количество!", True)
    await state.set_state(UserState.status_user)
    request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request_users)],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте пользователя для отслеживания", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.status_user)
@security('state')
async def _new_status_user(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    if message.content_type == "users_shared":
        user_id = message.users_shared.user_ids[0]
        account_id = message.chat.id
        if user_id == account_id:  # Себя нельзя
            await message.answer(**await status_users_menu(account_id))
        else:
            user = await telegram_clients[message.chat.id].get_entity(user_id)
            name = user.first_name + (f" {user.last_name}" if user.last_name else "")
            name = (name[:30] + "...") if len(name) > 30 else name
            telegram_clients[account_id].list_event_handlers()[4][1].chats.add(user_id)
            try:
                await db.execute(f"INSERT INTO status_users VALUES ({account_id}, {user_id}, $1, false, false, false, NULL, false)", name)
            except UniqueViolationError:  # Уже есть
                pass
            await message.answer(**await status_user_menu(message.chat.id, user_id))
    else:
        await message.answer(**await status_users_menu(message.chat.id))
    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data.startswith("status_user_del"))
@security()
async def _status_user_del(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    user_id = int(callback_query.data.replace("status_user_del", ""))
    account_id = callback_query.from_user.id
    telegram_clients[account_id].list_event_handlers()[4][1].chats.remove(user_id)
    await db.execute(f"DELETE FROM statistics_status_users WHERE account_id={account_id} AND user_id={user_id}")  # Удаление статистики
    await db.execute(f"DELETE FROM status_users WHERE account_id={account_id} AND user_id={user_id}")  # Удаление друга в сети
    await callback_query.message.edit_text(**await status_users_menu(callback_query.message.chat.id))


def status_users_initial():
    pass  # Чтобы PyCharm не ругался
