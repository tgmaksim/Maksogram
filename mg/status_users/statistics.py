import math
import numpy as np

from matplotlib import gridspec
from matplotlib import pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from typing import Optional
from calendar import monthrange
from mg.core.types import morning
from mg.core.database import Database
from datetime import datetime, timedelta
from mg.core.functions import time_now, get_time_zone, human_timedelta, www_path

from . types import StatusUserSettings


async def online_statistics(account_id: int, user: StatusUserSettings, period: str, offset: int) -> str:
    """Создает диаграммы и графики со статистикой онлайн и времени ответа, возвращает ссылку (www_path) на файл"""

    offset = {'day': offset, 'week': 7 * offset, 'month': 28 * offset}[period]  # Смещение периода в днях
    time_zone = await get_time_zone(account_id)

    now = time_now(time_zone) - timedelta(days=offset)

    # Две диаграммы сверху (круговая и столбиковая), график снизу (если не для себя)
    if user.id == account_id:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8))
        ax3 = None
    else:
        fig = plt.figure(figsize=(18, 16))
        gs = gridspec.GridSpec(2, 2, height_ratios=[1, 1])
        ax1, ax2 = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])  # Верхние диаграммы
        ax3 = fig.add_subplot(gs[1, :])  # Нижний график

    period_size, online_time, online_times, frequency = await get_data_by_period(account_id, user.id, period, time_zone, offset * 24 * 60 * 60)
    offline_time = period_size - online_time

    # Создаем круговую диаграмму по общему времени онлайн и офлайн
    labels = ["Онлайн", "Офлайн"]
    wedges, texts, auto_texts = ax1.pie([online_time, offline_time], labels=labels, colors=("#006e4a", "#60d4ae"),
                                        explode=(0.2, 0), autopct=lambda pct: human_timedelta(pct * period_size / 100))
    ax1.legend(wedges, labels, loc="center left", bbox_to_anchor=(0.8, -0.4, 0.5, 1), fontsize=20)
    plt.setp(auto_texts, size=20, weight="bold")
    plt.setp(texts, size=20)
    ax1.set_title(f"Статистика онлайн для {user.name}", fontsize=25, fontweight="bold")

    sleeping: list[Optional[int]] = [None, None]  # Начало и окончание сна
    weekdays = ('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс')

    if period == 'day':
        periods: list[int] = [*range(now.hour, 24), *range(now.hour)]
        for i, hour in enumerate(periods):
            if online_times[i] == 0 and sleeping[0] is None:  # В данный час время онлайн равно нулю и сон еще не начался
                sleeping[0] = i  # Предполагаемое начало сна
            elif online_times[i] > 0 and morning[0] <= hour < morning[1]:  # В данный час был(а) онлайн и уже утро
                sleeping[1] = i - 1
                break
            elif online_times[i]:  # Если в данный час онлайн, то сон точно не начался или прервался
                sleeping[0] = None
        colors = 'blue'

    elif period == 'week':
        periods: list[str] = [weekdays[i] for i in (*range(now.weekday(), 7), *range(now.weekday()))]
        colors = ['red' if weekday in ('сб', 'вс') else 'blue' for weekday in periods]

    else:  # month
        last_month = now.replace(day=1) - timedelta(days=1)
        last_month_size = monthrange(last_month.year, last_month.month)[1]  # Количество дней прошлого месяца
        periods: list[int] = [*range(last_month_size - (28 - now.day), last_month_size + 1), *range(max(1, now.day - 28), now.day)]

        offset_weekday = (now - timedelta(days=28)).weekday()
        colors = ['red' if weekdays[(i + offset_weekday) % 7] in ('сб', 'вс') else 'blue' for i in range(28)]

    periods: list[str] = list(map(str, periods))  # Конвертируем все в строки

    online_times = list(map(lambda t: t / 60, online_times))  # Время онлайн в минутах

    # Создаем столбиковую диаграмму по времени онлайн за подпериод
    ax2.bar(periods, online_times, color=colors, alpha=0.7)
    ax2.set_ylabel(f"Время онлайн (минуты)", fontsize=15)
    ax2.set_xlabel(f"Онлайн по {'часам' if period == 'day' else 'дням'}", fontsize=15)
    ax2.set_title(f"Онлайн по {'часам' if period == 'day' else 'дням'} для {user.name}", fontsize=20, fontweight="bold")
    ax2.set_xticks(periods)
    ax2.grid(True, axis='y', linestyle='--', alpha=0.5)

    # Серая зона сна и надпись
    if sleeping[0] is not None and sleeping[1] is not None:  # Сон обнаружен
        ax2.axvspan(sleeping[0], sleeping[1], facecolor='gray', alpha=0.3, label="Время сна")
        ax2.text(sum(sleeping) / 2, max(online_times) / 2, "Крепко спал(а)", rotation=90, ha='center', va='center', fontsize=20, fontweight="bold")

    # Зеленая линия с количеством входов
    ax2.plot(frequency, color="green", linewidth=3, label="Количество входов")
    ax2.legend(fontsize=16)

    if ax3:  # Нужен график с временем ответа
        time_readings = await get_time_reading(account_id, user.id)
        time_readings = list(map(lambda x: x.total_seconds() / 60, time_readings))  # Время ответа в минутах

        # Создаем график с временем ответа
        ax3.plot(time_readings, color="red", linewidth=3, zorder=0)
        ax3.set_title("Время ответа на ваши сообщения", fontsize=20, fontweight="bold")
        ax3.set_ylabel("Время ответа (минуты)", fontsize=16)
        ax3.grid(True, axis='y', linestyle='--', alpha=0.6)

        # Рисуем градиент на графике, где зеленый - быстро, голубой - медленно
        gradient = np.linspace(0, 1, 256).reshape(-1, 1)
        cmap = LinearSegmentedColormap.from_list("custom", ["blue", "green"])
        ax3.imshow(gradient, aspect='auto', cmap=cmap, alpha=0.5, zorder=0, extent=(0, len(time_readings), ax3.get_ylim()[0], ax3.get_ylim()[1]))

    plt.tight_layout()
    path = f"statistics_status_users/{account_id}.{user.id}.png"
    plt.savefig(www_path(path))
    plt.close()

    return path


async def get_data_by_period(account_id: int, user_id: int, period: str, time_zone: int, offset: int) -> tuple[int, int, list[int], list[int]]:
    """
    Получает статистические данные о времени онлайн за период

    :param account_id: клиент
    :param user_id: пользователь
    :param period: период (day, week, month)
    :param time_zone: часовой пояс
    :param offset: смещение периода в секундах
    :return: общее время (в секундах) в периоде, проведенное время в сети (в секундах) пользователем,
    список со временем онлайн (в секундах) за каждый подпериод, список с количеством входов за каждый подпериод
    """

    if period == 'day':
        period_size = 24 * 60 * 60
    elif period == 'week':
        period_size = 7 * 24 * 60 * 60
    else:
        period_size = 28 * 24 * 60 * 60

    data = await get_statistics(account_id, user_id, period_size, time_zone, offset)  # Список пар datetime (вход, выход)
    online_time = sum(map(lambda pair: abs(pair[0] - pair[1]).total_seconds(), data))  # Общее время онлайн за период

    online_times, frequency = difference_periods(data, period, time_zone, offset)

    return period_size, online_time, online_times, frequency


def difference_periods(periods: list[tuple[datetime, datetime]], period: str, time_zone: int, offset: int) -> tuple[list[int], list[int]]:
    """
    Принимает статистику онлайн (пары времени вход, выход) и возвращает список со временем онлайн (в секундах) за каждый подпериод и
    список с количеством входов за каждый подпериод, учитывая часовой пояс

    :param periods: список пар datetime (вход, выход)
    :param period: период (day, week или month)
    :param time_zone: часовой пояс
    :param offset: смещение периода в секундах
    :return: список времени онлайн (в секундах) за каждый подпериод и список с количеством входов за подпериод
    """

    # Считаем время конца отсчета по часовому поясу клиента
    if period == 'day':
        now = (time_now(time_zone) - timedelta(seconds=offset)).replace(minute=0, second=0, microsecond=0)
    else:
        now = (time_now(time_zone) - timedelta(seconds=offset)).replace(hour=0, minute=0, second=0, microsecond=0)

    # bin_size - количество секунд в подпериоде, max_bins - число подпериодов в периоде
    if period == 'day':
        bin_size = 60 * 60
        max_bins = 24
    elif period == 'week':
        bin_size = 24 * 60 * 60
        max_bins = 7
    else:  # month
        bin_size = 24 * 60 * 60
        max_bins = 28

    bins = [0] * max_bins  # Список времени онлайн (в секундах) за каждый подпериод
    frequency = [0] * max_bins  # Список с количеством входов за подпериод

    for start, end in periods:
        if start > end or end > now:
            continue

        # Получаем временные разницы относительно now
        start_delta = now - start
        end_delta = now - end

        # Индексы в списке bins для начала и конца
        start_bin = math.floor(start_delta.total_seconds() / bin_size)
        end_bin = math.floor(end_delta.total_seconds() / bin_size)

        # Если начало и конец в одном подпериоде
        if start_bin == end_bin:
            seconds = (end - start).total_seconds()
            if start_bin < max_bins:
                bins[start_bin] += seconds  # Добавляем ко времени онлайн в данном подпериоде
                frequency[start_bin] += 1  # Добавляем к количеству входов в данном подпериоде
            continue

        # Обрабатываем первый частичный интервал
        if period == 'day':
            bin_end = start.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            bin_end = start.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        if bin_end > start:
            seconds = (bin_end - start).total_seconds()
            if start_bin < max_bins:
                bins[start_bin] += seconds  # Добавляем ко времени онлайн в данном подпериоде
                frequency[start_bin] += 1  # Добавляем к количеству входов в данном подпериоде

        # Обрабатываем последний частичный интервал
        if period == 'day':
            bin_start = end.replace(minute=0, second=0, microsecond=0)
        else:
            bin_start = end.replace(hour=0, minute=0, second=0, microsecond=0)
        if bin_start < end:
            seconds = (end - bin_start).total_seconds()
            if end_bin < max_bins:
                bins[end_bin] += seconds  # Добавляем ко времени онлайн в данном подпериоде
                frequency[end_bin] += 1  # Добавляем к количеству входов в данном подпериоде

        # Обрабатываем полные интервалы между началом и концом
        for bin_idx in range(end_bin + 1, start_bin):
            if bin_idx < max_bins:
                bins[bin_idx] += bin_size  # Добавляем ко времени онлайн в данном подпериоде
                frequency[bin_idx] += 1  # Добавляем к количеству входов в данном подпериоде

    return list(reversed(bins)), list(reversed(frequency))


async def get_statistics(account_id: int, user_id: int, period_size: int, time_zone: int, offset: int) -> list[tuple[datetime, datetime]]:
    """
    Возвращает статистику онлайн в виде списка пар datetime (вход, выход) из базы данных

    :param account_id: клиент
    :param user_id: пользователь
    :param period_size: количество секунд в периоде
    :param time_zone: часовой пояс
    :param offset: смещение периода в секундах
    :return: список пар datetime (вход, выход)
    """

    time_zone *= 60 * 60

    # Пары datetime (вход, выход), если пара закончена, время выхода в диапазоне нужного периода
    sql = (f"SELECT online_time + INTERVAL '{time_zone} seconds' AS online_time, offline_time + INTERVAL '{time_zone} seconds' AS offline_time "
           f"FROM statistics_status_users WHERE account_id={account_id} AND user_id={user_id} AND offline_time IS NOT NULL "
           f"AND (now() - offline_time) >= INTERVAL '{offset} seconds' AND (now() - offline_time) < INTERVAL '{period_size + offset} seconds' "
           "ORDER BY online_time")
    data: list[dict[str, datetime]] = await Database.fetch_all(sql)

    return [(pair['online_time'], pair['offline_time']) for pair in data]


async def get_time_reading(account_id: int, user_id: int) -> list[timedelta]:
    """Возвращает список timedelta с данными о времени ответа собеседника"""

    sql = f"SELECT time FROM statistics_time_reading WHERE account_id={account_id} AND user_id={user_id}"
    data: list[timedelta] = await Database.fetch_all_for_one(sql)

    return data
