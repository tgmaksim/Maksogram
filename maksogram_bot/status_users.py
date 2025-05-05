import math
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from typing import Any
from calendar import monthrange
from datetime import datetime, timedelta
from asyncpg.exceptions import UniqueViolationError
from matplotlib.colors import LinearSegmentedColormap
from telethon.utils import parse_username, parse_phone
from core import (
    db,
    html,
    OWNER,
    morning,
    security,
    time_now,
    www_path,
    WWW_SITE,
    human_time,
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


def difference_periods(periods: list[list[datetime, datetime]], period: str, time_zone: int, offset: int) -> tuple[list[int], list[int]]:
    if period == "day":
        now = (time_now(time_zone) - timedelta(seconds=offset)).replace(minute=0, second=0, microsecond=0)
    else:
        now = (time_now(time_zone) - timedelta(seconds=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "day":
        bin_size = 3600  # 1 час в секундах
        max_bins = 24
    elif period == "week":
        bin_size = 86400  # 1 день в секундах
        max_bins = 7
    else:  # month
        bin_size = 86400  # 1 день в секундах
        max_bins = 28
    bins = [0] * max_bins
    frequency = [0] * max_bins

    for start, end in periods:
        if start > end or end > now:
            continue

        # Получаем временные разницы относительно now
        start_delta = now - start
        end_delta = now - end

        # Индексы временных интервалов
        start_bin = math.floor(start_delta.total_seconds() / bin_size)
        end_bin = math.floor(end_delta.total_seconds() / bin_size)

        # Если период в одном интервале
        if start_bin == end_bin:
            seconds = (end - start).total_seconds()
            if start_bin < max_bins:
                bins[start_bin] += seconds
                frequency[start_bin] += 1
            continue

        # Обрабатываем первый частичный интервал
        if period == "day":
            bin_end = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            bin_end = start.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        if bin_end > start:
            seconds = (bin_end - start).total_seconds()
            if start_bin < max_bins:
                bins[start_bin] += seconds
                frequency[start_bin] += 1

        # Обрабатываем последний частичный интервал
        if period == "day":
            bin_start = end.replace(minute=0, second=0, microsecond=0)
        else:
            bin_start = end.replace(hour=0, minute=0, second=0, microsecond=0)
        if bin_start < end:
            seconds = (end - bin_start).total_seconds()
            if end_bin < max_bins:
                bins[end_bin] += seconds
                frequency[end_bin] += 1

        # Обрабатываем полные интервалы между началом и концом
        for bin_idx in range(end_bin + 1, start_bin):
            if bin_idx < max_bins:
                bins[bin_idx] += bin_size
                frequency[bin_idx] += 1

    return list(reversed(bins)), list(reversed(frequency))


async def get_data_by_period(account_id: int, user_id: int, period: str, time_zone: int, offset: int) -> tuple[int, int, list[int], list[int]]:
    if period == "day":
        all_time = 24 * 60 * 60  # Количество секунд в дне
    elif period == "week":
        all_time = 7 * 24 * 60 * 60  # Количество секунд в неделе
    else:  # Месяц (28 дней)
        all_time = 28 * 24 * 60 * 60  # Количество секунд в 28 днях
    data = list(map(lambda x: (x['online_time'] + timedelta(hours=time_zone), x['offline_time'] + timedelta(hours=time_zone)),
                    await db.fetch_all(f"SELECT online_time, offline_time FROM statistics_status_users WHERE account_id={account_id} "
                                       f"AND user_id={user_id} AND offline_time IS NOT NULL AND "
                                       f"INTERVAL '{offset} seconds' < now() - offline_time AND "
                                       f"now() - offline_time < INTERVAL '{all_time+offset} seconds' ORDER BY online_time")))
    summa = sum(map(lambda x: abs((x[1] - x[0]).total_seconds()), data))  # Общее время в секундах и время онлайн
    # Общее время в секундах, время онлайн, список онлайн по группам и список с количеством входов поо группам
    return all_time, summa, *difference_periods(data, period, time_zone, offset)


async def online_statistics(account_id: int, user_id: int, user: dict[str, str], period: str, offset: int) -> str:
    coefficient = {"day": 24, "week": 7, "month": 28}[period]
    offset = {"day": offset, "week": 7*offset, "month": 28*offset}[period]
    time_zone: int = await db.fetch_one(f"SELECT time_zone FROM settings WHERE account_id={account_id}", one_data=True)
    now = time_now(time_zone) - timedelta(days=offset)
    all_time, online, periods_online, online_frequency = await get_data_by_period(account_id, user_id, period, time_zone, offset*86400)
    time_readings = await db.fetch_all(f"SELECT time FROM statistics_time_reading WHERE account_id={account_id} AND user_id={user_id}", one_data=True)
    offline = all_time - online
    labels = ["Онлайн", "Офлайн"]
    if account_id == user_id or period == "day":
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8))
        ax3 = None
    else:
        fig = plt.figure(figsize=(18, 16))
        gs = gridspec.GridSpec(2, 2, height_ratios=[1, 1])
        ax1, ax2 = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])  # Верхние диаграммы
        ax3 = fig.add_subplot(gs[1, :])

    wedges, texts, auto_texts = ax1.pie([online, offline], labels=labels, colors=("#006e4a", "#60d4ae"), explode=(0.2, 0),
                                        autopct=lambda pct: human_time(pct / 100 * all_time))
    ax1.legend(wedges, labels, loc="center left", bbox_to_anchor=(0.8, -0.4, 0.5, 1), fontsize=20)
    plt.setp(auto_texts, size=20, weight="bold")
    plt.setp(texts, size=20)
    ax1.set_title(f"Статистика онлайн для {user['name']}", fontsize=25, fontweight="bold")

    colors, sleeping = "blue", [False, False]
    if period == "day":
        periods = list(range(now.hour, coefficient)) + list(range(now.hour))
        for i, p in enumerate(periods):
            if not periods_online[i] and sleeping[0] is False:  # Офлайн и сон не начался
                sleeping[0] = i  # Предполагаемое начало сна
            elif morning[0] <= int(p) <= morning[1] and periods_online[i]:  # Утро и онлайн
                sleeping[1] = i-1
                break
            elif periods_online[i]:  # Онлайн
                sleeping[0] = False
    elif period == "week":
        periods = [["пн", "вт", "ср", "чт", "пт", "сб", "вс"][i] for i in list(range(now.weekday(), coefficient)) + list(range(now.weekday()))]
        colors = ["red" if weekday in ("сб", "вс") else "blue" for weekday in periods]
    else:  # month
        last_month = now.replace(day=1) - timedelta(days=1)
        end_month = monthrange(last_month.year, last_month.month)[1]
        periods = list(range(end_month - (coefficient - now.day), end_month+1)) + list(range(max(1, now.day - coefficient), now.day))
    periods = list(map(str, periods))
    periods_online = list(map(lambda x: x / 60, periods_online))  # Преобразование секунд в минуты
    ax2.bar(periods, periods_online, color=colors, alpha=0.7)
    ax2.set_ylabel("Время онлайн (минуты)", fontsize=15)
    ax2.set_xlabel(f"Онлайн по {'часам' if period == 'day' else 'дням'}", fontsize=15)
    ax2.set_title(f"Онлайн по {'часам' if period == 'day' else 'дням'} для {user['name']}", fontsize=20, fontweight="bold")
    ax2.set_xticks(periods)
    ax2.grid(True, axis='y', linestyle='--', alpha=0.5)

    if False not in sleeping:
        ax2.axvspan(sleeping[0], sleeping[1], facecolor='gray', alpha=0.3, label="Время сна")
        ax2.text(sum(sleeping) / 2, max(periods_online) / 2, "Крепко спал(а)",
                 rotation=90, ha='center', va='center', fontsize=20, fontweight="bold")
    ax2.plot(online_frequency, color="green", linewidth=3, label="Количество входов")
    ax2.legend(fontsize=16)

    if ax3:
        time_readings = list(map(lambda x: x.total_seconds() / 60, time_readings))
        ax3.plot(time_readings, color="red", linewidth=3, zorder=0)
        ax3.set_title("Время ответа на ваши сообщения", fontsize=20, fontweight="bold")
        ax3.set_ylabel("Время ответа (минуты)", fontsize=16)
        ax3.grid(True, axis='y', linestyle='--', alpha=0.6)

        gradient = np.linspace(0, 1, 256).reshape(-1, 1)
        cmap = LinearSegmentedColormap.from_list("custom", ["blue", "green"])
        ax3.imshow(gradient, aspect='auto', cmap=cmap, alpha=0.5, zorder=0,
                   extent=[0, len(time_readings), ax3.get_ylim()[0], ax3.get_ylim()[1]])

    plt.tight_layout()
    path = f"statistics_status_users/{account_id}.{user_id}.png"
    plt.savefig(www_path(path))
    plt.close()
    return path


@dp.callback_query(F.data == "status_users")
@security()
async def _status_users(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    await callback_query.message.edit_text(**await status_users_menu(callback_query.message.chat.id))


async def status_users_menu(account_id: int, text: str = None) -> dict[str, Any]:
    buttons = []
    users = sorted(await db.fetch_all(f"SELECT user_id, name FROM status_users WHERE account_id={account_id}"),
                   key=lambda x: len(x['name']))  # Список друзей в сети, отсортированных по возрастанию длины имени
    i = 0
    while i < len(users):  # Если длина имен достаточно короткая, то помещаем 2 в ряд, иначе 1
        if i+1 < len(users) and all(map(lambda x: len(x['name']) <= 15, users[i:i+1])):
            buttons.append([IButton(text=f"🌐 {users[i]['name']}", callback_data=f"status_user_menu{users[i]['user_id']}"),
                            IButton(text=f"🌐 {users[i+1]['name']}", callback_data=f"status_user_menu{users[i+1]['user_id']}")])
            i += 1
        else:
            buttons.append([IButton(text=f"🌐 {users[i]['name']}", callback_data=f"status_user_menu{users[i]['user_id']}")])
        i += 1
    buttons.append([IButton(text="➕ Добавить нового пользователя", callback_data="new_status_user")])
    buttons.append([IButton(text="◀️  Назад", callback_data="menu")])
    return {"text": text or "🌐 <b>Друг в сети</b>\nУведомления о входе/выходе из сети, пробуждении, прочтения сообщения, а также "
                            "статистика онлайн\n<blockquote>⛔️ Не работает, если собеседник скрыл время последнего захода...</blockquote>",
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


async def status_user_menu(account_id: int, user_id: int, user: dict = None) -> dict[str, Any]:
    def status(parameter: bool):
        return "🟢" if parameter else "🔴"

    def command(parameter: bool):
        return "off" if parameter else "on"

    if not user:
        user = await db.fetch_one(f"SELECT name, online, offline, reading, awake, statistics FROM status_users "
                                  f"WHERE account_id={account_id} AND user_id={user_id}")
    if user is None:
        return await status_users_menu(account_id)
    warning = "<blockquote>❗️ Для улучшения точности выберите часовой пояс в /settings</blockquote>" if user['awake'] else ''
    if user_id == account_id:
        markup = IMarkup(inline_keyboard=[[IButton(text=f"Статистика ↙️", callback_data=f"status_user_statistics_menu{user_id}")],
                                          [IButton(text="🚫 Удалить пользователя", callback_data=f"status_user_del{user_id}")],
                                          [IButton(text="◀️  Назад", callback_data="status_users")]])
        return {"text": "🌐 <b>Друг в сети</b>\nЗдесь вы можете посмотреть статистику онлайн для своего аккаунта за "
                        "день, неделю и месяц\n<blockquote>Для других пользователей доступны и другие функции</blockquote>",
                "parse_mode": html, "reply_markup": markup}
    markup = IMarkup(inline_keyboard=[
        [IButton(text=f"{status(user['online'])} Онлайн", callback_data=f"status_user_online_{command(user['online'])}_{user_id}"),
         IButton(text=f"{status(user['offline'])} Оффлайн", callback_data=f"status_user_offline_{command(user['offline'])}_{user_id}")],
        [IButton(text=f"{status(user['awake'])} Проснется 💤", callback_data=f"status_user_awake_{command(user['awake'])}_{user_id}"),
         IButton(text=f"Статистика ↙️", callback_data=f"status_user_statistics_menu{user_id}")],
        [IButton(text=f"{status(user['reading'])} Чтение моего сообщения", callback_data=f"status_user_reading_{command(user['reading'])}_{user_id}")],
        [IButton(text="🚫 Удалить пользователя", callback_data=f"status_user_del{user_id}")],
        [IButton(text="◀️  Назад", callback_data="status_users")]])
    return {"text": f"🌐 <b>Друг в сети</b>\nКогда <b>{user['name']}</b> будет онлайн/оффлайн, проснется или прочитает сообщение, "
                    f"придет уведомление. В разделе статистика данные об онлайн за день, неделю и месяц\n{warning}",
            "parse_mode": html, "reply_markup": markup}


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


async def status_user_statistics_menu(account_id: int, user_id: int, watch: str = None, offset: int = 0, name: str = None) -> dict[str, Any]:
    user = await db.fetch_one(f"SELECT statistics FROM status_users WHERE account_id={account_id} AND user_id={user_id}")
    if user is None:
        return await status_users_menu(account_id)
    if watch:
        left_offset, right_offset = offset+1, "w" if offset-1 < 0 else offset-1
        right = "➡️" if offset-1 >= 0 else "🚫"
        markup = IMarkup(inline_keyboard=
                         [[IButton(text="📊 День", callback_data=f"status_user_statistics_watch_day_00_{user_id}"),
                           IButton(text="📊 Неделя", callback_data=f"status_user_statistics_watch_week_00_{user_id}"),
                           IButton(text="📊 Месяц", callback_data=f"status_user_statistics_watch_month_00_{user_id}")],
                          [IButton(text="⬅️", callback_data=f"status_user_statistics_watch_{watch}_{left_offset}_{user_id}"),
                           IButton(text=right, callback_data=f"status_user_statistics_watch_{watch}_{right_offset}_{user_id}")],
                          [IButton(text="◀️  Назад", callback_data=f"status_user_menu{user_id}")]])
        return {"text": f"🌐 <b>Статистика для {name}</b>", "parse_mode": html, "reply_markup": markup}
    if user['statistics']:  # Сбор статистики включен
        markup = IMarkup(inline_keyboard=[[IButton(text="🔴 Выключить сбор статистики", callback_data=f"status_user_statistics_off_{user_id}")],
                                          [IButton(text="📊 День", callback_data=f"status_user_statistics_watch_day_0_{user_id}"),
                                           IButton(text="📊 Неделя", callback_data=f"status_user_statistics_watch_week_0_{user_id}"),
                                           IButton(text="📊 Месяц", callback_data=f"status_user_statistics_watch_month_0_{user_id}")],
                                          [IButton(text="◀️  Назад", callback_data=f"status_user_menu{user_id}")]])
    else:  # Сбор статистики выключен
        markup = IMarkup(inline_keyboard=[[IButton(text="🟢 Включить сбор статистики", callback_data=f"status_user_statistics_on_{user_id}")],
                                           [IButton(text="◀️  Назад", callback_data=f"status_user_menu{user_id}")]])
    return {"text": "🌐 <b>Статистика друга в сети</b>\nЗдесь вы можете вкл/выкл сбор статистики и посмотреть ее "
                    "в виде наглядных графиков и диаграмм за день, неделю или месяц", "parse_mode": html, "reply_markup": markup}


@dp.callback_query(F.data.startswith("status_user_statistics_watch_"))
@security()
async def _status_user_statistics_watch_period(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    account_id = callback_query.from_user.id
    period, offset, user_id = callback_query.data.replace("status_user_statistics_watch_", "").split("_", 3)
    user = await db.fetch_one(f"SELECT name, statistics FROM status_users WHERE account_id={account_id} AND user_id={user_id}")
    if user is None:
        return await status_users_menu(account_id)
    if user['statistics'] is False:
        return await status_user_statistics_menu(account_id, user_id)
    if offset == "w":  # Нажатие на 🚫
        return await callback_query.answer("Вы дошли до текущего периода!")
    path = await online_statistics(account_id, int(user_id), user, period, int(offset))  # Создание диаграмм
    await callback_query.message.edit_text(
        **await status_user_statistics_menu(account_id, user_id, period, int(offset), "себя" if user_id == account_id else user['name']),
        link_preview_options=preview_options(f"{path}?time={time_now().timestamp()}", WWW_SITE, show_above_text=True))


@dp.callback_query(F.data == "new_status_user")
@security('state')
async def _new_status_user_start(callback_query: CallbackQuery, state: FSMContext):
    if await new_callback_query(callback_query): return
    if await db.fetch_one(f"SELECT COUNT(*) FROM status_users WHERE account_id={callback_query.from_user.id}", one_data=True) >= 3:
        if callback_query.from_user.id != OWNER:
            return await callback_query.answer("У вас максимальное количество!", True)
    await state.set_state(UserState.status_user)
    request_users = KeyboardButtonRequestUsers(request_id=1, user_is_bot=False)
    markup = KMarkup(keyboard=[[KButton(text="Выбрать", request_users=request_users), KButton(text="Себя")],
                               [KButton(text="Отмена")]], resize_keyboard=True)
    message_id = (await callback_query.message.answer("Отправьте пользователя для отслеживания кнопкой, ID, username или "
                                                      "номер телефона", reply_markup=markup)).message_id
    await state.update_data(message_id=message_id)
    await callback_query.message.delete()


@dp.message(UserState.status_user)
@security('state')
async def _new_status_user(message: Message, state: FSMContext):
    if await new_message(message): return
    message_id = (await state.get_data())['message_id']
    await state.clear()
    account_id = message.chat.id
    if not await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True):
        await message.answer(**await status_users_menu(account_id, "<b>Maksogram выключен!</b>"))
    elif message.text == "Отмена":
        await message.answer(**await status_users_menu(account_id))
    else:  # Maksogram запущен
        entity, user = None, None
        username, phone = message.text and parse_username(message.text), message.text and parse_phone(message.text)
        if message.text == "Себя":
            entity = account_id
        elif message.content_type == "users_shared":
            entity = message.users_shared.user_ids[0]
        elif username[1] is False and username[0] is not None:  # Является ли строка username (не ссылка с приглашением)
            entity = username[0]
        elif phone and message.text.startswith('+'):
            entity = f"+{phone}"
        elif message.text and message.text.isdigit():  # ID пользователя
            entity = int(message.text)
        if entity:
            try:
                user = await telegram_clients[account_id].get_entity(entity)
            except ValueError:  # Пользователь с такими данными не найден
                pass

        if user:
            user_id = user.id
            if user_id == account_id:
                name = "Мой аккаунт"
            else:
                name = f"{user.first_name} {user.last_name or ''}".strip()
                telegram_clients[account_id].list_event_handlers()[4][1].chats.add(user_id)
            try:
                await db.execute(f"INSERT INTO status_users VALUES ({account_id}, {user_id}, $1, "
                                 f"false, false, false, NULL, false, NULL)", name)
            except UniqueViolationError:  # Уже есть
                pass
            await message.answer(**await status_user_menu(account_id, user_id, dict(name=name, online=False, offline=False,
                                                                                    reading=False, awake=None, statistics=False)))
        else:
            await message.answer(**await status_users_menu(account_id, "<b>Пользователь не найден!</b>"))

    await bot.delete_messages(chat_id=message.chat.id, message_ids=[message.message_id, message_id])


@dp.callback_query(F.data.startswith("status_user_del"))
@security()
async def _status_user_del(callback_query: CallbackQuery):
    if await new_callback_query(callback_query): return
    user_id = int(callback_query.data.replace("status_user_del", ""))
    account_id = callback_query.from_user.id
    telegram_clients[account_id].list_event_handlers()[4][1].chats.remove(user_id)
    await db.execute(f"DELETE FROM statistics_status_users WHERE account_id={account_id} AND user_id={user_id};\n"  # Удаление статистики
                     f"DELETE FROM statistics_time_reading WHERE account_id={account_id} AND user_id={user_id};\n"  # Удаление статистики
                     f"DELETE FROM status_users WHERE account_id={account_id} AND user_id={user_id}")  # Удаление друга в сети
    await callback_query.message.edit_text(**await status_users_menu(callback_query.message.chat.id))


def status_users_initial():
    pass  # Чтобы PyCharm не ругался
