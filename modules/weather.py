import aiohttp

from typing import Union
from core import db, MaksogramBot
from sys_keys import openweathermap_api_key


API_URL = f"https://api.openweathermap.org/data/2.5/weather?lang=ru&units=metric&appid={openweathermap_api_key}"


async def check_city(city: str) -> bool:
    return await get_weather(city) is not None


async def get_weather(city: str) -> Union[dict[str, Union[str, int]], None]:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_URL}&q={city}") as response:
            request: dict[str, Union[str, int]] = await response.json()
            if request['cod'] == 200:
                return {"Состояние": request['weather'][0]['description'].title(),
                        "Температура": f"{round(request['main']['temp'])}°C",
                        "Ощущается": f"{round(request['main']['feels_like'])}°C",
                        "Давление": f"{round(request['main']['pressure'] / 1.333)} мм рт столба",
                        "Скорость ветра": f"{round(request['wind']['speed'])} м/с"}


async def main(account_id: int) -> str:
    city = await db.fetch_one(f"SELECT city FROM settings WHERE account_id={account_id}", one_data=True)
    weather = await get_weather(city)
    if weather is None:
        await MaksogramBot.send_system_message("⚠️Ошибка в погоде⚠️\nКод запроса не равен 200")
        return "Произошла ошибка..."
    return f"Погода в городе {city}\n" + "\n".join([f"{parameter}: {weather[parameter]}" for parameter in weather])
