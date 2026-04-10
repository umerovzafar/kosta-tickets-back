from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


_REPORT_VISIBILITY = frozenset({"managers_only", "all_assigned"})
_PROJECT_TYPES = frozenset({"time_and_materials", "fixed_fee", "non_billable"})


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _strip_opt(v: str | None) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _decimal_none(v: Any) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _to_decimal(v: Any) -> Decimal:
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))
