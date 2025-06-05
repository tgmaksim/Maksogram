import re

from typing import Union
from core import convert_currencies


class Result:
    def __init__(self, value: int, currency0: str, currency1: str):
        self.value = value
        self.currency0 = currency0
        self.currency1 = currency1

    async def __call__(self) -> str:
        res = await convert_currencies(self.value, self.currency0, self.currency1)
        return f"""{self.value} {self.currency0} ≈ {f"{res:,}".replace(',', "'")} {self.currency1}"""


currencies = {
    "RUB": ["рубль", "рубля", "рублей", "рублю", "рублях", "ruble", "rub"],
    "USD": ["доллар", "доллара", "долларов", "доллару", "долларах", "dollar", "usd"],
    "EUR": ["евро", "euro", "eur"],
    "JPY": ["иена", "иены", "иен", "иене", "иенах", "yen", "jpy"],
    "GBP": ["фунт", "фунта", "фунтов", "фунту", "фунтах", "pound", "gbp"],
    "CNY": ["юань", "юаня", "юаней", "юаню", "юанях", "yuan", "cny"],
    "BTC": ["биткоин", "биткоина", "биткоину", "биткоинов", "биткоинах", "bitcoin", "btc"],
    "ETH": ["эфириум", "эфириума", "эфириума", "эфириуму", "эфириумах", "ethereum", "eth"],
    "USDT": ["usdt", "tether", "usdt"],
    "BNB": ["бинанс", "бинанса", "бинансов", "бинансу", "бинансах", "binance", "bnb"],
    "TRX": ["трон", "трона", "трону", "тронах", "tron", "trx"],
    "TON": ["тон", "тона", "тону", "тонах", "toncoin", "ton"],
    "XPR": ["xpr"],
    "SOL": ["солана", "solana", "sol"]
}


def get_currency(string: str) -> str:
    for id in currencies:
        if string in currencies[id]:
            return id


def main(text: str = None) -> Union[Result, list[Result]]:
    if not text:  # Курсы всех доступных валют
        return list(map(main, [f"Курс {currency}".lower() for currency in currencies]))

    match0 = re.fullmatch(rf'курс +({"|".join(sum(list(currencies.values()), []))})', text)
    match1 = re.fullmatch(rf'курс +({"|".join(sum(list(currencies.values()), []))}) +к +'
                          rf'({"|".join(sum(list(currencies.values()), []))})', text)
    match2 = re.fullmatch(rf'({"|".join(sum(list(currencies.values()), []))}) +в +'
                          rf'({"|".join(sum(list(currencies.values()), []))})', text)
    match3 = re.fullmatch(rf'(\d+\.?\d*) *({"|".join(sum(list(currencies.values()), []))})', text)
    match4 = re.fullmatch(rf'(\d+\.?\d*) *({"|".join(sum(list(currencies.values()), []))}) +в +'
                          rf'({"|".join(sum(list(currencies.values()), []))})', text)

    value = 1
    currency1 = "RUB"
    if match := match0:
        currency0 = get_currency(match.group(1))
        currency1 = "RUB" if currency0 != "RUB" else "USD"
    elif match := (match1 or match2):
        currency0 = get_currency(match.group(1))
        currency1 = get_currency(match.group(2))
    elif match := (match3 or match4):
        value = float(match.group(1))
        currency0 = get_currency(match.group(2))
        if match4: currency1 = get_currency(match.group(3))
    else:
        return

    return Result(value, currency0.upper(), currency1.upper())
