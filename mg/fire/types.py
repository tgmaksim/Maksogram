from typing import Optional
from datetime import datetime


FIRES_BASE_DIR = "fires"


class FireLevel:
    def __init__(self, level: int, photo: str, start: int, end: Optional[int]):
        self.level = level
        self.photo = photo
        self.start = start
        self.end = end


class Fire:
    def __init__(self, account_id: int, user_id: int, name: str, account_status: bool, user_status: bool, days: int, score: int, reset: bool, inline_message_id: Optional[int], updating_time: datetime):
        self.account_id = account_id
        self.user_id = user_id
        self.name = name
        self.account_status = account_status
        self.user_status = user_status
        self.days = days
        self.score = score
        self.reset = reset
        self.inline_message_id = inline_message_id
        self.updating_time = updating_time

    @property
    def active(self) -> bool:
        return self.account_status and self.user_status

    @property
    def level(self) -> int:
        if self.reset or not self.active:
            return 0

        for fire_level in fire_levels.values():
            if fire_level.start <= self.days < (fire_level.end or float('inf')):
                return fire_level.level

        raise ValueError("Уровень огонька не найден")

    @property
    def photo(self) -> str:
        if self.reset:
            return fire_levels[0].photo
        return fire_levels[self.level].photo

    @classmethod
    def from_json(cls, json_data: dict) -> 'Fire':
        return cls(
            account_id=json_data['account_id'],
            user_id=json_data['user_id'],
            name=json_data['name'],
            account_status=json_data['account_status'],
            user_status=json_data['user_status'],
            days=json_data['days'],
            score=json_data['score'],
            reset=json_data['reset'],
            inline_message_id=json_data['inline_message_id'],
            updating_time=json_data['updating_time']
        )

    @classmethod
    def list_from_json(cls, json_data: list[dict]) -> list['Fire']:
        return [cls.from_json(data) for data in json_data]


fire_levels = {
    0: FireLevel(0, f"{FIRES_BASE_DIR}/fire0.png", 0, 1),
    1: FireLevel(1, f"{FIRES_BASE_DIR}/fire1.png", 1, 30),
    2: FireLevel(2, f"{FIRES_BASE_DIR}/fire2.png", 30, 100),
    3: FireLevel(3, f"{FIRES_BASE_DIR}/fire3.png", 100, None)
}
