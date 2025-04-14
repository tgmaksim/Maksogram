import re

from typing import Optional, Coroutine
from datetime import datetime, timedelta


months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "ноября", "декабря"]


async def main(text: str, time_zone: Coroutine[None, None, int]) -> Optional[datetime]:
    match_exact = re.fullmatch(r'напомни( +(завтра|послезавтра|(\d{1,2}) *(января|февраля|марта|апреля|мая|июня|июля|'
                               r'августа|сентября|октября|ноября|декабря)))? +в *(\d{1,2})[:.](\d{1,2})', text)
    match_interval = re.fullmatch(r'напомни +через *(\d{1,2})? *(ч|час|часа|часов)? *(\d{1,2})? *(мин|минуту|минуты|минут)?', text)
    if (utcnow := datetime.utcnow()).second >= 30:
        now = utcnow.replace(second=0, microsecond=0, tzinfo=None) + timedelta(hours=await time_zone, minutes=1)
    else:  # utcnow.second < 30
        now = utcnow.replace(second=0, microsecond=0, tzinfo=None) + timedelta(hours=await time_zone)
    if match_exact:  # напомни в 12:00, напомни завтра в 12:00, напомни послезавтра в 12:00, напомни 9 декабря в 12:00
        data = match_exact.groups()
        if data[0] is None:  # без даты
            result = now.replace(hour=int(data[3]), minute=int(data[4]))
            if result <= now:
                return result + timedelta(days=1)
            return result
        else:  # С датой
            if data[0] in ("сегодня", "завтра", "послезавтра"):
                result = now.replace(hour=int(data[3]), minute=int(data[4]))
                if data[0] == "сегодня":
                    return result
                elif data[0] == "завтра":
                    return result + timedelta(days=1)
                return result + timedelta(days=2)  # Послезавтра
            else:  # Число и месяц
                result = now.replace(day=int(data[1]), month=months.index(data[2])+1, hour=int(data[3]), minute=int(data[4]))
                if result <= now:
                    return result.replace(year=result.year+1)
                return result
    elif match_interval:  # напомни через 5 минут, напомни через 5 часов
        data = match_interval.groups()
        if any(data):  # Время присутствует
            if data[1] and data[3]:  # Через несколько часов и минут
                return now + timedelta(hours=int(data[0] or 1), minutes=int(data[2] or 1))
            elif data[1]:  # Через несколько часов
                return now + timedelta(hours=int(data[0] or 1))
            elif data[3]:  # Через несколько минут
                return now + timedelta(minutes=int(data[0] or 1))
