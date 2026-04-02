"""Загрузка профилей пользователей из auth для отображения автора заявки."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

_log = logging.getLogger(__name__)
_MAX_CONCURRENT = 12


async def fetch_users_by_ids(
    auth_base_url: str,
    authorization: Optional[str],
    user_ids: set[int],
) -> dict[int, dict]:
    """
    GET {auth}/users/{id} для каждого уникального id (параллельно, с лимитом).
    Возвращает словарь id -> тело ответа auth (snake_case полей).
    """
    if not authorization or not user_ids:
        return {}
    base = auth_base_url.rstrip("/")
    sem = asyncio.Semaphore(_MAX_CONCURRENT)

    async def one(uid: int) -> tuple[int, dict | None]:
        async with sem:
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    r = await client.get(
                        f"{base}/users/{uid}",
                        headers={"Authorization": authorization},
                    )
                if r.status_code == 200:
                    return uid, r.json()
                _log.debug("auth users/%s status=%s", uid, r.status_code)
            except httpx.RequestError as e:
                _log.debug("auth users/%s err=%s", uid, e)
            return uid, None

    pairs = await asyncio.gather(*(one(uid) for uid in user_ids))
    out: dict[int, dict] = {}
    for uid, data in pairs:
        if data is not None:
            out[uid] = data
    return out
