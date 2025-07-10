import orjson

from mg.config import db_config

from typing import List, Any, Union, Dict
from asyncpg import Pool, Record, create_pool
from datetime import date, time, datetime, timedelta


INTEGER_TYPE = Union[int, float]
DATETIME_TYPE = Union[date, time, datetime, timedelta]
JSON_TYPE = Union[Dict[str, Any], List[Any]]
SQL_TYPE = Union[INTEGER_TYPE, DATETIME_TYPE, JSON_TYPE, bool, bytes, str]


class Database:
    pool: Pool = None

    @classmethod
    async def init(cls):
        cls.pool = await create_pool(min_size=3, **db_config)

    @classmethod
    async def execute(cls, sql: str, *params):
        """
        Выполняет SQL-запрос и ничего не возвращает

        :param sql: SQL-запрос
        :param params: дополнительные параметры запроса
        """

        await cls.pool.execute(sql, *params)

    @classmethod
    async def fetch_all(cls, sql: str, *params) -> List[Dict[str, SQL_TYPE]]:
        """
        Выполняет SQL-запрос и возвращает список строк

        :param sql: SQL-запрос
        :param params: дополнительные параметры запроса
        :return: список словарей со строковым ключем (название столбца) и объектами SQL-типа
        """

        data = await cls.pool.fetch(sql, *params)

        return cls.deserialize(data)

    @classmethod
    async def fetch_all_for_one(cls, sql: str, *params) -> List[SQL_TYPE]:
        """
        Выполняет SQL-запрос и возвращает список из одного результата каждого запроса

        :param sql: SQL-запрос
        :param params: дополнительные параметры запроса
        :return: список из одного результата каждого запроса
        """

        data = await cls.pool.fetch(sql, *params)

        return [cls.deserialize(line, one=True) for line in data]

    @classmethod
    async def fetch_row(cls, sql: str, *params) -> Dict[str, SQL_TYPE]:
        """
        Выполняет SQL-запрос и возвращает одну строку ответа

        :param sql: SQL-запрос
        :param params: дополнительные параметры запроса
        :return: словарь со строковым ключем (название столбца) и объекта SQL-типа
        """

        data = await cls.pool.fetchrow(sql, *params)

        return cls.deserialize(data)

    @classmethod
    async def fetch_row_for_one(cls, sql: str, *params) -> SQL_TYPE:
        """
        Выполняет SQL-запрос и возвращает один результат одной строки ответа

        :param sql: SQL-запрос
        :param params: дополнительные параметры запроса
        :return: объект SQL-типа
        """

        data = await cls.pool.fetchrow(sql, *params)

        return cls.deserialize(data, one=True)

    @classmethod
    def deserialize(cls, data, one: bool = False):
        """
        Десериализует данные в JSON-формат

        :param data: данные для десериализации
        :param one: True, если необходимо из списка/словаря длиной 1 вытащить единственное значение, иначе False
        """

        if isinstance(data, list):
            result = [cls.deserialize(item, one=False) for item in data]
        elif isinstance(data, Record):
            result = {key: cls.deserialize(data[key], one=False) for key in data.keys()}
        else:
            try:
                result = orjson.loads(data)  # Если строка JSON-формата, то десериализуем
            except (TypeError, orjson.JSONDecodeError):
                return data

        if not one:
            return result  # Возвращаем весь объект

        if isinstance(result, list):
            if len(result) > 1:
                raise ValueError("Количество объектов в списке больше одного")
            return result[0]

        if isinstance(result, dict):
            if len(result) > 1:
                raise ValueError("Количество объектов в словаре больше одного")
            return list(result.values())[0]

        return result  # Объект нелинейный, возвращаем его целым

    @classmethod
    def serialize(cls, data: JSON_TYPE) -> str:
        """Сериализует словарь или список в JSON-строку"""

        return orjson.dumps(data).decode()
