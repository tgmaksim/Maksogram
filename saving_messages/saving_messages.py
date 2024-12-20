from . import program, admin_program

from datetime import timedelta
from . accounts import Account
from asyncio import AbstractEventLoop
from telethon.sync import TelegramClient
from core import OWNER, get_telegram_client, Variables, time_now, MaksogramBot


async def warning(account: Account):
    await MaksogramBot.send_message(account.id, "Ваш платеж просрочен! Программа будет отключена завтра. Способы оплаты /payment "
                                                "Если вы отправили деньги, то проверьте еще раз и напишите отзыв /feedback")
    await MaksogramBot.send_system_message(f"Платеж просрочен ({account.name})")


async def error(account: Account):
    await account.set_status_payment(False)
    await account.off()
    await MaksogramBot.send_message(account.id, "Ваш платеж просрочен. Программа остановлена. Отправьте нужную "
                                                "сумму или напишите отзыв, если произошла ошибка. Во всем разберемся! Способы оплаты /payment")
    await MaksogramBot.send_system_message(f"Платеж просрочен. Программа не запущена ({account.name})")


def main(loop: AbstractEventLoop):
    accounts = Account.get_accounts()
    for account in accounts:
        telegram_client = get_telegram_client(account.phone)

        if account.payment.user == 'user':
            if account.payment.next_payment.strftime("%Y/%m/%d") == time_now().strftime("%Y/%m/%d"):
                loop.create_task(warning(account))
            elif (account.payment.next_payment + timedelta(days=1)).strftime("%Y/%m/%d") == \
                    time_now().strftime("%Y/%m/%d") and account.is_started:
                loop.create_task(error(account))
                continue

        if not account.my_messages or not account.is_started or not account.is_paid:
            continue
        start = admin_start if account.id == OWNER else account_start

        print("Вход %s" % account.name)
        telegram_client.connect()
        if not telegram_client.is_user_authorized():
            loop.create_task(account.off())
            loop.create_task(MaksogramBot.send_message(account.id, "Вы удалили сессию Telegram, программа не работает"))
            continue
        print("Запуск %s (v%s)" % (account.name, Variables.version))
        start(loop, account.id, telegram_client)


def admin_start(loop: AbstractEventLoop, account_id: int, telegram_client: TelegramClient):
    loop.create_task(admin_program.Program(telegram_client, account_id).run_until_disconnected())


def account_start(loop: AbstractEventLoop, account_id: int, telegram_client: TelegramClient):
    loop.create_task(program.Program(telegram_client, account_id).run_until_disconnected())
