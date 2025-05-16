import os
import re
import aiohttp
import asyncio

from dotenv import load_dotenv
from core import www_path, time_now


dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

api_key = os.environ['ApiKey']
process_id = os.environ['ProcessIdMaksogram']


async def reload():
    for file in os.listdir(www_path("posts")):
        old = int(re.split(r'\.|-', file)[3])
        if old + 24*60*60 <= time_now().timestamp():
            os.remove(www_path(f"posts/{file}"))
    for file in os.listdir(www_path("stories")):
        old = int(re.split(r'\.|-', file)[3])
        if old + 24*60*60 <= time_now().timestamp():
            os.remove(www_path(f"stories/{file}"))
    async with aiohttp.ClientSession() as session:
        async with session.post("https://panel.netangels.ru/api/gateway/token/",
                                data={"api_key": api_key}) as response:
            token = (await response.json())['token']
            await session.post(f"https://api-ms.netangels.ru/api/v1/hosting/background-processes/{process_id}/restart",
                               headers={"Authorization": f"Bearer {token}"})

if __name__ == '__main__':
    asyncio.run(reload())
