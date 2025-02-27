from datetime import timedelta
from . import program, admin_program
from aiogram.exceptions import TelegramForbiddenError
from core import (
    db,
    OWNER,
    time_now,
    account_on,
    MaksogramBot,
    telegram_clients,
    new_telegram_client,
    UserIsNotAuthorized,
)


async def main():
    for account_id in await db.fetch_all("SELECT account_id FROM accounts", one_data=True):
        account_id: int
        phone_number = await db.fetch_one(f"SELECT phone_number FROM accounts WHERE account_id={account_id}", one_data=True)
        name = await db.fetch_one(f"SELECT name FROM accounts WHERE account_id={account_id}", one_data=True)
        telegram_clients[account_id] = new_telegram_client(f"+{phone_number}")
        is_started: bool = await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True)
        payment = await db.fetch_one(f"SELECT \"user\", is_paid, next_payment, second_notification FROM payment WHERE account_id={account_id}")
        if payment['user'] == 'user' and payment['is_paid']:
            if payment['next_payment'] <= (time_now() - timedelta(days=1)):  # После дня окончания
                try:
                    await db.execute(f"UPDATE payment SET is_paid=false WHERE account_id={account_id}")
                    await db.execute(f"UPDATE settings SET is_started=false WHERE account_id={account_id}")
                    await MaksogramBot.send_message(account_id, "Ваша подписка истекла. Продлите ее, чтобы пользоваться Maksogram")
                    await MaksogramBot.send_system_message(f"Платеж просрочен. Maksogram не запущен ({name})")
                except TelegramForbiddenError:
                    pass
                continue
            if (time_now() - timedelta(days=1)) <= payment['next_payment'] <= time_now():  # В день окончания
                if (time_now() - payment['second_notification']).total_seconds() >= 23*60*60 + 50*60:  # Прошлое уведомление было не менее 23 часов 50 минут назад
                    await db.execute(f"UPDATE payment SET second_notification=now() WHERE account_id={account_id}")
                    try:
                        await MaksogramBot.send_message(account_id, "Ваша подписка истечет завтра. Продлите ее, чтобы пользоваться Maksogram")
                        await MaksogramBot.send_system_message(f"Платеж просрочен ({name})")
                    except TelegramForbiddenError:
                        pass

        if not is_started or not payment['is_paid']:
            continue

        try:
            await account_on(account_id, (admin_program if account_id == OWNER else program).Program)
        except ConnectionError as e:
            await MaksogramBot.send_message(account_id, "Произошла ошибка при запуске Maksogram, скоро все будет исправлено. "
                                                        "Желательно ничего не трогать :)")
            raise e
        except UserIsNotAuthorized:
            await db.execute(f"UPDATE settings SET is_started=false WHERE account_id={account_id}")
            try:
                await MaksogramBot.send_message(account_id, "Вы удалили сессию Telegram, Maksogram не может работать без нее")
            except TelegramForbiddenError:
                pass
            continue
