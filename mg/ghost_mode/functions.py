import re

from mg.config import WWW_SITE

from telethon.tl.patched import Message
from mg.client.types import maksogram_clients
from telethon.tl.types.stories import PeerStories, Stories
from telethon.utils import get_input_peer, get_input_channel
from telethon.tl.functions.stories import GetPeerStoriesRequest, GetPinnedStoriesRequest
from telethon.tl.types import StoryItem, MessageMediaPhoto, MessageMediaDocument, PeerChannel, Channel

from typing import Union, Optional
from mg.core.database import Database
from . types import CopyPostResult, CopyPostItem
from mg.core.functions import time_now, www_path, resources_path, get_subscription

BASE_PATH_STORIES = "stories"
COUNT_PINNED_STORIES = 10

MAX_COUNT_USAGE_GHOST_STORIES_PER_DAY = 0
MAX_COUNT_USAGE_GHOST_STORIES_PER_DAY_FOR_PREMIUM = 5

MAX_COUNT_USAGE_GHOST_COPY_PER_DAY = 1
MAX_COUNT_USAGE_GHOST_COPY_PER_DAY_FOR_PREMIUM = 5

BASE_PATH_POSTS = "posts"
PRIVATE_CHANNEL_POST_RE = re.compile(r'(?:https?://)?(?:www\.)?(?:telegram\.(?:me|dog)|t\.me)/c/(?P<channel_id>\d+)/(?P<post_id>\d+)(?:\?single)?')
PUBLIC_CHANNEL_POST_RE = (
    re.compile(r'(?:https?://)?(?:www\.)?(?:telegram\.(?:me|dog)|t\.me)/(?P<channel_username>[a-zA-Z](?:(?!__)\w){1,30}[a-zA-Z\d])/(?P<post_id>\d+)(?:\?single)?'))


async def check_count_usage_ghost_mode(account_id: int, function: str) -> bool:
    """Считает количество использований функции режима призрака за сегодня и возвращает возможность вызвать еще раз"""

    subscription = await get_subscription(account_id)
    if subscription == 'admin':
        return True

    count: int = await maksogram_clients[account_id].get_limit(f"ghost_{function}")  # Проверка лимита и его сброс при необходимости

    if function == 'stories':
        if subscription == 'premium':
            return count < MAX_COUNT_USAGE_GHOST_STORIES_PER_DAY_FOR_PREMIUM
        return count < MAX_COUNT_USAGE_GHOST_STORIES_PER_DAY
    else:
        if subscription == 'premium':
            return count < MAX_COUNT_USAGE_GHOST_COPY_PER_DAY_FOR_PREMIUM
        return count < MAX_COUNT_USAGE_GHOST_COPY_PER_DAY


async def update_limit(account_id: int, function: str):
    """Обновляет количество использования функции"""

    sql = f"UPDATE limits SET ghost_{function}=ghost_{function} + 1 WHERE account_id={account_id}"
    await Database.execute(sql)


async def download_stories(account_id: int, user_id: int, stories: list[StoryItem]) -> list[str]:
    """Скачивает полученные истории и возвращает список HTML-ссылок"""

    links = []
    ts = int(time_now().timestamp())
    maksogram_client = maksogram_clients[account_id]

    for story in stories:
        if isinstance(story.media, MessageMediaPhoto):
            path = f"{BASE_PATH_STORIES}/{account_id}.{user_id}.{story.id}.{ts}.png"
            links.append(f"<a href='{WWW_SITE}/{path}'>Фото №{story.id} от {story.media.photo.date.strftime('%d-%m %H:%M')}</a>")

        elif isinstance(story.media, MessageMediaDocument) and story.media.video:
            path = f"{BASE_PATH_STORIES}/{account_id}.{user_id}.{story.id}.{ts}.mp4"
            links.append(f"<a href='{WWW_SITE}/{path}'>Видео №{story.id} ({int(story.media.document.attributes[0].duration)} сек) "
                         f"от {story.media.document.date.strftime('%d-%m %H:%M')}</a>\n")

        else:
            continue

        await maksogram_client.client.download_media(story.media, www_path(path))

    return links


async def download_peer_stories(account_id: int, user_id: int) -> list[str]:
    """Скачивает активные истории пользователя и возвращает HTML-ссылки на них"""

    maksogram_client = maksogram_clients[account_id]
    peer_stories: PeerStories = await maksogram_client.client(GetPeerStoriesRequest(
        get_input_peer(await maksogram_client.client.get_input_entity(user_id))
    ))

    return await download_stories(account_id, user_id, peer_stories.stories.stories)


async def download_pinned_stories(account_id: int, user_id: int) -> list[str]:
    """Скачивает COUNT_PINNED_STORIES историй из профиля пользователя и возвращает HTML-ссылки на них"""

    maksogram_client = maksogram_clients[account_id]
    pinned_stories: Stories = await maksogram_client.client(GetPinnedStoriesRequest(
        get_input_peer(await maksogram_client.client.get_input_entity(user_id)),
        offset_id=0,
        limit=COUNT_PINNED_STORIES
    ))

    return await download_stories(account_id, user_id, pinned_stories.stories)


def parse_post_link(text: str) -> Optional[tuple[Union[str, int], int]]:
    """Проверяет текст на правильную ссылку на пост в публичном или приватном канале и возвращает None или пару (entity, post_id)"""

    if match := re.fullmatch(PRIVATE_CHANNEL_POST_RE, text):
        return int(match.group('channel_id')), int(match.group('post_id'))

    if match := re.fullmatch(PUBLIC_CHANNEL_POST_RE, text):
        return match.group('channel_username'), int(match.group('post_id'))


async def download_post(account_id: int, entity: Union[str, int], post_id: int) -> CopyPostResult:
    """Скачивает пост из канала по идентификатору (если пост является частью альбома, скачивается альбом)"""

    ts = int(time_now().timestamp())
    maksogram_client = maksogram_clients[account_id]

    entity = PeerChannel(entity) if isinstance(entity, int) else entity
    try:
        channel: Channel = await maksogram_client.client.get_entity(entity)
    except ValueError as e:
        maksogram_client.logger.error(f"ошибка ValueError при поиске '{entity} ({e})'")
        return CopyPostResult(
            ok=False,
            posts=None,
            warning="Канал не найден"
        )
    else:
        input_channel = get_input_channel(channel)
        maksogram_client.logger.info(f"копирование поста из {input_channel}")

    post: Optional[Message] = await maksogram_client.client.get_messages(channel, ids=post_id)
    if not post:
        maksogram_client.logger.info(f"пост {post_id} на канале {input_channel} не найден")
        return CopyPostResult(
            ok=False,
            posts=None,
            warning="Пост на канале не найден"
        )

    posts: list[Message] = []
    if post.grouped_id:
        async for grouped_post in maksogram_client.client.iter_messages(channel, min_id=max(post_id-10, 0), max_id=post_id+10):
            if grouped_post.grouped_id != post.grouped_id:
                continue  # Перебор всех возможных постов альбома
            posts.append(grouped_post)

        maksogram_client.logger.info(f"найдено {len(posts)} постов в альбоме сообщения {post_id} на канале {input_channel}")
    else:
        posts.append(post)

    result = []
    for grouped_post in posts:
        if not grouped_post.media or grouped_post.web_preview:
            if not grouped_post.message:
                maksogram_client.logger.info(f"пост {grouped_post.id} на канале {input_channel} не имеет медиа и текста "
                                             f"(web_preview: {bool(grouped_post.web_preview)})")
                continue  # Нет текста и медиа
            path = None
        elif isinstance(grouped_post.media, MessageMediaPhoto):
            path = resources_path(f"{BASE_PATH_POSTS}/{account_id}.{channel.id}.{grouped_post.id}.{ts}.png")
        elif grouped_post.video or grouped_post.video_note:
            path = resources_path(f"{BASE_PATH_POSTS}/{account_id}.{channel.id}.{grouped_post.id}.{ts}.mp4")
        elif grouped_post.voice or grouped_post.audio:
            path = resources_path(f"{BASE_PATH_POSTS}/{account_id}.{channel.id}.{grouped_post.id}.{ts}.mp3")
        else:
            media = grouped_post.media.document if isinstance(grouped_post.media, MessageMediaDocument) else grouped_post.media.__class__.__name__
            maksogram_client.logger.info(f"пост {grouped_post.id} на канале {input_channel} содержит необрабатываемое медиа {media}")
            continue

        await maksogram_client.client.download_media(grouped_post, path)

        result.append(CopyPostItem(
            text=grouped_post.message,
            entities=grouped_post.entities or [],
            media=path,
            video_note=grouped_post.video_note,
            voice_note=grouped_post.voice
        ))

    return CopyPostResult(
        ok=True,
        posts=result,
        warning=None
    )
