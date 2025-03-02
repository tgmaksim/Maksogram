import aiohttp

from typing import Union
from core import db, MaksogramBot
from sys_keys import openweathermap_api_key


API_URL = f"https://api.openweathermap.org/data/2.5/weather?lang=ru&units=metric&appid={openweathermap_api_key}"
icons = {
    "01d": "☀️", "01n": "🌙",
    "02d": "⛅️", "02n": "⛅️",
    "03d": "☁️", "03n": "☁️",
    "04d": "☁️", "04n": "☁️",
    "09d": "🌧",  "09n": "🌧",
    "10d": "🌧",  "10n": "🌧",
    "11d": "🌩",  "11n": "🌩",
    "13d": "🌨",  "13n": "🌨",
    "50d": "⚪️",  "50n": "⚪️",
}


async def check_city(city: str) -> bool:
    return await get_weather(city) is not None


def get_wind(wind: dict[str, Union[str, int]]) -> str:
    if 337.5 <= wind['deg'] or wind['deg'] < 22.5:
        direction = "северный"
    elif 22.5 <= wind['deg'] < 67.5:
        direction = "северо-восточный"
    elif 67.5 <= wind['deg'] < 112.5:
        direction = "северный"
    elif 112.5 <= wind['deg'] < 157.5:
        direction = "юго-восточный"
    elif 157.5 <= wind['deg'] < 202.5:
        direction = "южный"
    elif 202.5 <= wind['deg'] < 247.5:
        direction = "юго-западный"
    elif 247.5 <= wind['deg'] < 292.5:
        direction = "западный"
    elif 292.5 <= wind['deg'] < 337.5:
        direction = "северо-западный"
    else:
        direction = ""
    return f"{direction} {wind['speed']} м/с 💨"


def get_status(statuses: list[dict[str, Union[str, int]]]) -> str:
    result = []
    for status in statuses:
        icon = icons.get(status['icon'], "")
        result.append(f"{icon} {status['description']}")
    return " ".join(result)


async def get_weather(city: str) -> Union[dict[str, Union[str, int]], None]:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_URL}&q={city}") as response:
            request: dict[str, Union[str, int]] = await response.json()
            if request['cod'] == 200:
                return f"{get_status(request['weather'])}\n" \
                       f"Температура: {round(request['main']['temp'])}°C\n" \
                       f"Ощущается: {round(request['main']['feels_like'])}°C\n" \
                       f"Давление: {round(request['main']['pressure'] / 1.333)} мм рт столба\n" \
                       f"Ветер: {get_wind(request['wind'])}"


async def main(account_id: int) -> str:
    city = await db.fetch_one(f"SELECT city FROM settings WHERE account_id={account_id}", one_data=True)
    weather = await get_weather(city)
    if weather is None:
        await MaksogramBot.send_system_message("⚠️Ошибка в погоде⚠️\nКод запроса не равен 200")
        return f"<b>Погода в городе {city}</b>\nПроизошла ошибка..."
    return f"<b>Погода в городе {city}</b>\n\n{weather}"
