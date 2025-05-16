import asyncio

from datetime import timedelta
from core import (
    db,
    time_now,
    account_off,
    MaksogramBot,
)

from aiogram.exceptions import TelegramForbiddenError
from maksogram_bot.core import (
    payment_menu,
)


async def main():
    while True:
        for account in await db.fetch_all("SELECT accounts.account_id, accounts.name, settings.is_started FROM accounts LEFT "
                                          "JOIN settings ON accounts.account_id = settings.account_id"):
            account_id = account['account_id']
            payment = await db.fetch_one(f"SELECT \"user\", is_paid, next_payment FROM payment WHERE account_id={account_id}")
            if not (payment['user'] == 'user' and payment['is_paid']): continue
            if time_now() <= payment['next_payment'] <= (time_now() + timedelta(days=1)):  # За день до конца
                first_notification = await db.fetch_one(f"SELECT first_notification FROM payment WHERE account_id={account_id}", one_data=True)
                if (time_now() - first_notification).total_seconds() >= 23*60*60 + 50*60:  # Прошлое уведомление было не менее 23 часов 50 минут назад
                    await db.execute(f"UPDATE payment SET first_notification=now() WHERE account_id={account_id}")
                    await MaksogramBot.send_system_message(f"Подписка заканчивается ({account['name']})")
                    await MaksogramBot.send_message(account_id, "Текущая подписка заканчивается! Произведите следующий "
                                                                "платеж до конца завтрашнего дня")
                    message = await payment_menu()
                    await MaksogramBot.bot.send_photo(account_id, **message)
            elif payment['next_payment'] <= (time_now() - timedelta(days=1)):  # После дня окончания
                await db.execute(f"UPDATE payment SET is_paid=false WHERE account_id={account_id}")
                await account_off(account_id)
                if account['is_started']:
                    try:
                        await MaksogramBot.send_message(account_id, "Ваша подписка истекла. Продлите ее, чтобы пользоваться Maksogram")
                    except TelegramForbiddenError:
                        pass
                await MaksogramBot.send_system_message(f"Платеж просрочен. Maksogram остановлен ({account['name']})")
            elif (time_now() - timedelta(days=1)) <= payment['next_payment'] <= time_now():  # В день окончания
                second_notification = await db.fetch_one(f"SELECT second_notification FROM payment WHERE account_id={account_id}", one_data=True)
                if (time_now() - second_notification).total_seconds() >= 23*60*60 + 50*60:  # Прошлое уведомление было не менее 23 часов 50 минут назад
                    await db.execute(f"UPDATE payment SET second_notification=now() WHERE account_id={account_id}")
                    if account['is_started']:
                        try:
                            await MaksogramBot.send_message(account_id, "Ваша подписка истечет завтра. Продлите ее, чтобы пользоваться Maksogram")
                        except TelegramForbiddenError:
                            pass
                    await MaksogramBot.send_system_message(f"Платеж просрочен ({account['name']})")
        await asyncio.sleep(60*60)
