import time
import asyncio

from sqlite3 import connect
from typing import Union, Iterable
from sys_keys import sessions_path
from telethon import TelegramClient
from aiogram.types import MessageEntity
from datetime import datetime, timedelta
from core import time_now, new_telegram_client, json_decode, json_encode, resources_path, db

accounts: dict[int, 'Account'] = {}


class UserIsNotAuthorized(Exception):
    pass


class Account:
    def __init__(
            self,
            name: str,
            id: Union[int, str],
            phone_number: str,
            my_messages: Union[int, str],
            message_changes: Union[int, str],
            added_chats: list[Union[int, str], ...],
            removed_chats: list[Union[int, str], ...],
            status_users: list[Union[int, str], ...],
            is_started: str,
            payment: dict[str, str],
            is_paid: str,
            answering_machine: dict[str, Union[int, dict[int, dict[str, Union[str, list[dict]]]]]],
    ):
        self.name: str = name
        self.id: int = int(id)
        self.phone_number: str = phone_number
        self.my_messages: int = int(my_messages)
        self.message_changes: int = int(message_changes)
        self.added_chats: list[int] = list(map(int, added_chats))
        self.removed_chats: list[int] = list(map(int, removed_chats))
        self.status_users: list[int] = list(map(int, status_users))
        self.is_started: bool = bool(int(is_started))
        self.payment: Payment = Payment(datetime.strptime(payment['next_payment'], "%Y/%m/%d") if payment['next_payment'] else None, payment['user'], int(payment['fee']))
        self.is_paid: bool = bool(int(is_paid))
        self.answering_machine: AnsweringMachine = AnsweringMachine(answering_machine['main'], answering_machine['variants'])

        self.telegram_client: TelegramClient = new_telegram_client(phone_number)

        accounts[self.id] = self

    @staticmethod
    def get_accounts() -> list['Account']:
        with connect(resources_path("db.sqlite3")) as conn:
            cur = conn.cursor()
            cur.execute("SELECT name, id, phone_number, my_messages, message_changes, added_chats, removed_chats, "
                        "status_users, is_started, payment, is_paid, answering_machine FROM accounts")
        return [Account(d0, d1, d2, d3, d4, json_decode(d5), json_decode(d6), json_decode(d7), d8, json_decode(d9), d10,
                        json_decode(d11)) for d0, d1, d2, d3, d4, d5, d6, d7, d8, d9, d10, d11 in cur.fetchall()]

    def get_session_path(self) -> str:
        return sessions_path(self.phone_number)

    async def execute(self, sql: str, params: tuple = ()) -> tuple[tuple[Union[str, int]]]:
        return await db.execute(sql.replace("<table>", f"'{self.id}_messages'"), params)

    async def insert_new_message(self, chat_id: int, message_id: int, saved_message_id: int, is_read: int):
        # is_read: -1 (от меня), -2 (от другого), 0 - в группе, 1 (прочитано)
        await self.execute("INSERT INTO <table> VALUES (?, ?, ?, ?, ?)", (chat_id, message_id, saved_message_id, is_read, ""))

    async def get_last_reactions(self, chat_id: int, message_id: int) -> Union[str, None]:
        r = await self.execute("SELECT reactions FROM <table> WHERE chat_id=? AND message_id=?", (chat_id, message_id))
        if not r:
            return
        return r[0][0]

    async def get_saved_message_id(self, chat_id: int, message_id: int) -> Union[int, None]:
        r = await self.execute("SELECT saved_message_id FROM <table> WHERE chat_id=? AND message_id=?", (chat_id, message_id))
        if not r:
            return
        return int(r[0][0])

    async def update_reactions(self, reactions: str, chat_id: int, message_id: int):
        await self.execute("UPDATE <table> SET reactions=? WHERE chat_id=? AND message_id=?", (reactions, chat_id, message_id))

    async def get_private_message_by_id(self, message_id: int) -> Union[tuple[int, int], None]:
        r = await self.execute("SELECT chat_id, saved_message_id FROM <table> WHERE message_id=? AND chat_id>?",
                               (message_id, -10000000000))
        if not r:
            return
        return tuple(map(int, r[0]))

    async def delete_message(self, saved_message_id: int):
        await self.execute("DELETE FROM <table> WHERE saved_message_id=?", (saved_message_id,))

    async def get_read_messages(self, chat_id: int, max_id: int, is_read: int) -> Union[tuple[int, ...], None]:
        r = await self.execute("SELECT saved_message_id FROM <table> WHERE is_read=? AND chat_id=? AND message_id<=?",
                               (is_read, chat_id, max_id))
        if not r:
            return
        await self.execute("UPDATE <table> SET is_read=? WHERE chat_id=? AND message_id<=?", (1, chat_id, max_id))
        return tuple(map(lambda x: int(x[0]), r))

    async def create_table(self):
        await self.execute("CREATE TABLE IF NOT EXISTS <table> (chat_id INTEGER, message_id INTEGER, "
                           "saved_message_id INTEGER, is_read INTEGER, reactions TEXT)")

    async def off(self):
        await db.execute("UPDATE accounts SET is_started=? WHERE id=?", (0, self.id))
        self.is_started = False
        telegram_client, self.telegram_client = self.telegram_client, new_telegram_client(self.phone_number)
        if telegram_client.is_connected():
            await telegram_client.disconnect()

    async def on(self, Program):
        if not self.telegram_client.is_connected():
            await self.telegram_client.connect()
        if await self.telegram_client.is_user_authorized():
            await db.execute("UPDATE accounts SET is_started=? WHERE id=?", (1, self.id))
            self.is_started = True
            asyncio.get_running_loop().create_task(Program(self.telegram_client, self.id).run_until_disconnected())
        else:
            raise UserIsNotAuthorized()

    async def remove_status_user(self, user_id: int) -> int:
        try:
            self.status_users.remove(user_id)
        except ValueError:
            return 1
        else:
            await db.execute("UPDATE accounts SET status_users=? WHERE id=?", (json_encode(self.status_users), self.id))

    async def add_status_users(self, user_id: int) -> int:
        if user_id == self.id:
            return 1
        if user_id in self.status_users:
            return 2
        self.status_users.append(user_id)
        await db.execute("UPDATE accounts SET status_users=? WHERE id=?", (json_encode(self.status_users), self.id))

    async def set_status_payment(self, is_paid: bool, next_payment: Union[datetime, timedelta, None] = None):
        await db.execute("UPDATE accounts SET is_paid=? WHERE id=?", (int(is_paid), self.id))
        self.is_paid = is_paid
        if isinstance(next_payment, timedelta):
            next_payment = max(self.payment.next_payment, time_now()) + next_payment
        if isinstance(next_payment, datetime):
            self.payment.next_payment = next_payment
            await self.execute("UPDATE accounts SET payment=? WHERE id=?", (json_encode(self.payment.dict()), self.id))


class Payment:
    def __init__(self, net_payment: datetime, user: str, fee: int):
        self.next_payment = net_payment
        self.user = user
        self.fee = fee

    def dict(self) -> dict:
        return {
            'next_payment': self.next_payment.strftime("%Y/%m/%d"),
            'user': self.user,
            'fee': self.fee
        }


class AnsweringMachine:
    class Answer:
        def __init__(self, id: int, text: str, entities: Iterable[dict[str, Union[int, str, None]]]):
            self.id = id
            self.text = text
            self.entities = [MessageEntity(**entity) for entity in entities]

        def dict(self) -> dict[str, Union[str, list[dict]]]:
            return {"text": self.text, "entities": [entity.model_dump() for entity in self.entities]}

    def __init__(self, main: int, variants: dict[int, dict[str, Union[str, list[dict]]]]):
        self.main: int = main
        self.variants: dict[int, AnsweringMachine.Answer] = {int(id): self.Answer(id=int(id), **variants[id]) for id in variants}

    def append(self, text: str, entities: list[MessageEntity]):
        id = int(time.time()) - 1737828000  # 1737828000 - 2025/01/26 00:00 (день активного обновления автоответчика)
        self.variants[id] = self.Answer(id, text, map(lambda x: x.model_dump(), entities))

    def delete(self, answer_id: int):
        if self.main == answer_id:
            self.main = 0
        del self.variants[answer_id]

    def json(self) -> str:
        return json_encode({"main": self.main, "variants": {id: self.variants[id].dict() for id in self.variants}})

    def __getitem__(self, item: int) -> Union[Answer, None]:
        try:
            return self.variants[item]
        except KeyError:
            return

    def __iter__(self) -> 'AnsweringMachine':
        self.iter = self.variants.__iter__()
        return self

    def __next__(self) -> Answer:
        try:
            next_id_answer: int = self.iter.__next__()
        except (StopIteration, IndexError) as e:
            del self.iter
            raise e
        return self.variants[next_id_answer]

    def __len__(self) -> int:
        return self.variants.__len__()
