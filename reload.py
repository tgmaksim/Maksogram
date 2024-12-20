import os
import aiohttp
import asyncio

from dotenv import load_dotenv


dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

api_key = os.environ['ApiKey']
process_id = os.environ['ProcessIdMaksogram']


async def reload():
    async with aiohttp.ClientSession() as session:
        async with session.post("https://panel.netangels.ru/api/gateway/token/",
                                data={"api_key": api_key}) as response:
            token = (await response.json())['token']
            await session.post(f"https://api-ms.netangels.ru/api/v1/hosting/background-processes/{process_id}/restart",
                               headers={"Authorization": f"Bearer {token}"})

if __name__ == '__main__':
    asyncio.run(reload())
