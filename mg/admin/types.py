from dataclasses import dataclass


@dataclass
class AccountWithStatus:
    account_id: int
    is_started: bool
