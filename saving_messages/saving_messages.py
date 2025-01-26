from . import program, admin_program

from datetime import timedelta
from . accounts import Account, UserIsNotAuthorized
from aiogram.exceptions import TelegramForbiddenError
from core import OWNER, Variables, time_now, MaksogramBot


async def warning(account: Account):
    await MaksogramBot.send_message(account.id, "Ваша подписка истечет завтра. Продлите ее, чтобы пользоваться Maksogram")
    await MaksogramBot.send_system_message(f"Платеж просрочен ({account.name})")


async def error(account: Account):
    await account.set_status_payment(False)
    await account.off()
    await MaksogramBot.send_message(account.id, "Ваша подписка истекла. Продлите ее, чтобы пользоваться Maksogram")
    await MaksogramBot.send_system_message(f"Платеж просрочен. maksogram не запущен ({account.name})")


async def main():
    accounts = Account.get_accounts()
    for account in accounts:
        if account.payment.user == 'user':
            if account.payment.next_payment.strftime("%Y/%m/%d") == time_now().strftime("%Y/%m/%d"):
                await warning(account)
            elif (time_now() + timedelta(days=1)) >= account.payment.next_payment and account.is_started:
                await error(account)
                continue

        if not account.my_messages or not account.is_started or not account.is_paid:
            continue

        print("Вход %s" % account.name)
        try:
            await account.on((admin_program if account.id == OWNER else program).Program)
        except UserIsNotAuthorized:
            await account.off()
            try:
                await MaksogramBot.send_message(account.id, "Вы удалили сессию Telegram, Maksogram не может работать без нее")
            except TelegramForbiddenError:
                pass
            continue
        print("Запуск %s (v%s)" % (account.name, Variables.version))
