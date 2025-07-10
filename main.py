import sys
import asyncio

from mg.core.database import Database
from mg.core.types import MaksogramBot
from subscription import subscriptions
from mg.bot.maksogram_bot import start_bot
from mg.client.start_clients import start_clients


def check_argv():
    program_variant = sys.argv[1]
    if program_variant not in ("release", "debug"):
        raise SystemError("Выберите вариант запуска программы: release или debug")


if __name__ == '__main__':
    check_argv()  # Проверка правильности запуска

    main_loop = asyncio.new_event_loop()  # Получение цикла событий asyncio
    main_loop.run_until_complete(MaksogramBot.init())  # Инициализация MaksogramBot (telethon)
    main_loop.run_until_complete(Database.init())  # Инициализация пула соединений с базой данных

    main_loop.create_task(subscriptions())  # Добавление в цикл событий обработчика подписок
    main_loop.create_task(start_clients())  # Добавление в цикл событий функций для каждого пользователя
    main_loop.create_task(start_bot())  # Добавление в цикл событий функции для бота

    main_loop.run_forever()  # Запуск всех функций в цикле asyncio
