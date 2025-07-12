from mg.config import YOOMONEY_API_ID, YOOMONEY_API_KEY

from yookassa import Configuration, Payment

from datetime import datetime
from typing import Any, Optional
from mg.core.database import Database
from mg.core.types import MaksogramBot
from mg.core.functions import zip_int_data
from asyncpg.exceptions import UniqueViolationError


Configuration.configure(account_id=YOOMONEY_API_ID, secret_key=YOOMONEY_API_KEY)


class YPayment:
    def __init__(self, payment_id: str, time: datetime):
        self.id = payment_id
        self.time = time

    @classmethod
    def from_json(cls, json_data: dict[str, Any]) -> 'YPayment':
        return cls(
            payment_id=json_data['payment_id'],
            time=json_data['time']
        )


async def create_payment(account_id: int, amount: int, about: str, subscription_id: int) -> str:
    """Создает ссылку для оплаты Maksogram Premium"""

    payment = Payment.create({
        'amount': {
            'value': f"{amount:0.2f}",
            'currency': 'RUB',
        },
        'description': f"Maksogram Premium для {account_id} на {about.lower()}",
        'confirmation': {
            'type': 'redirect',
            'return_url': f"https://t.me/{MaksogramBot.username}?start=p{zip_int_data(subscription_id)}"
        },
        'metadata': {
            'account_id': account_id,
            'subscription_id': subscription_id
        },
        'capture': True
    })

    await add_payment(account_id, payment.id)

    return payment.confirmation.confirmation_url


async def add_payment(account_id: int, payment_id: str):
    """Добавляет платеж в базу данных для последующей проверки транзакции"""

    sql = "INSERT INTO yoomoney (account_id, payment_id, time) VALUES ($1, $2, now())"
    try:
        await Database.execute(sql, account_id, payment_id)
    except UniqueViolationError:
        sql = f"UPDATE yoomoney SET payment_id=$1, time=now() WHERE account_id={account_id}"
        await Database.execute(sql, payment_id)


async def check_payment(account_id: int) -> Optional[str]:
    """Проверяет транзакцию yoomoney и возвращает ее статус оплаты"""

    payment = await get_payment(account_id)
    if payment is None:
        return None

    return Payment.find_one(payment.id).status


async def get_payment(account_id: int) -> Optional[YPayment]:
    """Возвращает сохраненный платеж"""

    sql = f"SELECT payment_id, time FROM yoomoney WHERE account_id={account_id}"
    data: Optional[dict] = await Database.fetch_row(sql)
    if not data:
        return

    return YPayment.from_json(data)


async def delete_payment(account_id: int):
    """Удаляет платеж, если он завершился"""

    sql = f"DELETE FROM yoomoney WHERE account_id={account_id}"
    await Database.execute(sql)
