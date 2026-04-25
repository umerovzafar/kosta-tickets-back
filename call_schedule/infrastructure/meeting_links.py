"""Извлечение и нормализация ссылок на звонок (Zoom, Teams, Meet, …) из события Graph."""

from __future__ import annotations

import re
from typing import Any

_HTTPS_RE = re.compile(
    r"https://[^\s<>\"']+",
    re.IGNORECASE,
)
# Ссылки в атрибуте href, пока теги ещё не убрали
_HREF_RE = re.compile(
    r"""href\s*=\s*["']?(https://[^"'>\s]+)""",
    re.IGNORECASE,
)


def _strip_htmlish(text: str) -> str:
    if not text:
        return ""
    t = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    t = re.sub(r"</p\s*>", "\n", t, flags=re.IGNORECASE)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ")
    t = t.replace("&#160;", " ")
    t = t.replace("&amp;", "&")
    t = t.replace("&#58;", ":")
    return t


def event_meeting_urls_from_body_object(ev: dict[str, Any]) -> list[str]:
    """URL из `body.content` (сырой HTML/текст, чтобы не терять href=…)."""
    b = ev.get("body")
    if isinstance(b, dict):
        c = b.get("content")
        if isinstance(c, str) and c.strip():
            return extract_https_urls(c)
    return extract_https_urls(event_body_text(ev))


def event_body_text(ev: dict[str, Any]) -> str:
    """Текст из body (HTML/текст) и запас bodyPreview."""
    b = ev.get("body")
    if isinstance(b, dict):
        raw = b.get("content")
        if isinstance(raw, str) and raw.strip():
            if (b.get("contentType") or "").lower() == "html":
                return _strip_htmlish(raw)
            return raw
    prev = ev.get("bodyPreview")
    if isinstance(prev, str) and prev.strip():
        return prev
    return ""


def extract_https_urls(text: str) -> list[str]:
    if not text or not str(text).strip():
        return []
    raw = str(text)
    found = list(_HREF_RE.findall(raw)) + _HTTPS_RE.findall(raw)
    out: list[str] = []
    seen: set[str] = set()
    for u in found:
        u = u.rstrip(").,;]")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def classify_meeting_url(url: str) -> str:
    u = (url or "").lower()
    if "zoom.us" in u or "zoom.com" in u:
        return "zoom"
    if "teams.microsoft" in u or "teams.live" in u or "teams.google" in u:
        return "teams"
    if "meet.google" in u:
        return "meet"
    if "webex" in u:
        return "webex"
    if "gotomeeting" in u or "global.gotowebinar" in u:
        return "goto"
    if "whereby" in u or "daily.co" in u or "meet.jit.si" in u:
        return "webrtc"
    return "other"


def build_meeting_link_objects(urls: list[str]) -> list[dict[str, str]]:
    return [
        {
            "url": u,
            "kind": classify_meeting_url(u),
        }
        for u in urls
    ]
