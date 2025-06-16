import os

from typing import Union, Optional
from asyncpg.exceptions import UniqueViolationError
from core import (
    db,
    OWNER,
    full_name,
    resources_path,
    telegram_clients,
)

from telethon.tl.types.users import UserFull
from telethon.tl.types.payments import SavedStarGifts
from telethon.tl.types import StarGiftUnique, StarGift
from telethon.tl.types.photos import Photos, PhotosSlice
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.photos import GetUserPhotosRequest
from telethon.tl.functions.payments import GetSavedStarGiftsRequest

from . types import (
    User,
    Gift,
    FullUser,
    GiftGiver,
    FullAvatar,
)


MAX_COUNT_USERS = 4
MAX_COUNT_AVATARS = 64
MAX_COUNT_GIFTS = 64


async def get_saved_users(account_id: int) -> list[User]:
    """
    Получает из базы данных пользователей с параметрами `user_id` и `name`

    :param account_id: клиент
    :return: Список `User`, отсортированный по неубыванию длины `User.name`
    """

    sql = f"SELECT user_id, name FROM changed_profiles WHERE account_id={account_id}"
    data: list[dict] = await db.fetch_all(sql)

    users: list[User] = User.list_from_json(data)

    return sorted(users, key=lambda user: len(user.name))  # Сортировка по неубыванию длины имени


async def check_count_saved_users(account_id: int) -> bool:
    """
    Считает количество пользователей в базе данных и проверяет, можно ли добавить еще одного

    :param account_id: клиент
    :return: `True`, если количество пользователей позволяет добавить еще одного, иначе `False`
    """

    if account_id == OWNER:
        return True

    sql = f"SELECT COUNT(*) FROM changed_profiles WHERE account_id={account_id}"
    count: int = await db.fetch_one(sql, one_data=True)

    return count < MAX_COUNT_USERS


async def add_saved_user(account_id: int, user_id: int, name: str):
    """
    Добавляет нового пользователя в базу данных

    :param account_id: клиент
    :param user_id: пользователь
    :param name: имя пользователя
    """

    sql = "INSERT INTO changed_profiles (account_id, user_id, name, avatars, gifts, bio) VALUES ($1, $2, $3, NULL, NULL, NULL)"
    try:
        await db.execute(sql, account_id, user_id, name)
    except UniqueViolationError:  # Такой пользователь у клиента уже есть
        pass


async def delete_saved_user(account_id: int, user_id: int):
    """
    Удаляет пользователя из базы данных

    :param account_id: клиент
    :param user_id: пользователь
    """

    delete_avatars(account_id, user_id)

    sql = f"DELETE FROM changed_profiles WHERE account_id={account_id} AND user_id={user_id}"
    await db.execute(sql)


async def get_saved_full_user(account_id: int, user_id: int) -> Optional[FullUser]:
    """
    Получает полные данные пользователя из базы данных

    :param account_id: клиент
    :param user_id: пользователь
    :return: `None`, если пользователя у клиента в базе данных не найдено, иначе `FullUser` с полными данными
    """

    sql = f"SELECT user_id, name, avatars, gifts, bio FROM changed_profiles WHERE account_id={account_id} AND user_id={user_id}"
    data: Optional[dict] = await db.fetch_one(sql)
    if not data:
        return None  # Пользователь у клиента не найден

    return FullUser.from_json(data)


async def get_saved_full_users(account_id: int) -> list[FullUser]:
    """
    Получает список пользователей с полными данными

    :param account_id: клиент
    :return: список `FullUser` с полными данными
    """

    sql = f"SELECT user_id, name, avatars, gifts, bio FROM changed_profiles WHERE account_id={account_id}"
    data: list[dict] = await db.fetch_all(sql)

    return FullUser.list_from_json(data)


async def get_avatars(account_id: int, user_id: int) -> Optional[dict[int, FullAvatar]]:
    """
    Получает список аватарок пользователя

    :param account_id: клиент
    :param user_id: пользователь
    :return: `None`, если количество аватарок превысило лимит `MAX_COUNT_AVATARS`,
        иначе `dict` полученных аватарок (id: `FullAvatar`)
    """

    request = GetUserPhotosRequest(
        user_id=user_id,
        offset=0,
        max_id=0,
        limit=MAX_COUNT_AVATARS
    )
    response: Union[Photos, PhotosSlice] = await telegram_clients[account_id](request)

    if isinstance(response, PhotosSlice):
        return None  # Лимит превышен

    return {avatar.id: FullAvatar(avatar) for avatar in response.photos}


async def download_avatars(account_id: int, user_id: int, *, avatars: Optional[dict[int, FullAvatar]] = None) -> list[str]:
    """
    Скачивает аватарки пользователя в папку `resources/avatars` с форматом `account_id.user_id.avatar_id.ext`

    :param account_id: клиент
    :param user_id: пользователь
    :param avatars: необязательный список аватарок для скачивания
    :return: список path к сохраненным аватаркам
    """

    if not avatars:
        avatars = await get_avatars(account_id, user_id)

        if not avatars:
            return None  # Лимит превышен

    paths = []
    for avatar_id, avatar in avatars.items():
        paths.append(path := resources_path(f"avatars/{account_id}.{user_id}.{avatar_id}.{avatar.ext}"))
        await telegram_clients[account_id].download_media(avatar.photo, path)

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

    request = GetSavedStarGiftsRequest(
        peer=user_id,
        offset='',
        limit=MAX_COUNT_GIFTS
    )
    response: SavedStarGifts = await telegram_clients[account_id](request)

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
                slug=gift.slug
            )
        else:  # StarGift
            result[gift.id] = Gift(
                gift_id=gift.id,
                unique=False,
                giver=gift_giver,
                limited=gift.limited,
                stars=gift.stars,
                slug=None
            )

    return result


async def get_bio(account_id: int, user_id: int) -> str:
    """
    Получает описание "О себе" пользователя

    :param account_id: клиент
    :param user_id: пользователь
    :return: Описание
    """

    request = GetFullUserRequest(id=user_id)
    response: UserFull = await telegram_clients[account_id](request)

    return response.full_user.about
