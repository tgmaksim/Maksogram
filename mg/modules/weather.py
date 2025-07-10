import aiohttp

from mg.config import OPENWEATHERMAP_API_KEY

from dataclasses import dataclass
from typing import Optional, Union, Any

from . functions import get_city


@dataclass
class ResultWeather:
    ok: bool
    city: str
    weather: Optional[str]
    error: Optional[Exception]


class WeatherRequestError(Exception):
    pass


API_URL = f"https://api.openweathermap.org/data/2.5/weather?lang=ru&units=metric&appid={OPENWEATHERMAP_API_KEY}"
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
    if 0 <= wind['speed'] < 3:
        speed = "легкий"
    elif 3 <= wind['speed'] < 6:
        speed = "слабый"
    elif 6 <= wind['speed'] < 10:
        speed = "умеренный"
    elif 10 <= wind['speed'] < 14:
        speed = "сильный"
    elif 14 <= wind['speed'] < 21:
        speed = "⚠️ <b>очень сильный</b>"
    elif 21 <= wind['speed'] < 25:
        speed = "⚠️ <b>шторм</b>"
    elif 25 <= wind['speed'] < 29:
        speed = "⚠️ <b>сильный шторм</b>"
    else:  # wind['speed'] > 30
        speed = "⚠️ <b>ураган</b>"
    return f"{speed} {direction}"


def get_status(statuses: list[dict[str, Union[str, int]]]) -> str:
    result = []
    for status in statuses:
        icon = icons.get(status['icon'], "")
        result.append(f"{icon} {status['description']}")
    return " ".join(result)


async def get_weather(city: str) -> Optional[str]:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_URL}&q={city}") as response:
            request: dict[str, Any] = await response.json()

            if request['cod'] == 200:
                return f"{get_status(request['weather'])}\n" \
                       f"Температура: {round(request['main']['temp'])}°C\n" \
                       f"Ощущается: {round(request['main']['feels_like'])}°C\n" \
                       f"Давление: {round(request['main']['pressure'] / 1.333)} мм рт столба\n" \
                       f"Ветер: {get_wind(request['wind'])}"

            raise WeatherRequestError(f"{request['cod']}: {request['message']}")


async def weather(account_id: int) -> ResultWeather:
    city = await get_city(account_id)

    try:
        text = await get_weather(city)
    except WeatherRequestError as e:
        return ResultWeather(
            ok=False,
            city=city,
            weather=None,
            error=e
        )
    else:
        return ResultWeather(
            ok=True,
            city=city,
            weather=text,
            error=None
        )


async def check_city(city: str) -> bool:
    try:
        await get_weather(city)
    except WeatherRequestError:
        return False

    return True
