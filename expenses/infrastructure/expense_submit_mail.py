"""Почта по заявкам на расход: черновик (create) и поступление на согласование (submit)."""

from __future__ import annotations

import html
import logging
from datetime import date, datetime
from decimal import Decimal
from email.message import EmailMessage
from typing import TYPE_CHECKING, Literal
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import aiosmtplib

if TYPE_CHECKING:
    from infrastructure.config import Settings

_log = logging.getLogger(__name__)


def _smtp_ready(settings: Settings) -> bool:
    return bool(
        (settings.smtp_host or "").strip()
        and (settings.smtp_user or "").strip()
        and (settings.smtp_password or "").strip()
    )


def _smtp_missing_env_names(settings: Settings) -> list[str]:
    """Имена переменных (без секретов) — для логов, если письмо не уходит."""
    out: list[str] = []
    if not (settings.smtp_host or "").strip():
        out.append("EXPENSE_SMTP_HOST")
    if not (settings.smtp_user or "").strip():
        out.append("EXPENSE_SMTP_USER")
    if not (settings.smtp_password or "").strip():
        out.append("EXPENSE_SMTP_PASSWORD")
    return out


def _parse_recipients(raw: str) -> list[str]:
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


def _format_date(d: date | datetime | None) -> str:
    if d is None:
        return "—"
    if isinstance(d, datetime):
        return d.date().isoformat()
    return d.isoformat()


def _format_money(amount: Decimal | None) -> str:
    if amount is None:
        return "—"
    return f"{amount.quantize(Decimal('0.01')):,.2f}".replace(",", " ")


def _build_open_link(settings: Settings, expense_id: str) -> str | None:
    base = (settings.frontend_url or "").strip().rstrip("/")
    if not base:
        return None
    try:
        return settings.expense_notify_link_template.format(
            frontend_url=base,
            expense_id=expense_id,
        )
    except (KeyError, ValueError) as e:
        _log.warning("EXPENSE_NOTIFY_LINK_TEMPLATE invalid: %s", e)
        return f"{base}/expenses/{expense_id}"


def append_url_intent(url: str, param: str, value: str) -> str:
    """Добавляет query-параметр; для URL с # — в fragment (hash-router)."""
    url = (url or "").strip()
    if not url:
        return url
    u = urlparse(url)
    frag = u.fragment or ""
    if frag:
        sep = "&" if "?" in frag else "?"
        new_frag = f"{frag}{sep}{param}={value}"
        return urlunparse((u.scheme, u.netloc, u.path, u.params, u.query, new_frag))
    qs = parse_qs(u.query, keep_blank_values=True)
    qs[param] = [value]
    new_q = urlencode(qs, doseq=True)
    return urlunparse((u.scheme, u.netloc, u.path, u.params, new_q, u.fragment))


def _button_block_html(href: str, label: str, bg_hex: str) -> str:
    safe_href = html.escape(href, quote=True)
    safe_label = html.escape(label)
    return f"""
<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 10px 0;">
  <tr>
    <td align="left" style="border-radius:8px;background:{bg_hex};">
      <a href="{safe_href}" target="_blank" rel="noopener noreferrer"
         style="display:inline-block;padding:14px 28px;font-family:Segoe UI,Arial,sans-serif;font-size:15px;line-height:1.2;color:#ffffff !important;text-decoration:none;font-weight:600;border-radius:8px;background:{bg_hex};">
        {safe_label}
      </a>
    </td>
  </tr>
</table>"""


def _build_interactive_html(
    *,
    stage: Literal["draft", "submitted"],
    safe_id: str,
    safe_author: str,
    expense_date_fmt: str,
    safe_et: str,
    money_fmt: str,
    reimb: str,
    safe_desc: str,
    open_link: str | None,
    intent_param: str,
) -> str:
    if stage == "submitted":
        badge_upper = "На согласование"
        extra_line = (
            '<p style="margin:12px 0 0 0;font-size:15px;color:#64748b;line-height:1.45;">'
            "Требуется решение модератора.</p>"
        )
    else:
        badge_upper = "Черновик"
        extra_line = (
            '<p style="margin:12px 0 0 0;font-size:15px;color:#64748b;line-height:1.45;">'
            "Автор создал заявку. После отправки на согласование придёт ещё одно письмо с кнопками «Утвердить» и «Отклонить».</p>"
        )

    if open_link:
        safe_open = html.escape(open_link, quote=True)
        if stage == "submitted":
            approve_url = append_url_intent(open_link, intent_param, "approve")
            reject_url = append_url_intent(open_link, intent_param, "reject")
            actions_block = f"""
<div style="margin:24px 0;padding:20px 20px 8px 20px;background:#eef2ff;border-radius:12px;border:1px solid #c7d2fe;">
  <p style="margin:0 0 16px 0;font-family:Segoe UI,Arial,sans-serif;font-size:15px;color:#1e1b4b;font-weight:600;">
    Действия (откройте в браузере, войдите в систему при необходимости)
  </p>
  {_button_block_html(open_link, "Открыть заявку", "#2563eb")}
  {_button_block_html(approve_url, "Утвердить", "#16a34a")}
  {_button_block_html(reject_url, "Отклонить", "#dc2626")}
  <p style="margin:12px 0 0 0;font-family:Segoe UI,Arial,sans-serif;font-size:12px;color:#64748b;line-height:1.4;">
    «Утвердить» и «Отклонить» добавляют параметр <code style="background:#f1f5f9;padding:2px 6px;border-radius:4px;">{html.escape(intent_param)}</code>
    — фронтенд может открыть диалог согласования.
  </p>
  <p style="margin:8px 0 0 0;font-family:Segoe UI,Arial,sans-serif;font-size:12px;color:#94a3b8;">
    Если кнопки не нажимаются: <a href="{safe_open}" style="color:#2563eb;">ссылка на заявку</a>
  </p>
</div>"""
        else:
            actions_block = f"""
<div style="margin:24px 0;padding:20px 20px 8px 20px;background:#f0fdf4;border-radius:12px;border:1px solid #bbf7d0;">
  <p style="margin:0 0 16px 0;font-family:Segoe UI,Arial,sans-serif;font-size:15px;color:#14532d;font-weight:600;">
    Просмотр черновика
  </p>
  {_button_block_html(open_link, "Открыть заявку", "#2563eb")}
  <p style="margin:12px 0 0 0;font-family:Segoe UI,Arial,sans-serif;font-size:12px;color:#64748b;line-height:1.4;">
    Утвердить или отклонить можно после того, как автор отправит заявку на согласование.
  </p>
  <p style="margin:8px 0 0 0;font-family:Segoe UI,Arial,sans-serif;font-size:12px;color:#94a3b8;">
    <a href="{safe_open}" style="color:#2563eb;">Ссылка на заявку</a>
  </p>
</div>"""
    else:
        actions_block = """
<p style="font-family:Segoe UI,Arial,sans-serif;color:#64748b;">
  <em>Задайте FRONTEND_URL в env сервиса expenses — тогда в письме появятся кнопки.</em>
</p>"""

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<title>Заявка на расход {safe_id}</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f5;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f4f4f5;">
  <tr>
    <td align="center" style="padding:24px 16px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08);">
        <tr>
          <td style="padding:24px 24px 8px 24px;font-family:Segoe UI,Arial,sans-serif;">
            <p style="margin:0 0 8px 0;font-size:13px;color:#64748b;text-transform:uppercase;letter-spacing:.04em;">{html.escape(badge_upper)}</p>
            <h1 style="margin:0;font-size:22px;line-height:1.3;color:#0f172a;">Расход <span style="color:#2563eb;">{safe_id}</span></h1>
            {extra_line}
          </td>
        </tr>
        <tr>
          <td style="padding:8px 24px 24px 24px;font-family:Segoe UI,Arial,sans-serif;font-size:15px;line-height:1.55;color:#334155;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;">
              <tr><td style="padding:6px 0;border-bottom:1px solid #e2e8f0;"><strong>Автор</strong></td><td style="padding:6px 0;border-bottom:1px solid #e2e8f0;">{safe_author}</td></tr>
              <tr><td style="padding:6px 0;border-bottom:1px solid #e2e8f0;"><strong>Дата расхода</strong></td><td style="padding:6px 0;border-bottom:1px solid #e2e8f0;">{html.escape(expense_date_fmt)}</td></tr>
              <tr><td style="padding:6px 0;border-bottom:1px solid #e2e8f0;"><strong>Тип</strong></td><td style="padding:6px 0;border-bottom:1px solid #e2e8f0;">{safe_et}</td></tr>
              <tr><td style="padding:6px 0;border-bottom:1px solid #e2e8f0;"><strong>Сумма (UZS)</strong></td><td style="padding:6px 0;border-bottom:1px solid #e2e8f0;">{html.escape(money_fmt)}</td></tr>
              <tr><td style="padding:6px 0;border-bottom:1px solid #e2e8f0;"><strong>Возмещаемый</strong></td><td style="padding:6px 0;border-bottom:1px solid #e2e8f0;">{html.escape(reimb)}</td></tr>
              <tr><td style="padding:6px 0;vertical-align:top;"><strong>Описание</strong></td><td style="padding:6px 0;">{safe_desc}</td></tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:0 24px 24px 24px;">
            {actions_block}
          </td>
        </tr>
        <tr>
          <td style="padding:16px 24px;background:#f8fafc;border-top:1px solid #e2e8f0;font-family:Segoe UI,Arial,sans-serif;font-size:12px;color:#94a3b8;">
            Письмо отправлено автоматически сервисом расходов Kosta Legal.
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>"""


async def _send_moderation_message(
    settings: Settings,
    *,
    stage: Literal["draft", "submitted"],
    expense_id: str,
    description: str | None,
    amount_uzs: Decimal | None,
    expense_date: date | datetime | None,
    expense_type: str | None,
    is_reimbursable: bool,
    author_email: str | None,
    author_name: str | None,
) -> None:
    if stage == "draft":
        if not settings.expense_notify_on_create:
            _log.debug("expense notify: EXPENSE_NOTIFY_ON_CREATE=false, skip")
            return
    elif not settings.expense_notify_on_submit:
        _log.debug("expense notify: EXPENSE_NOTIFY_ON_SUBMIT=false, skip")
        return

    if not _smtp_ready(settings):
        missing = _smtp_missing_env_names(settings)
        _log.warning(
            "expense notify: в контейнере/процессе expenses не заданы переменные %s — письмо не отправлено. "
            "Для Docker: задайте их в .env у корня compose и передавайте в сервис expenses (см. docker-compose.yml), "
            "либо env_file. Текущий EXPENSE_SMTP_HOST=%r (пустой=%s)",
            ", ".join(missing) if missing else "(неизвестно)",
            (settings.smtp_host or "")[:80],
            not bool((settings.smtp_host or "").strip()),
        )
        return
    recipients = _parse_recipients(settings.expense_notify_to)
    if not recipients:
        _log.warning("expense notify: EXPENSE_NOTIFY_TO пусто, skip")
        return

    author_line = (author_name or "").strip() or "—"
    if author_email:
        author_line = f"{author_line} ({author_email})" if author_line != "—" else author_email

    reimb = "да" if is_reimbursable else "нет"
    desc = (description or "").strip() or "—"
    et = (expense_type or "").strip() or "—"
    safe_desc = html.escape(desc)
    safe_et = html.escape(et)
    safe_author = html.escape(author_line)
    safe_id = html.escape(expense_id)
    expense_date_fmt = _format_date(expense_date)
    money_fmt = _format_money(amount_uzs)

    open_link = _build_open_link(settings, expense_id)
    link_plain = open_link or "(задайте FRONTEND_URL в env сервиса expenses)"
    intent_param = (settings.expense_notify_intent_param or "intent").strip() or "intent"

    if stage == "draft":
        subject = f"Заявка на расход {expense_id} — черновик"
        plain_lines = [
            f"Создан черновик заявки: {expense_id}",
            f"Автор: {author_line}",
            f"Дата расхода: {expense_date_fmt}",
            f"Тип: {et}",
            f"Сумма (UZS): {money_fmt}",
            f"Возмещаемый: {reimb}",
            f"Описание: {desc}",
            "",
            "Открыть заявку:",
            link_plain,
            "",
            "После отправки автором на согласование вы получите письмо с действиями «Утвердить» / «Отклонить».",
            "",
            "— Kosta Legal / расходы",
        ]
    else:
        subject = f"Заявка на расход {expense_id} — на согласование"
        plain_lines = [
            f"Заявка на согласование: {expense_id}",
            f"Автор: {author_line}",
            f"Дата расхода: {expense_date_fmt}",
            f"Тип: {et}",
            f"Сумма (UZS): {money_fmt}",
            f"Возмещаемый: {reimb}",
            f"Описание: {desc}",
            "",
            "Ссылки (нужен вход в приложение, роль модерации):",
            f"Открыть: {link_plain}",
        ]
        if open_link:
            plain_lines.extend(
                [
                    f"Утвердить ({intent_param}=approve): {append_url_intent(open_link, intent_param, 'approve')}",
                    f"Отклонить ({intent_param}=reject): {append_url_intent(open_link, intent_param, 'reject')}",
                ]
            )
        plain_lines.extend(["", "— Kosta Legal / расходы"])

    text_body = "\n".join(plain_lines)

    html_body = _build_interactive_html(
        stage=stage,
        safe_id=safe_id,
        safe_author=safe_author,
        expense_date_fmt=expense_date_fmt,
        safe_et=safe_et,
        money_fmt=money_fmt,
        reimb=reimb,
        safe_desc=safe_desc,
        open_link=open_link,
        intent_param=intent_param,
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    from_addr = (settings.expense_mail_from or settings.smtp_user or "").strip()
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    _log.info(
        "expense notify: отправка SMTP stage=%s expense_id=%s to=%s host=%s",
        stage,
        expense_id,
        recipients,
        settings.smtp_host.strip(),
    )
    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host.strip(),
            port=int(settings.smtp_port),
            username=settings.smtp_user.strip(),
            password=settings.smtp_password,
            start_tls=bool(settings.smtp_use_tls),
        )
    except Exception as e:
        _log.error(
            "expense notify: ошибка SMTP stage=%s expense_id=%s: %s: %s",
            stage,
            expense_id,
            type(e).__name__,
            e,
        )
        raise
    _log.info(
        "expense moderation mail (%s) sent to %s expense_id=%s",
        stage,
        recipients,
        expense_id,
    )


async def notify_expense_created(
    settings: Settings,
    *,
    expense_id: str,
    description: str | None,
    amount_uzs: Decimal | None,
    expense_date: date | datetime | None,
    expense_type: str | None,
    is_reimbursable: bool,
    author_email: str | None,
    author_name: str | None,
) -> None:
    """Письмо модераторам при POST /expenses (черновик)."""
    await _send_moderation_message(
        settings,
        stage="draft",
        expense_id=expense_id,
        description=description,
        amount_uzs=amount_uzs,
        expense_date=expense_date,
        expense_type=expense_type,
        is_reimbursable=is_reimbursable,
        author_email=author_email,
        author_name=author_name,
    )


async def notify_expense_submitted(
    settings: Settings,
    *,
    expense_id: str,
    description: str | None,
    amount_uzs: Decimal | None,
    expense_date: date | datetime | None,
    expense_type: str | None,
    is_reimbursable: bool,
    author_email: str | None,
    author_name: str | None,
) -> None:
    """Письмо модераторам при отправке на согласование (submit → pending_approval)."""
    await _send_moderation_message(
        settings,
        stage="submitted",
        expense_id=expense_id,
        description=description,
        amount_uzs=amount_uzs,
        expense_date=expense_date,
        expense_type=expense_type,
        is_reimbursable=is_reimbursable,
        author_email=author_email,
        author_name=author_name,
    )


async def send_expense_smtp_test(settings: Settings) -> list[str]:
    """Тест SMTP: письмо «на согласование» с полным набором кнопок."""
    if not _smtp_ready(settings):
        raise ValueError("Задайте EXPENSE_SMTP_HOST, EXPENSE_SMTP_USER, EXPENSE_SMTP_PASSWORD")
    recipients = _parse_recipients(settings.expense_notify_to)
    if not recipients:
        raise ValueError("EXPENSE_NOTIFY_TO пусто")

    intent_param = (settings.expense_notify_intent_param or "intent").strip() or "intent"
    open_link = _build_open_link(settings, "TEST-EXPENSE")
    safe_id = html.escape("TEST-EXPENSE")
    html_body = _build_interactive_html(
        stage="submitted",
        safe_id=safe_id,
        safe_author=html.escape("Тестовый автор (SMTP)"),
        expense_date_fmt="2099-01-01",
        safe_et=html.escape("office"),
        money_fmt="1 234 567.89",
        reimb="да",
        safe_desc=html.escape("Это тестовое письмо: проверка кнопок и вёрстки."),
        open_link=open_link,
        intent_param=intent_param,
    )
    link_plain = open_link or "(задайте FRONTEND_URL)"
    plain = "\n".join(
        [
            "[Тест] Проверка SMTP и интерактивного письма.",
            "",
            f"Открыть: {link_plain}",
        ]
        + (
            [
                f"Утвердить: {append_url_intent(open_link, intent_param, 'approve')}",
                f"Отклонить: {append_url_intent(open_link, intent_param, 'reject')}",
            ]
            if open_link
            else []
        )
    )

    msg = EmailMessage()
    msg["Subject"] = "[Тест] Kosta Legal — расходы, SMTP + кнопки"
    from_addr = (settings.expense_mail_from or settings.smtp_user or "").strip()
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients)
    msg.set_content(plain)
    msg.add_alternative(html_body, subtype="html")

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host.strip(),
        port=int(settings.smtp_port),
        username=settings.smtp_user.strip(),
        password=settings.smtp_password,
        start_tls=bool(settings.smtp_use_tls),
    )
    _log.info("expense SMTP test sent to %s", recipients)
    return recipients
