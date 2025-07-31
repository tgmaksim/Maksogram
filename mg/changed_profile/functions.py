import os

from typing import Union, Optional
from mg.core.database import Database
from mg.client.types import maksogram_clients
from asyncpg.exceptions import UniqueViolationError
from mg.core.functions import resources_path, full_name, get_subscription

from telethon.tl.types import PeerUser
from telethon.utils import get_input_user
from telethon.tl.types.users import UserFull
from telethon.tl.types.payments import SavedStarGifts
from telethon.tl.types import StarGiftUnique, StarGift
from telethon.tl.types.photos import Photos, PhotosSlice
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.photos import GetUserPhotosRequest
from telethon.tl.functions.payments import GetSavedStarGiftsRequest

from . types import (
    Gift,
    GiftGiver,
    FullAvatar,
    ChangedProfileSettings,
)


MAX_COUNT_USERS = 1
MAX_COUNT_USERS_FOR_PREMIUM = 4
MAX_COUNT_AVATARS = 64
MAX_COUNT_GIFTS = 64


async def get_changed_profiles_settings(account_id: int) -> list[ChangedProfileSettings]:
    """
    Получает список пользователей с полными данными

    :param account_id: клиент
    :return: список `ChangedProfileSettings` с полными данными
    """

    sql = f"SELECT user_id, name, avatars, gifts, bio FROM changed_profiles WHERE account_id={account_id}"
    data: list[dict] = await Database.fetch_all(sql)

    return ChangedProfileSettings.list_from_json(data)


async def check_count_changed_profiles(account_id: int) -> bool:
    """
    Считает количество пользователей в базе данных и проверяет, можно ли добавить еще одного

    :param account_id: клиент
    :return: `True`, если количество пользователей позволяет добавить еще одного, иначе `False`
    """

    subscription = await get_subscription(account_id)

    if subscription == 'admin':
        return True

    sql = f"SELECT COUNT(*) FROM changed_profiles WHERE account_id={account_id}"
    count: int = await Database.fetch_row_for_one(sql)

    if subscription == 'premium':
        return count < MAX_COUNT_USERS_FOR_PREMIUM
    return count < MAX_COUNT_USERS


async def add_changed_profile(account_id: int, user_id: int, name: str):
    """
    Добавляет нового пользователя в базу данных

    :param account_id: клиент
    :param user_id: пользователь
    :param name: имя пользователя
    """

    sql = "INSERT INTO changed_profiles (account_id, user_id, name, avatars, gifts, bio) VALUES ($1, $2, $3, NULL, NULL, NULL)"
    try:
        await Database.execute(sql, account_id, user_id, name)
    except UniqueViolationError:  # Такой пользователь у клиента уже есть
        pass


async def delete_changed_profile(account_id: int, user_id: int):
    """
    Удаляет пользователя из базы данных

    :param account_id: клиент
    :param user_id: пользователь
    """

    delete_avatars(account_id, user_id)

    sql = f"DELETE FROM changed_profiles WHERE account_id={account_id} AND user_id={user_id}"
    await Database.execute(sql)


async def get_changed_profile_settings(account_id: int, user_id: int) -> Optional[ChangedProfileSettings]:
    """
    Получает полные данные пользователя из базы данных

    :param account_id: клиент
    :param user_id: пользователь
    :return: `None`, если пользователя у клиента в базе данных не найдено, иначе `ChangedProfileSettings`
    """

    sql = f"SELECT user_id, name, avatars, gifts, bio FROM changed_profiles WHERE account_id={account_id} AND user_id={user_id}"
    data: Optional[dict] = await Database.fetch_row(sql)
    if not data:
        return None  # Пользователь у клиента не найден

    return ChangedProfileSettings.from_json(data)


async def get_avatars(account_id: int, user_id: int) -> Optional[dict[int, FullAvatar]]:
    """
    Получает список аватарок пользователя

    :param account_id: клиент
    :param user_id: пользователь
    :return: `None`, если количество аватарок превысило лимит `MAX_COUNT_AVATARS`,
        иначе `dict` полученных аватарок (id: `FullAvatar`)
    """

    client = maksogram_clients[account_id].client

    request = GetUserPhotosRequest(
        user_id=get_input_user(await client.get_input_entity(PeerUser(user_id=user_id))),
        offset=0,
        max_id=0,
        limit=MAX_COUNT_AVATARS
    )
    response: Union[Photos, PhotosSlice] = await client(request)

    if isinstance(response, PhotosSlice):
        return None  # Лимит превышен

    return {avatar.id: FullAvatar(avatar) for avatar in response.photos}


async def download_avatars(account_id: int, user_id: int, *, avatars: dict[int, FullAvatar]) -> list[str]:
    """
    Скачивает аватарки пользователя в папку `resources/avatars` с форматом `account_id.user_id.avatar_id.ext`

    :param account_id: клиент
    :param user_id: пользователь
    :param avatars: необязательный список аватарок для скачивания
    :return: список path к сохраненным аватаркам
    """

    paths = []
    for avatar_id, avatar in avatars.items():
        paths.append(path := resources_path(f"avatars/{account_id}.{user_id}.{avatar_id}.{avatar.ext}"))
        await maksogram_clients[account_id].client.download_media(avatar.photo, path)

    return paths


def delete_avatars(account_id: int, user_id: int):
    """
    Удаляет скачанные аватарки пользователя из папки `resources/avatars`

    :param account_id: клиент
    :param user_id: пользователь
    """

    dir_path = resources_path("avatars")

    for file_name in os.listdir(dir_path):
        if file_name.startswith(f"{account_id}.{user_id}"):
            os.remove(resources_path(f"avatars/{file_name}"))


async def get_gifts(account_id: int, user_id: int) -> Optional[dict[int, Gift]]:
    """
    Получает список подарков пользователя

    :param account_id: клиент
    :param user_id: пользователь
    :return: `None`, если количество подарков превысило лимит `MAX_COUNT_GIFTS`,
        иначе `dict` подарков (id: `Gift`)
    """

    client = maksogram_clients[account_id].client

    request = GetSavedStarGiftsRequest(
        peer=get_input_user(await client.get_input_entity(PeerUser(user_id=user_id))),
        offset='',
        limit=MAX_COUNT_GIFTS
    )
    response: SavedStarGifts = await client(request)

    if response.count > MAX_COUNT_GIFTS:
        return None  # Лимит превышен

    result: dict[int, Gift] = {}

    for saved_gift in response.gifts:
        gift: Union[StarGift, StarGiftUnique] = saved_gift.gift
        gift_giver: Optional[GiftGiver] = None

        if saved_gift.from_id:  # Отправитель подарка виден
            giver_user = [user for user in response.users if user.id == saved_gift.from_id.user_id][0]  # User, кто подарил
            gift_giver = GiftGiver(giver_user.id, giver_user.username, full_name(giver_user))

        if isinstance(gift, StarGiftUnique):  # Уникальный подарок
            result[gift.id] = Gift(
                gift_id=gift.id,
                unique=True,
                giver=gift_giver,
                limited=True,  # Этот параметр не имеет значения при unique=True
                stars=None,
                slug=gift.slug,
                sticker=gift.attributes[0].document
            )
        else:  # StarGift
            result[gift.id] = Gift(
                gift_id=gift.id,
                unique=False,
                giver=gift_giver,
                limited=gift.limited,
                stars=gift.stars,
                slug=None,
                sticker=gift.sticker
            )

    return result


async def download_gift(account_id: int, user_id: int, gift: Gift) -> str:
    """
    Скачивает стикер подарка пользователя в папку ``resources/gifts`` с форматом ``account_id.user_id.gift_id.tgs``

    :param account_id: клиент
    :param user_id: пользователь
    :param gift: подарок для скачивания
    :return: path к скачанному подарку
    """

    path = resources_path(f"gifts/{account_id}.{user_id}.{gift.gift_id}.tgs")
    await maksogram_clients[account_id].client.download_media(gift.sticker, path)

    return path


async def get_bio(account_id: int, user_id: int) -> Optional[str]:
    """
    Получает описание "О себе" пользователя

    :param account_id: клиент
    :param user_id: пользователь
    :return: Описание
    """

    client = maksogram_clients[account_id].client

    request = GetFullUserRequest(id=get_input_user(await client.get_input_entity(PeerUser(user_id=user_id))))
    response: UserFull = await client(request)

    return response.full_user.about or ''


async def update_changed_profile(account_id: int, user_id: int, field: str, value: Optional[str] = None):
    """
    Обновляет параметры пользователя в Профиль друга

    :param account_id: клиент
    :param user_id: пользователь
    :param field: поле для изменения
    :param value: новое значение (необязательно, по умолчанию `NULL`)
    """

    sql = f"UPDATE changed_profiles SET {field}=$1 WHERE account_id={account_id} AND user_id={user_id}"
    await Database.execute(sql, value)
