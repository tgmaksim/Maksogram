import re

from typing import Union, Optional

from . functions import get_main_currency, convert_currencies


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


class ResultConvertionCurrencies:
    def __init__(self, value: int, currency0: str, currency1: str):
        self.value = value
        self.currency0 = currency0
        self.currency1 = currency1

    async def __call__(self, account_id: int) -> str:
        if self.currency1.lower() == "<main_currency>":
            self.currency1 = await get_main_currency(account_id)

            if self.currency1 is None:
                self.currency1 = "RUB"

            if self.currency0 == self.currency1:
                self.currency1 = "RUB" if self.currency0 == "USD" else "USD"

        res = await convert_currencies(self.value, self.currency0, self.currency1)
        res_str = f"{res:,}".replace(',', "'")

        return f"{self.value} {self.currency0} ≈ {res_str} {self.currency1}"


def get_currency(string: str) -> Optional[str]:
    for currency_id in currencies:
        if string in currencies[currency_id]:
            return currency_id


def currency_rate(text: str = None, my_currencies: list[str] = None) -> Optional[Union[ResultConvertionCurrencies, list[ResultConvertionCurrencies]]]:
    if my_currencies:  # Курсы нужных валют
        return list(map(currency_rate, [f"Курс {currency}".lower() for currency in my_currencies]))

    match0 = re.fullmatch(rf'курс +({"|".join(sum(list(currencies.values()), []))})', text)
    match1 = re.fullmatch(rf'курс +({"|".join(sum(list(currencies.values()), []))}) +к +'
                          rf'({"|".join(sum(list(currencies.values()), []))})', text)
    match2 = re.fullmatch(rf'({"|".join(sum(list(currencies.values()), []))}) +в +'
                          rf'({"|".join(sum(list(currencies.values()), []))})', text)
    match3 = re.fullmatch(rf'(\d+\.?\d*) *({"|".join(sum(list(currencies.values()), []))})', text)
    match4 = re.fullmatch(rf'(\d+\.?\d*) *({"|".join(sum(list(currencies.values()), []))}) +в +'
                          rf'({"|".join(sum(list(currencies.values()), []))})', text)

    value = 1
    currency1 = "<main_currency>"
    if match := match0:
        currency0 = get_currency(match.group(1))

    elif match := (match1 or match2):
        currency0 = get_currency(match.group(1))
        currency1 = get_currency(match.group(2))

    elif match := (match3 or match4):
        value = float(match.group(1))
        currency0 = get_currency(match.group(2))
        if match4:
            currency1 = get_currency(match.group(3))

    else:
        return

    return ResultConvertionCurrencies(value, currency0.upper(), currency1.upper())
