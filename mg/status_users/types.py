from typing import Optional
from datetime import datetime


class StatusUserSettings:
    def __init__(self, user_id: int, name: str, online: bool, offline, reading: bool, awake: Optional[datetime], statistics: bool, last_message: Optional[datetime]):
        self.id = user_id
        self.name = name
        self.online = online
        self.offline = offline
        self.reading = reading
        self.awake = awake
        self.statistics = statistics
        self.last_message = last_message

    @classmethod
    def from_json(cls, json_data: dict) -> 'StatusUserSettings':
        return cls(
            user_id=json_data['user_id'],
            name=str(json_data['name']),
            online=json_data['online'],
            offline=json_data['offline'],
            reading=json_data['reading'],
            awake=json_data['awake'],
            statistics=json_data['statistics'],
            last_message=json_data['last_message']
        )

    @classmethod
    def list_from_json(cls, json_data: list[dict]) -> list['StatusUserSettings']:
        return [cls.from_json(data) for data in json_data]
