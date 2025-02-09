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


async def warning(id: int, name: str):
    await MaksogramBot.send_message(id, "Ваша подписка истечет завтра. Продлите ее, чтобы пользоваться Maksogram")
    await MaksogramBot.send_system_message(f"Платеж просрочен ({name})")


async def main():
    for account in await db.fetch_all("SELECT id, name, is_started, is_paid, payment, phone_number FROM accounts"):
        telegram_clients[account['id']] = new_telegram_client(f"+{account['phone_number']}")
        if account['payment']['user'] == 'user' and account['is_started'] and account['is_paid']:
            if account['payment']['next_payment'] + 24*60*60 <= time_now().timestamp():
                await db.execute(f"UPDATE accounts SET is_paid=false WHERE id={account['id']}")
                await db.execute(f"UPDATE accounts SET is_started=false WHERE id={account['id']}")
                await MaksogramBot.send_message(account['id'], "Ваша подписка истекла. Продлите ее, чтобы пользоваться Maksogram")
                await MaksogramBot.send_system_message(f"Платеж просрочен. Maksogram не запущен ({account['name']})")
                continue
            if account['payment']['next_payment'] <= time_now().timestamp():
                await MaksogramBot.send_message(account['id'], "Ваша подписка истечет завтра. "
                                                               "Продлите ее, чтобы пользоваться Maksogram")
                await MaksogramBot.send_system_message(f"Платеж просрочен ({account['name']})")

        if not account['is_started'] or not account['is_paid']:
            continue

        try:
            await account_on(account['id'], (admin_program if account['id'] == OWNER else program).Program)
        except UserIsNotAuthorized:
            await db.execute(f"UPDATE accounts SET is_started=false WHERE id={account['id']}")
            try:
                await MaksogramBot.send_message(account['id'], "Вы удалили сессию Telegram, Maksogram не может работать без нее")
            except TelegramForbiddenError:
                pass
            continue
