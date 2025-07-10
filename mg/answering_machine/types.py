from typing import Optional, Any
from datetime import time, datetime

LENGTH_SHORT_TEXT = 30
MAX_LENGTH_TEXT = 33
week = ('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс')


class AutoAnswerMedia:
    def __init__(self, ext: str, access_hash: int):
        self.ext = ext
        self.access_hash = access_hash

    @classmethod
    def from_json(cls, json_data: dict[str, Any]) -> 'AutoAnswerMedia':
        return cls(
            ext=json_data['ext'],
            access_hash=json_data['access_hash']
        )


class AutoAnswer:
    def __init__(self, answer_id: int, status: bool, text: str, entities: list[dict], media: Optional[AutoAnswerMedia], start_time: Optional[time],
                 end_time: Optional[time], weekdays: list[int], triggers: Optional[dict[str, str]], offline: bool, chats: Optional[dict[str, str]],
                 contacts: Optional[bool], blacklist_chats: Optional[bool], triggering: dict[int, datetime], time_zone: int):
        self.id = answer_id
        self.status = status
        self.text = text
        self.entities = entities
        self.media = media
        self.start_time = start_time
        self.end_time = end_time
        self.weekdays = weekdays
        self.triggers = {int(key): value for key, value in triggers.items()}
        self.offline = offline
        self.chats = {int(key): value for key, value in chats.items()}
        self.contacts = contacts
        self.blacklist_chats = blacklist_chats
        self.triggering = triggering
        self.time_zone = time_zone

        self.short_text = f"{text[:LENGTH_SHORT_TEXT]}..." if len(text) > MAX_LENGTH_TEXT else text

        self.time = (start_time, end_time)
        self.human_timetable = self._format_human_timetable() if self.start_time else None
        self.human_weekdays = self._format_human_weekdays() if self.weekdays else None

        self.human_triggers = self._format_human_triggers()
        self.short_human_triggers = f"{self.human_triggers[:LENGTH_SHORT_TEXT]}..." if len(self.human_triggers) > MAX_LENGTH_TEXT \
            else self.human_triggers
        self.short_triggers = {key: (f"{value[:LENGTH_SHORT_TEXT]}..." if len(value) > MAX_LENGTH_TEXT else value)
                               for key, value in sorted(self.triggers.items())}

        self.human_chats = self._format_human_chats()
        self.short_human_chats = f"{self.human_chats[:LENGTH_SHORT_TEXT]}..." if len(self.human_chats) > MAX_LENGTH_TEXT else self.human_chats
        self.short_chats = {key: (f"{value[:LENGTH_SHORT_TEXT]}..." if len(value) > MAX_LENGTH_TEXT else value)
                            for key, value in sorted(self.chats.items())}

    @property
    def chats_about(self) -> str:
        if self.blacklist_chats:
            text = "Отвечаю всем кроме "
        else:
            text = "Отвечаю только "

        if self.contacts is True:
            text += "контактов и " if self.blacklist_chats else "контактам и "
        elif self.contacts is False:
            text += "не контактов и " if self.blacklist_chats else "не контактам и "

        text += ("выбранных чатов" if self.blacklist_chats else "выбранным чатам") + (': ' if self.chats else '') + self.human_chats

        return text

    def _format_human_weekdays(self) -> str:
        if self.weekdays == [0, 1, 2, 3, 4, 5, 6]:
            return "всю неделю"
        if self.weekdays == [0, 1, 2, 3, 4]:
            return "по будням"
        if self.weekdays == [5, 6]:
            return "по выходным"

        if len(self.weekdays) >= 3 and self.weekdays == [*range(self.weekdays[0], self.weekdays[-1] + 1)]:  # Целостный промежуток недели
            return f"{week[self.weekdays[0]]} — {week[self.weekdays[-1]]}"

        return " ".join([week[weekday] for weekday in self.weekdays])  # Список через пробел

    def _format_human_triggers(self) -> str:
        return '; '.join(self.triggers.values())

    def _format_human_timetable(self) -> str:
        start_time = self.start_time.replace(hour=(self.start_time.hour + self.time_zone) % 24)
        end_time = self.end_time.replace(hour=(self.end_time.hour + self.time_zone) % 24) if self.end_time else None

        if not end_time:  # До пробуждения
            return f"{start_time.hour:02d}:{start_time.minute:02d} — до утра"

        return f"{start_time.hour:02d}:{start_time.minute:02d} — {end_time.hour:02d}:{end_time.minute:02d}"

    def _format_human_chats(self) -> str:
        return ', '.join(self.chats.values())

    @classmethod
    def from_json(cls, json_data: dict[str, Any], triggering: dict[int, datetime], time_zone: int) -> 'AutoAnswer':
        return cls(
            answer_id=json_data['answer_id'],
            status=json_data['status'],
            text=json_data['text'],
            entities=json_data['entities'],
            media=AutoAnswerMedia.from_json(json_data['media']) if json_data['media'] else None,
            start_time=json_data['start_time'],
            end_time=json_data['end_time'],
            weekdays=json_data['weekdays'],
            triggers=json_data['triggers'],
            offline=json_data['offline'],
            chats=json_data['chats'],
            contacts=json_data['contacts'],
            blacklist_chats=json_data['blacklist_chats'],
            time_zone=time_zone,
            triggering=triggering,
        )

    @classmethod
    def list_from_json(cls, json_data: list[dict[str, Any]], triggering: dict[int, dict[int, datetime]], time_zone: int) -> list['AutoAnswer']:
        return [cls.from_json(data, triggering.get(data['answer_id'], {}), time_zone) for data in json_data]
