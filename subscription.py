import asyncio

from mg.config import OWNER

from datetime import timedelta
from mg.client.functions import get_accounts
from mg.core.functions import time_now, get_payment_data, reset_subscription

from mg.bot.maksogram_bot import bot
from mg.bot.functions import set_time_subscription_notification


async def subscriptions():
    await asyncio.sleep(60)  # Ожидание полного запуска клиентов

    while True:
        for account_id, is_started in await get_accounts():
            payment_info = await get_payment_data(account_id)
            if payment_info.subscription != 'premium':
                continue

            if time_now() <= payment_info.ending <= (time_now() + timedelta(days=1)):  # За день до конца
                if time_now() - payment_info.first_notification >= timedelta(days=1):  # Уведомление об окончании подписки еще не пришло

                    await set_time_subscription_notification(account_id, "first")

                    if is_started:
                        await bot.send_message(
                            account_id, "🌟 <b>Maksogram Premium</b>\nMaksogram Premium заканчивается. Чтобы иметь полный доступ к функциям, продлите ее")
                    await bot.send_message(OWNER, f"Подписка заканчивается ({account_id})")

            elif payment_info.ending <= (time_now() - timedelta(days=1)):  # После дня окончания
                await reset_subscription(account_id)

                if is_started:
                    await bot.send_message(
                        account_id, "🌟 <b>Maksogram Premium</b>\nMaksogram Premium истекла, без подписки некоторые функции имеют ограничения!")
                await bot.send_message(OWNER, f"Подписка Maksogram Premium истекла ({account_id})")

            elif (time_now() - timedelta(days=1)) <= payment_info.ending <= time_now():  # В день окончания
                if time_now() - payment_info.second_notification >= timedelta(days=1):  # Уведомление об окончании подписки еще не пришло

                    await set_time_subscription_notification(account_id, "second")

                    if is_started:
                        await bot.send_message(
                            account_id, "🌟 <b>Maksogram Premium</b>\nMaksogram Premium истекает завтра, продлите ее, чтобы иметь полный доступ к функциям")
                    await bot.send_message(OWNER, f"Платеж просрочен ({account_id})")

        await asyncio.sleep(60*60)  # Проверка каждый час
