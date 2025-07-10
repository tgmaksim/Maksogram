from typing import Optional


class SecurityAgent:
    def __init__(self, account_id: int, agent_id: int, name: str, recovery: bool):
        self.account_id = account_id
        self.id = agent_id
        self.name = name
        self.recover = recovery

    @classmethod
    def from_json(cls, json_data: dict) -> 'SecurityAgent':
        return cls(
            account_id=json_data['account_id'],
            agent_id=json_data['agent_id'],
            name=str(json_data['name']),
            recovery=json_data['recovery']
        )

    @classmethod
    def list_from_json(cls, json_data: list[dict]) -> list['SecurityAgent']:
        return [cls.from_json(data) for data in json_data]


class SecuritySettings:
    def __init__(self, security_hack: bool, security_no_access: bool, email: Optional[str], agents: list[SecurityAgent]):
        self.security_hack = security_hack
        self.security_no_access = security_no_access
        self.email = email
        self.agents = agents

    @classmethod
    def from_json(cls, json_data: dict) -> 'SecuritySettings':
        return cls(
            security_hack=json_data['security_hack'],
            security_no_access=json_data['security_no_access'],
            email=json_data['email'],
            agents=SecurityAgent.list_from_json(json_data['agents'])
        )
