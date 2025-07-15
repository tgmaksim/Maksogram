from mg.config import WWW_SITE

from typing import Optional
from mg.core.database import Database
from mg.core.types import MaksogramBot
from asyncpg.exceptions import UniqueViolationError
from mg.core.functions import get_subscription, zip_int_data

from mg.bot.types import bot, CallbackData
from mg.bot.functions import preview_options
from aiogram.types import InlineKeyboardMarkup as IMarkup
from aiogram.types import InlineKeyboardButton as IButton

from . types import Fire

cb = CallbackData()
MAX_COUNT_FIRES = 1
MAX_COUNT_FIRES_FOR_PREMIUM = 5

MESSAGE_FIRE_FORMAT = lambda account_id, user_id, name, days, score, active: \
    (f"{'🔥' if active else '🙁'} <b>{name}</b>\nСерия: {days} 🔥\nСчет: {score} 💥\nОтправляйте друг другу голосовые и кружки, чтобы увеличить счет\n"
     f"<b><a href='t.me/{MaksogramBot.username}?start=f{zip_int_data(account_id)}-{zip_int_data(user_id)}'>Меню</a></b> — управление огоньком\n")


async def get_fires(account_id: int) -> list[Fire]:
    """Возвращает список огоньков клиента, отсортированный по длине имени"""

    sql = (f"SELECT account_id, user_id, name, account_status, user_status, days, score, reset, inline_message_id, updating_time "
           f"FROM fires WHERE account_id={account_id}")
    data: list[dict] = await Database.fetch_all(sql)

    fires = Fire.list_from_json(data)

    return sorted(fires, key=lambda fire: len(fire.name))


async def check_count_fires(account_id: int) -> bool:
    """Считает количество созданных огоньков и возвращает возможность создать еще один"""

    subscription = await get_subscription(account_id)
    if subscription == 'admin':
        return True

    sql = f"SELECT COUNT(*) FROM fires WHERE account_id={account_id}"
    count: int = await Database.fetch_row_for_one(sql)

    if subscription == 'premium':
        return count < MAX_COUNT_FIRES_FOR_PREMIUM
    return count < MAX_COUNT_FIRES


async def add_fire(account_id: int, user_id: int, name: str, inline_message_id: str) -> bool:
    """Создает огонек с пользователем и возвращает результат выполнения"""

    sql = f"INSERT INTO fires (account_id, user_id, name, inline_message_id, updating_time) VALUES($1, $2, $3, $4, now())"
    try:
        await Database.execute(sql, account_id, user_id, name, inline_message_id)
    except UniqueViolationError:
        return False
    return True


async def get_fire(account_id: int = None, user_id: int = None, inline_message_id: int = None) -> Optional[Fire]:
    """Возвращает огонек с другом"""

    if inline_message_id:
        where = f"inline_message_id='{inline_message_id}'"
    else:
        where = f"account_id={account_id} AND user_id={user_id}"

    sql = f"SELECT account_id, user_id, name, account_status, user_status, days, score, reset, inline_message_id, updating_time FROM fires WHERE {where}"
    data: Optional[dict] = await Database.fetch_row(sql)
    if not data:
        return None

    return Fire.from_json(data)


async def edit_fire_message(fire: Fire, *, text: str = None):
    """Изменяет сообщение в чате с огоньком"""

    if text:
        await bot.edit_message_text(text, inline_message_id=fire.inline_message_id)
        return

    if fire.reset:
        text = f"😩 <b>{fire.name}</b>\nОгонек потух...\nВосстановить его может только создатель в меню бота"
    else:
        text = MESSAGE_FIRE_FORMAT(fire.account_id, fire.user_id, fire.name, fire.days, fire.score, fire.active)

    await bot.edit_message_text(text, inline_message_id=fire.inline_message_id,
                                reply_markup=IMarkup(inline_keyboard=[[IButton(text="🔥", callback_data=cb('inline_fire'))]]),
                                link_preview_options=preview_options(fire.photo, site=WWW_SITE, show_above_text=True))


async def edit_fire_name(account_id: int, user_id: int, name: str):
    """Изменяет имя огонька с другом"""

    sql = f"UPDATE fires SET name=$1 WHERE account_id={account_id} AND user_id={user_id}"
    await Database.execute(sql, name)


async def delete_fire(account_id: int, user_id: int):
    """Удаляет огонек с другом"""

    sql = f"DELETE FROM fires WHERE account_id={account_id} AND user_id={user_id}"
    await Database.execute(sql)


async def set_fire_inline_message_id(account_id: int, user_id: int, inline_message_id: str):
    """Изменяет inline_message_id для огонька с другом"""

    sql = f"UPDATE fires SET inline_message_id=$1 WHERE account_id={account_id} AND user_id={user_id}"
    await Database.execute(sql, inline_message_id)


async def update_fire_status(account_id: int, user_id: int, status: str):
    """Обновляет account_status или user_status огонька с другом"""

    if status == 'reset':
        sql = f"UPDATE fires SET account_status=false, user_status=false, updating_time=now() WHERE account_id={account_id} AND user_id={user_id}"
        await Database.execute(sql)
        return

    sql = f"UPDATE fires SET {status}_status=true WHERE account_id={account_id} AND user_id={user_id}"
    await Database.execute(sql)

    sql = f"UPDATE fires SET days=days + 1 WHERE account_id={account_id} AND user_id={user_id} AND account_status=true AND user_status=true"
    await Database.execute(sql)


async def reset_fire(account_id: int, user_id: int):
    """Сбрасывает огонек, если его не успели продлить"""

    sql = f"UPDATE fires SET account_status=false, user_status=false, reset=true WHERE account_id={account_id} AND user_id={user_id}"
    await Database.execute(sql)


async def clear_fire(account_id: int, user_id: int):
    """Обнуляет все достижения огонька"""

    sql = (f"UPDATE fires SET reset=false, days=0, score=0, account_status=false, user_status=false, updating_time=now() "
           f"WHERE account_id={account_id} AND user_id={user_id}")
    await Database.execute(sql)


async def recover_fire(account_id: int, user_id: int):
    """Восстанавливает огонек с другом"""

    sql = f"UPDATE fires SET reset=false, updating_time=now() WHERE account_id={account_id} AND user_id={user_id}"
    await Database.execute(sql)


async def update_score_fire(account_id: int, user_id: int):
    """Увеличивает счет на единицу"""

    sql = f"UPDATE fires SET score=score + 1 WHERE account_id={account_id} AND user_id={user_id}"
    await Database.execute(sql)
