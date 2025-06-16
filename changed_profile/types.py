from enum import StrEnum
from typing import Literal, Union, Optional

from telethon.tl.types import Photo


class AvatarExt(StrEnum):
    mp4 = "mp4"
    png = "png"


TypeExt = Union[Literal["png", "mp4"], AvatarExt]


class SavedAvatar:
    def __init__(self, avatar_id: int, ext: TypeExt):
        self.avatar_id = avatar_id
        self.ext = ext

    @property
    def video(self) -> bool:
        """Является ли аватарка видео"""

        return self.ext == AvatarExt.mp4

    @classmethod
    def from_json(cls, json_data: dict) -> 'SavedAvatar':
        """Десериализация JSON в `SavedAvatar`"""

        return cls(
            avatar_id=json_data['avatar_id'],
            ext=json_data['ext']
        )

    @classmethod
    def list_from_json(cls, json_data: Optional[dict[str, dict]]) -> Optional[dict[int, 'SavedAvatar']]:
        """
        Десериализация списка JSON в список `SavedAvatar`

        :return: `None`, если `json_data` = `None`, иначе `dict` (id: `SavedAvatar`)
        """

        if json_data is None:
            return None

        return {avatar_data['avatar_id']: cls.from_json(avatar_data) for avatar_data in json_data.values()}


class FullAvatar:
    def __init__(self, photo: Photo):
        self.avatar_id = photo.id
        self.photo = photo

    @property
    def video(self) -> bool:
        """Является ли аватарка видео"""

        return bool(self.photo.video_sizes)

    @property
    def ext(self) -> AvatarExt:
        """Расширение файла аватарки"""

        return AvatarExt.mp4 if self.photo.video_sizes else AvatarExt.png

    def to_dict(self) -> dict:
        """Сериализация `FullAvatar` в JSON"""

        return dict(
            avatar_id=self.avatar_id,
            ext=self.ext
        )


class GiftGiver:
    def __init__(self, user_id: int, username: str, name: str):
        self.user_id = user_id
        self.username = username
        self.name = name

    @property
    def link(self) -> str:
        """Ссылка на пользователя: @username или <a href='tg://user?id=user_id'>name</a>"""

        if self.username:
            return f"@{self.username}"
        else:
            return f"<a href='tg://user?id={self.user_id}'>{self.name}</a>"

    @classmethod
    def from_json(cls, json_data: Optional[dict]) -> Optional['GiftGiver']:
        """
        Десериализация JSON в `GiftGiver`

        :return: `None`, если `json_data` = `None`, иначе `GiftGiver`
        """

        if json_data is None:
            return None

        return cls(
            user_id=json_data['user_id'],
            username=json_data['username'],
            name=json_data['name']
        )

    def to_dict(self) -> dict:
        """Сериализация `GiftGiver` в JSON"""

        return dict(
            user_id=self.user_id,
            username=self.username,
            name=self.name
        )


class Gift:
    def __init__(self, gift_id: int, unique: bool, giver: Optional[GiftGiver], limited: bool, stars: Optional[int], slug: Optional[str]):
        self.gift_id = gift_id
        self.unique = unique
        self.giver = giver
        self.limited = limited
        self.stars = stars
        self.slug = slug

    @property
    def type(self) -> Literal["подарок", "лимитированный подарок", "уникальный подарок"]:
        """Тип подарка: подарок, лимитированный подарок, уникальный подарок"""

        if self.unique:
            return "уникальный подарок"
        elif self.limited:
            return "лимитированный подарок"
        else:
            return "подарок"

    @classmethod
    def from_json(cls, json_data: dict) -> 'Gift':
        """Десериализация JSON в `Gift`"""

        return cls(
            gift_id=json_data['gift_id'],
            unique=json_data['unique'],
            giver=GiftGiver.from_json(json_data['giver']),
            limited=json_data['limited'],
            stars=json_data['stars'],
            slug=json_data['slug']
        )

    @classmethod
    def list_from_json(cls, json_data: Optional[dict[str, dict]]) -> Optional[dict[int, 'Gift']]:
        """
        Десериализация списка JSON в список `Gift`

        :return: `None`, если `json_data` = `None`, иначе `dict` (id: `Gift`)
        """

        if json_data is None:
            return None

        return {gift_data['gift_id']: cls.from_json(gift_data) for gift_data in json_data.values()}

    def to_dict(self) -> dict:
        """Сериализация `Gift` в JSON"""

        return dict(
            gift_id=self.gift_id,
            unique=self.unique,
            giver=self.giver.to_dict() if self.giver else None,
            limited=self.limited,
            stars=self.stars,
            slug=self.slug
        )


class User:
    def __init__(self, user_id: int, name: str):
        self.user_id = user_id
        self.name = name

    @classmethod
    def from_json(cls, json_data: dict) -> 'User':
        """Десериализация JSON в `User`"""

        return cls(
            user_id=json_data['user_id'],
            name=json_data['name']
        )

    @classmethod
    def list_from_json(cls, json_data: list[dict]) -> list['User']:
        """
        Десериализация списка JSON в список `User`

        :return: `None`, если `json_data` = `None`, иначе список `User`
        """

        return [cls.from_json(user_data) for user_data in json_data]


class FullUser:
    def __init__(self, user_id: int, name: str, avatars: Optional[dict[int, SavedAvatar]], gifts: Optional[dict[int, Gift]], bio: Optional[str]):
        self.user_id = user_id
        self.name = name
        self.avatars = avatars
        self.gifts = gifts
        self.bio = bio

    @classmethod
    def from_json(cls, json_data: dict) -> 'FullUser':
        """Десериализация JSON в `FullUser`"""

        return cls(
            user_id=json_data['user_id'],
            name=json_data['name'],
            avatars=SavedAvatar.list_from_json(json_data['avatars']),
            gifts=Gift.list_from_json(json_data['gifts']),
            bio=json_data['bio']
        )

    @classmethod
    def list_from_json(cls, json_data: list[dict]) -> list['FullUser']:
        """Десериализация списка JSON в список `FullUser`"""

        return [cls.from_json(user_data) for user_data in json_data]
