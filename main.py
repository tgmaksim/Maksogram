import sys
import asyncio

from maksogram_bot import maksogram_bot
from saving_messages import saving_messages


def check_argv():
    program_variant = sys.argv[1]
    if program_variant not in ("release", "debug"):
        raise TypeError("Выберите вариант запуска программы: release или debug")


if __name__ == '__main__':
    check_argv()  # Проверка правильности запуска
    main_loop = asyncio.get_event_loop()  # Получение цикла событий asyncio
    saving_messages.main(main_loop)  # Добавление в цикл событий функций для каждого пользователя
    main_loop.create_task(maksogram_bot.start_bot())  # Добавление в цикл событий функции для бота
    main_loop.run_forever()  # Запуск всех функций в цикле asyncio
