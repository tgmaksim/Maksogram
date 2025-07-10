import asyncio

from mg.config import OWNER

from datetime import timedelta
from mg.client import MaksogramClient
from mg.client.functions import get_accounts
from mg.core.functions import time_now, set_is_paid

from mg.bot.maksogram_bot import bot
from mg.bot.functions import get_payment_data, payment_menu, set_time_subscription_notification


async def subscriptions():
    await asyncio.sleep(60)  # Ожидание полного запуска клиентов

    while True:
        for account_id, is_started in await get_accounts():
            payment_info = await get_payment_data(account_id)
            if payment_info.user == 'admin' or not payment_info.is_paid:
                continue

            if time_now() <= payment_info.next_payment <= (time_now() + timedelta(days=1)):  # За день до конца
                if time_now() - payment_info.first_notification >= timedelta(days=1):  # Уведомление об окончании подписки еще не пришло

                    await set_time_subscription_notification(account_id, "first")

                    if is_started:
                        await bot.send_message(account_id, "Подписка Maksogram заканчивается, чтобы продолжить пользоваться, выберите и оплатите подписку")
                        await bot.send_photo(account_id, **await payment_menu())
                    await bot.send_message(OWNER, f"Подписка заканчивается ({account_id})")

            elif payment_info.next_payment <= (time_now() - timedelta(days=1)):  # После дня окончания
                await set_is_paid(account_id, False)

                if is_started:
                    await MaksogramClient.off_account(account_id)
                    await bot.send_message(account_id, "Подписка истекла, Maksogram остановлен!")
                await bot.send_message(OWNER, f"Подписка истекла, Maksogram остановлен ({account_id})")

            elif (time_now() - timedelta(days=1)) <= payment_info.next_payment <= time_now():  # В день окончания
                if time_now() - payment_info.second_notification >= timedelta(days=1):  # Уведомление об окончании подписки еще не пришло

                    await set_time_subscription_notification(account_id, "second")

                    if is_started:
                        await bot.send_message(account_id, "Подписка Maksogram истекает завтра, выберите и оплатите, чтобы продолжить пользоваться")
                    await bot.send_message(OWNER, f"Платеж просрочен ({account_id})")

        await asyncio.sleep(1*60)  # Проверка каждый час
