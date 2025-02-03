import json

from typing import Union, Any
from asyncpg import Connection, Record, connect

from sys_keys import db_config


class Database:
    def __init__(self):
        self.__connection: Union[Connection, None] = None

    async def connect(self):
        self.__connection = await connect(**db_config)

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.__connection.close()

    def serialize(self, data) -> Union[int, str, float, list, dict]:
        if isinstance(data, list):
            return [self.serialize(item) for item in data]
        if isinstance(data, Record):
            return {key: self.serialize(data[key]) for key in data.keys()}
        try:
            return json.loads(data)
        except (TypeError, json.JSONDecodeError):
            return data

    async def execute(self, sql: str, *params):
        await self.__connection.execute(sql, *params)

    async def fetch_all(self, sql: str, *params, one_data: bool = False) -> Union[list[dict], list]:
        if not one_data:
            return self.serialize(await self.__connection.fetch(sql, *params))
        return list(map(lambda x: x.items().__iter__().__next__()[1], self.serialize(await self.__connection.fetch(sql, *params))))

    async def fetch_one(self, sql: str, *params, one_data: bool = False) -> Union[dict, Any]:
        if not one_data:
            return self.serialize(await self.__connection.fetchrow(sql, *params))
        return self.serialize(await self.__connection.fetchrow(sql, *params) or {0: None}).items().__iter__().__next__()[1]
