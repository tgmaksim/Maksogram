from mg.config import OWNER

from typing import Optional, Literal
from mg.core.database import Database
from asyncpg import UniqueViolationError

from aiogram.types import MessageEntity

from . types import SecuritySettings, SecurityAgent


MAX_COUNT_AGENTS = 3


async def is_security_agent(agent_id: int) -> bool:
    """Проверяет пользователя на присутствие в списке доверенных лиц одного из клиентов"""

    sql = f"SELECT true FROM security_agents WHERE agent_id={agent_id}"
    data: Optional[bool] = await Database.fetch_row_for_one(sql)

    return data is True


async def get_security_settings(account_id: int) -> SecuritySettings:
    """Возвращает полную информацию о настройках Защиты аккаунта у клиента"""

    # Подзапрос на получение доверенных лиц конвертируется в JSON-список и возвращается вместе с остальными данными
    sql = f"""SELECT 
                    security.security_hack,
                    security.security_no_access,
                    security.email,
                    COALESCE(
                        (SELECT jsonb_agg(
                            jsonb_build_object(
                                'account_id', security_agents.account_id,
                                'agent_id', security_agents.agent_id,
                                'name', security_agents.name,
                                'recovery', security_agents.recovery
                            )
                        ) FROM security_agents WHERE security_agents.account_id = {account_id}),
                        '[]'::jsonb
                    ) AS agents
               FROM security
               WHERE security.account_id = {account_id}"""

    data: dict = await Database.fetch_row(sql)

    return SecuritySettings.from_json(data)

def check_valid_email(text: str, entities: Optional[list[MessageEntity]]) -> bool:
    """Проверяет корректность email"""

    return entities and len(entities) == 1 and (entities[0].offset, entities[0].length) == (0, len(text)) and entities[0].type == "email"


async def update_email(account_id: int, email: str):
    """Изменяет почту Защиты аккаунта для клиента"""

    sql = f"UPDATE security SET email=$1 WHERE account_id={account_id}"
    await Database.execute(sql, email)


async def get_security_agents(account_id: int) -> list[SecurityAgent]:
    """Возвращает список доверенных лиц клиента"""

    sql = f"SELECT account_id, agent_id, name, recovery FROM security_agents WHERE account_id={account_id}"
    data: list[dict] = await Database.fetch_all(sql)

    agents = SecurityAgent.list_from_json(data)

    return sorted(agents, key=lambda agent: len(agent.name))


async def check_count_agents(account_id: int) -> bool:
    """Считает количество доверенных у клиента и возвращает возможность добавить еще одного"""

    if account_id == OWNER:
        return True

    sql = f"SELECT COUNT(*) FROM security_agents WHERE account_id={account_id}"
    data: int = await Database.fetch_row_for_one(sql)

    return data < MAX_COUNT_AGENTS


async def add_security_agent(account_id: int, agent_id: int, name: str) -> bool:
    """Добавляет доверенное лицо в список клиента, если пользовать уже является чьи-то доверенным лицом, то возвращает False, иначе True"""

    sql = "INSERT INTO security_agents (account_id, agent_id, name, recovery) VALUES ($1, $2, $3, false)"
    try:
        await Database.execute(sql, account_id, agent_id, name)
    except UniqueViolationError:
        return False

    return True


async def delete_security_agent(account_id: int, agent_id: int):
    """Удаляет доверенное лицо из списка у клиента"""

    sql = f"DELETE FROM security_agents WHERE account_id={account_id} AND agent_id={agent_id}"
    await Database.execute(sql)


async def set_security_function(account_id: int, function: Literal["hack", "no_access"], command: bool):
    """Включает/выключает функцию Защиты аккаунта (для no_access отключает режим восстановления для доверенных лиц)"""

    if function == "no_access" and not command:
        await stop_recovery(account_id)

    sql = f"UPDATE security SET security_{function}={command} WHERE account_id={account_id}"
    await Database.execute(sql)


async def stop_recovery(account_id: int):
    """Отключает восстановление у всех доверенных лиц клиента"""

    sql = f"UPDATE security_agents SET recovery=false WHERE account_id={account_id}"
    await Database.execute(sql)


async def get_security_agent(agent_id: int) -> SecurityAgent:
    """Возвращает агента по идентификатору"""

    sql = f"SELECT account_id, agent_id, name, recovery FROM security_agents WHERE agent_id={agent_id}"
    data: dict = await Database.fetch_row(sql)

    return SecurityAgent.from_json(data)


async def set_recovery(agent_id: int, recovery: bool):
    """Включает/выключает восстановление аккаунта у доверенного лица"""

    sql = f"UPDATE security_agents SET recovery={recovery} WHERE agent_id={agent_id}"
    await Database.execute(sql)


async def enabled_security_hack(account_id: int) -> bool:
    """Проверяет статус Защиты аккаунта от взлома у клиента"""

    sql = f"SELECT security_hack FROM security WHERE account_id={account_id}"
    data: bool = await Database.fetch_row_for_one(sql)

    return data
