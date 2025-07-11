from mg.client import MaksogramClient
from mg.core.types import MaksogramBot
from mg.core.functions import format_error
from mg.bot.types import feedback_link, support_link
from telethon.errors.rpcerrorlist import UserIsBlockedError
from mg.client.functions import get_accounts, new_telegram_client
from mg.client.types import maksogram_clients, UserIsNotAuthorized


async def start_clients():
    for account_id, is_started in await get_accounts():
        if not is_started:
            continue

        maksogram_client = MaksogramClient(account_id, new_telegram_client(account_id))
        maksogram_clients[account_id] = maksogram_client

        try:
            await maksogram_client.on_account(account_id)
        except UserIsNotAuthorized:
            await maksogram_client.set_is_started(False)

            try:
                await MaksogramBot.send_message(
                    account_id, "Чтобы Maksogram уведомлял об удалении и изменении сообщений, нужно войти в аккаунт. Понимаем ваши опасения "
                                f"по поводу безопасности: вы можете почитать {feedback_link} или написать {support_link}", link_preview=False)
            except UserIsBlockedError:
                pass

            await MaksogramBot.send_system_message(f"Удалена сессия у {account_id}")
        except Exception as e:
            await MaksogramBot.send_system_message(f"Ошибка при запуске {account_id}" + format_error(e))
