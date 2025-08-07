import re

from typing import Optional
from datetime import datetime, timedelta, UTC

from mg.core.functions import get_time_zone

from . types import RemindCommand


months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "ноября", "декабря"]
weekdays = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
REMINDER_EXACT_RE = re.compile(
    r'напомни *(?:мне|нам)? *(сегодня|послезавтра|завтра|(\d{1,2}) *(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)|'
    r'в? *(понедельник|вторник|среда|четверг|пяница|суббота|воскресенье))? *в? *(\d{1,2})[:.](\d{1,2}) *(.*)')
REMINDER_INTERVAL_RE = re.compile(r'напомни *(?:мне|нам)? *через *(\d{1,2})? *(часа|часов|час|ч)? *(\d{1,2})? *(минуту|минуты|минут|мин)? *(.*)')


async def now(account_id: int) -> datetime:
    time_zone: int = await get_time_zone(account_id)

    return datetime.now(UTC).replace(second=0, microsecond=0, tzinfo=None) + timedelta(hours=time_zone)


async def reminder(account_id: int, text: str) -> Optional[RemindCommand]:
    match_exact = re.fullmatch(REMINDER_EXACT_RE, text)
    match_interval = re.fullmatch(REMINDER_INTERVAL_RE, text)

    if match_exact:  # напомни в 12:00, напомни завтра в 12:00, напомни послезавтра в 12:00, напомни 9 декабря в 12:00
        data = match_exact.groups()
        time = await now(account_id)

        if data[0] is None:  # без даты
            result = time.replace(hour=int(data[4]), minute=int(data[5]))

            if result <= time:
                return RemindCommand(result + timedelta(days=1), text=data[6])

            return RemindCommand(result, text=data[6])

        else:  # С датой
            if data[0] in ("сегодня", "завтра", "послезавтра"):
                result = time.replace(hour=int(data[4]), minute=int(data[5]))

                if data[0] == "сегодня":
                    return RemindCommand(result, text=data[6])

                elif data[0] == "завтра":
                    return RemindCommand(result + timedelta(days=1), text=data[6])

                return RemindCommand(result + timedelta(days=2), text=data[6])  # Послезавтра

            elif data[3] in weekdays:
                result = time.replace(hour=int(data[4]), minute=int(data[5]))
                weekday = weekdays.index(data[3])  # сейчас

                result += timedelta(days=(7 + weekday - result.weekday()) % 7 or 7)  # Если день недели тот же, то напоминание через 7 дней
                return RemindCommand(result, text=data[6])

            else:  # Число и месяц
                result = time.replace(day=int(data[1]), month=months.index(data[2])+1, hour=int(data[4]), minute=int(data[5]))

                if result <= time:
                    return RemindCommand(result.replace(year=result.year+1), text=data[6])

                return RemindCommand(result, text=data[6])

    elif match_interval:  # напомни через 5 минут, напомни через 5 часов
        data = match_interval.groups()
        time = await now(account_id)

        if any(data):  # Время присутствует
            if data[1] and data[3]:  # Через несколько часов и минут
                return RemindCommand(time + timedelta(hours=int(data[0] or 1), minutes=int(data[2] or 1)), text=data[4])

            elif data[1]:  # Через несколько часов
                return RemindCommand(time + timedelta(hours=int(data[0] or 1)), text=data[4])

            elif data[3]:  # Через несколько минут
                return RemindCommand(time + timedelta(minutes=int(data[0] or 1)), text=data[4])
