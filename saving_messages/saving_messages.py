from datetime import timedelta
from . import program, admin_program
from aiogram.exceptions import TelegramForbiddenError
from core import (
    db,
    OWNER,
    time_now,
    account_on,
    MaksogramBot,
    async_processes,
    telegram_clients,
    new_telegram_client,
    UserIsNotAuthorized,
)


async def main():
    for account in await db.fetch_all("SELECT account_id, phone_number, name FROM accounts"):
        account_id: int = account['account_id']
        telegram_clients[account_id] = new_telegram_client(f"+{account['phone_number']}")
        async_processes[account_id] = []
        is_started: bool = await db.fetch_one(f"SELECT is_started FROM settings WHERE account_id={account_id}", one_data=True)
        payment = await db.fetch_one(f"SELECT \"user\", is_paid, next_payment, second_notification FROM payment WHERE account_id={account_id}")
        if payment['user'] == 'user' and payment['is_paid']:
            if payment['next_payment'] <= (time_now() - timedelta(days=1)):  # После дня окончания
                try:
                    await db.execute(f"UPDATE payment SET is_paid=false WHERE account_id={account_id}")
                    await db.execute(f"UPDATE settings SET is_started=false WHERE account_id={account_id}")
                    if is_started:
                        await MaksogramBot.send_message(account_id, "Ваша подписка истекла. Продлите ее, чтобы пользоваться Maksogram")
                    await MaksogramBot.send_system_message(f"Платеж просрочен. Maksogram не запущен ({account['name']})")
                except TelegramForbiddenError:
                    pass
                continue
            if (time_now() - timedelta(days=1)) <= payment['next_payment'] <= time_now():  # В день окончания
                if (time_now() - payment['second_notification']).total_seconds() >= 23*60*60 + 50*60:  # Прошлое уведомление было не менее 23 часов 50 минут назад
                    await db.execute(f"UPDATE payment SET second_notification=now() WHERE account_id={account_id}")
                    try:
                        if is_started:
                            await MaksogramBot.send_message(account_id, "Ваша подписка истечет завтра. Продлите ее, чтобы пользоваться Maksogram")
                        await MaksogramBot.send_system_message(f"Платеж просрочен ({account['name']})")
                    except TelegramForbiddenError:
                        pass

        if not is_started or not payment['is_paid']:
            continue

        try:
            await account_on(account_id, (admin_program if account_id == OWNER else program).Program)
        except ConnectionError as e:
            await MaksogramBot.send_message(account_id, "Произошла ошибка при запуске Maksogram, скоро все будет исправлено. "
                                                        "Желательно ничего не трогать :)")
            await MaksogramBot.send_system_message(f"⚠️Ошибка⚠️\n\n{e.__class__.__name__}: {e}")
        except UserIsNotAuthorized:
            await db.execute(f"UPDATE settings SET is_started=false WHERE account_id={account_id}")
            try:
                await MaksogramBot.send_message(account_id, "Вы удалили сессию Telegram, Maksogram не может работать без нее")
            except TelegramForbiddenError:
                pass
            continue
