import os
import aiohttp

from core import human_bytes
from telethon import TelegramClient
from aiogram.types import Message as BotMessage
from aiogram.types import InlineKeyboardButton as IButton
from aiogram.types import InlineKeyboardMarkup as IMarkup
from telethon.tl.patched import Message as AccountMessage


api_key = os.environ['ApiKey']
documents_path = "/home/c87813/tgmaksim.ru/www/документы"


async def reload_server():  # перезагрузка сервера (сайта, ботов, программ, игр)
    async with aiohttp.ClientSession() as session:
        async with session.post("https://panel.netangels.ru/api/gateway/token/", data={"api_key": api_key}) as response:
            token = (await response.json())['token']  # получение Bearer-токена
            response_status_site = await session.get("https://api-ms.netangels.ru/api/v1/hosting/virtualhosts/297559/",
                                                     headers={"Authorization": f"Bearer {token}"})
            status_site = (await response_status_site.json())['state'] == "ENABLED"
            if status_site:  # если сайт reminder.tgmaksim.ru включен
                await session.put("https://api-ms.netangels.ru/api/v1/hosting/virtualhosts/297559/restart/",
                                  headers={"Authorization": f"Bearer {token}"})
            await session.put("https://api-ms.netangels.ru/api/v1/hosting/virtualhosts/276599/restart/",
                              headers={"Authorization": f"Bearer {token}"})


async def upload_file(message: AccountMessage, progress_message: BotMessage):
    async def progress_callback(recieved: int, total: int):
        if recieved/total*100 != progress[0]:
            progress[0] = recieved/total*100
            await progress_message.edit_text(f"Загрузка файла: {human_bytes(recieved)}/{human_bytes(total)}")

    client: TelegramClient = message.client
    progress = [0.0]
    await client.download_media(message, f"{documents_path}/{message.text}", progress_callback=progress_callback)
    markup = IMarkup(inline_keyboard=[[IButton(text="Проверить", url=f"https://tgmaksim.ru/документы/{message.text}")]])
    await progress_message.edit_text("Файл загружен\n#upload_file", reply_markup=markup)
