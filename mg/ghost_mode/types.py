from typing import Optional
from dataclasses import dataclass

from telethon.tl.types import TypeMessageEntity


@dataclass
class CopyPostItem:
    text: str
    entities: list[TypeMessageEntity]
    media: Optional[str]  # path
    video_note: bool
    voice_note: bool


@dataclass
class CopyPostResult:
    ok: bool
    posts: Optional[list[CopyPostItem]]
    warning: Optional[str]
