from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:
    id: int
    azure_oid: str
    email: str
    display_name: Optional[str]
    picture: Optional[str]
    role: str
    is_blocked: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime
