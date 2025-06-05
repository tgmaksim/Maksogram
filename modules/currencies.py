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


currencies = {"RUB": {0: "рубль", 1: "рубля", 2: "ruble", 3: "rub"}, "USD": {0: "доллар", 1: "доллара", 2: "dollar", 3: "usd"},
              "EUR": {0: "евро", 1: "евро", 2: "euro", 3: "eur"}, "JPY": {0: "иена", 1: "иены", 2: "yen", 3: "jpy"},
              "GBP": {0: "фунт", 1: "фунта", 2: "pound", 3: "gbp"}, "CNY": {0: "юань", 1: "юаня", 2: "yuan", 3: "cny"},

              "BTC": {0: "биткоин", 1: "биткоина", 2: "bitcoin", 3: "btc"}, "ETH": {0: "эфириум", 1: "эфириума", 2: "ethereum", 3: "eth"},
              "USDT": {0: "usdt", 1: "usdt", 2: "tether", 3: "usdt"}, "BNB": {0: "бинанс", 1: "бинанса", 2: "binance", 3: "bnb"},
              "TRX": {0: "трон", 1: "трона", 2: "tron", 3: "trx"}, "TON": {0: "тон", 1: "тона", 2: "toncoin", 3: "ton"},
              "XPR": {0: "xpr", 1: "xpr", 2: "xpr", 3: "xpr"}, "SOL": {0: "солана", 1: "солана", 2: "solana", 3: "sol"}}


def get_currency(string: str) -> str:
    for id in currencies:
        if string in currencies[id].values():
            return id


def main(text: str = None) -> Union[Result, list[Result]]:
    if not text:  # Курсы всех доступных валют
        return list(map(main, [f"Курс {currency}".lower() for currency in currencies]))

    match0 = re.fullmatch(rf'курс +({"|".join(sum(map(lambda x: list(x.values()), currencies.values()), []))})', text)
    match1 = re.fullmatch(rf'курс +({"|".join(sum(map(lambda x: list(x.values()), currencies.values()), []))}) +к +'
                          rf'({"|".join(sum(map(lambda x: list(x.values()), currencies.values()), []))})', text)
    match2 = re.fullmatch(rf'({"|".join(sum(map(lambda x: list(x.values()), currencies.values()), []))}) +в +'
                          rf'({"|".join(sum(map(lambda x: list(x.values()), currencies.values()), []))})', text)
    match3 = re.fullmatch(rf'(\d+\.?\d*) *({"|".join(sum(map(lambda x: list(x.values()), currencies.values()), []))})', text)
    match4 = re.fullmatch(rf'(\d+\.?\d*) *({"|".join(sum(map(lambda x: list(x.values()), currencies.values()), []))}) +в +'
                          rf'({"|".join(sum(map(lambda x: list(x.values()), currencies.values()), []))})', text)

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
