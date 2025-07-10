from typing import Optional


class SpeedAnswerMedia:
    def __init__(self, access_hash: int, ext: str):
        self.access_hash = access_hash
        self.ext = ext

    @classmethod
    def from_json(cls, json_data: dict) -> 'SpeedAnswerMedia':
        return cls(
            access_hash=json_data['access_hash'],
            ext=json_data['ext']
        )


class SpeedAnswer:
    def __init__(self, answer_id: int, trigger: str, text: str, entities: list[dict], media: Optional[SpeedAnswerMedia]):
        self.id = answer_id
        self.trigger = trigger
        self.text = text
        self.entities = entities
        self.media = media

    @classmethod
    def list_from_json(cls, json_data: list[dict]) -> list['SpeedAnswer']:
        return [cls.from_json(data) for data in json_data]

    @classmethod
    def from_json(cls, json_data: dict) -> 'SpeedAnswer':
        return cls(
            answer_id=json_data['answer_id'],
            trigger=str(json_data['trigger']),
            text=str(json_data['text']),
            entities=json_data['entities'],
            media=SpeedAnswerMedia.from_json(json_data['media']) if json_data['media'] else None
        )