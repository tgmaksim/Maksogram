from . import program, admin_program
from aiogram.exceptions import TelegramForbiddenError
from core import (
    db,
    OWNER,
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

        if not is_started:
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
            await MaksogramBot.send_system_message(f"Удалена сессия у пользователя {account['name']}")
