import os
import asyncio

from mg.admin.functions import reload_maksogram
from mg.core.functions import www_path, time_now

from mg.ghost_mode.functions import BASE_PATH_STORIES


async def reload():
    for file in os.listdir(www_path(BASE_PATH_STORIES)):
        old = int(file.split('.')[3])

        if time_now().timestamp() - old >= 24 * 60 * 60:
            os.remove(www_path(f"{BASE_PATH_STORIES}/{file}"))

    await reload_maksogram(logging=False)

if __name__ == '__main__':
    asyncio.run(reload())