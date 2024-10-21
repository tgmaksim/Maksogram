import os
import core

from sqlite3 import connect
from typing import Union, Iterable
from json import JSONDecoder as json


class Account:
    accounts: dict[int, 'Account'] = {}

    def __init__(
            self,
            name: str,
            id: Union[int, str],
            password: Union[str, None],
            phone: str,
            my_messages: Union[int, str],
            message_changes: Union[int, str],
            channel_status_username: Union[int, str, None],
            message_status_id: Union[str, None],
            add_chats: Iterable[Union[int, str]],
            status_users: Iterable[Union[int, str]]
    ):
        self.name: str = name
        self.id: int = int(id)
        self.password: Union[str, None] = password
        self.phone: str = phone
        self.my_messages: int = int(my_messages)
        self.message_changes: int = int(message_changes)
        self.chanel_status_username: Union[str, None] = channel_status_username
        self.message_status_id: Union[int, None] = None if message_status_id is None else int(message_status_id)
        self.add_chats: list[int] = list(map(int, add_chats))
        self.status_users: list[int] = list(map(int, status_users))

        Account.accounts[self.id] = self

    @staticmethod
    def get_accounts() -> list['Account']:
        with connect(core.resources_path("db.sqlite3")) as conn:
            cur = conn.cursor()
            cur.execute("SELECT name, id, password, phone, my_messages, message_changes, "
                        "channel_status_username, message_status_id, add_chats, status_users FROM accounts")
            accounts = cur.fetchall()
        return [Account(d0, d1, d2, d3, d4, d5, d6, d7, json().decode(d8), json().decode(d9))
                for d0, d1, d2, d3, d4, d5, d6, d7, d8, d9 in accounts]

    def get_session_path(self) -> str:
        return os.path.join("sessions", self.phone)
