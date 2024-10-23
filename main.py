import core
import asyncio

import program
import admin_program

from typing import Union
from accounts import Account
from asyncio import AbstractEventLoop
from telethon.sync import TelegramClient


def main(account_run: Union[int, None] = None):
    main_loop = asyncio.get_event_loop()

    accounts = Account.get_accounts()
    for account in accounts:
        telegram_client = TelegramClient(
            account.get_session_path(),
            core.Data.APPLICATION_ID,
            core.Data.APPLICATION_HASH,
            device_model=account.device_model,
            system_version="Windows 10 x64",
            app_version="%s x64" % core.Data.version,
            lang_code="ru",
            system_lang_code="ru"
        )

        if account.id != account_run or account.my_messages == 0:
            continue
        start = admin_start if account.id == 5128609241 else account_start

        print("Вход %s" % account.name)
        telegram_client.connect()
        if not telegram_client.is_user_authorized():
            telegram_client.start(phone=lambda: account.phone, password=lambda: account.password)
        print("Запуск %s (v%s)" % (account.name, core.Data.version))
        start(main_loop, account, telegram_client)

    main_loop.run_forever()  # Погнали


def admin_start(loop: AbstractEventLoop, account: Account, telegram_client: TelegramClient):
    loop.create_task(admin_program.Program(telegram_client, account).run_until_disconnected())


def account_start(loop: AbstractEventLoop, account: Account, telegram_client: TelegramClient):
    loop.create_task(program.Program(telegram_client, account).run_until_disconnected())


if __name__ == '__main__':
    main()
