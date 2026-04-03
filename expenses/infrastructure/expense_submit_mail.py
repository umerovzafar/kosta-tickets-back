"""Почта по заявкам на расход: уведомление модераторам при отправке на согласование (submit)."""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote, urlparse, urlunparse, parse_qs, urlencode

import aiosmtplib

from infrastructure.expense_notify_routing import resolve_expense_notify_recipients

if TYPE_CHECKING:
    from infrastructure.config import Settings

_log = logging.getLogger(__name__)

_INLINE_IMAGE_MAX_BYTES = 2 * 1024 * 1024
_INLINE_IMAGE_MAX = 5


def _is_inline_image_mime(mt: str) -> bool:
    m = (mt or "").strip().lower()
    if m == "image/jpg":
        m = "image/jpeg"
    return m in {"image/jpeg", "image/png", "image/gif", "image/webp"}


@dataclass
class AttachmentEmailItem:
    id: str
    file_name: str
    storage_key: str
    mime_type: str | None
    size_bytes: int
    attachment_kind: str | None


@dataclass
class ExpenseModerationEmailContext:
    expense_id: str
    description: str | None
    expense_date: date | datetime | None
    payment_deadline: date | None
    amount_uzs: Decimal | None
    exchange_rate: Decimal | None
    equivalent_amount: Decimal | None
    expense_type: str | None
    expense_subtype: str | None
    is_reimbursable: bool
    payment_method: str | None
    department_id: str | None
    project_id: str | None
    vendor: str | None
    business_purpose: str | None
    comment: str | None
    author_email: str | None
    author_name: str | None
    attachments: list[AttachmentEmailItem]


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


def _smtp_ready(settings: Settings) -> bool:
    return bool(
        (settings.smtp_host or "").strip()
        and (settings.smtp_user or "").strip()
        and (settings.smtp_password or "").strip()
    )


def _smtp_missing_env_names(settings: Settings) -> list[str]:
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


def _format_rate(r: Decimal | None) -> str:
    if r is None:
        return "—"
    return f"{r.quantize(Decimal('0.000001')):,.6f}".replace(",", " ")


def _kind_label(k: str | None) -> str:
    if not k or not str(k).strip():
        return "—"
    m = {"payment_document": "Документ для оплаты", "payment_receipt": "Квитанция об оплате"}
    return m.get(str(k).strip(), str(k).strip())


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


def _button_row_html(href: str, label: str, bg: str) -> str:
    safe_href = html.escape(href, quote=True)
    safe_label = html.escape(label)
    return f"""
<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:0 0 12px 0;width:100%;max-width:320px;">
  <tr>
    <td align="center" style="border-radius:10px;background:{bg};">
      <a href="{safe_href}" target="_blank" rel="noopener noreferrer"
         style="display:block;padding:16px 24px;font-family:Segoe UI,Arial,sans-serif;font-size:16px;color:#ffffff !important;text-decoration:none;font-weight:700;border-radius:10px;">
        {safe_label}
      </a>
    </td>
  </tr>
</table>"""


def _detail_row(label: str, value_html: str) -> str:
    return f"""
<tr>
  <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;color:#64748b;font-size:14px;width:38%;vertical-align:top;">{html.escape(label)}</td>
  <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;color:#0f172a;font-size:14px;vertical-align:top;">{value_html}</td>
</tr>"""


def _build_moderation_html(
    *,
    ctx: ExpenseModerationEmailContext,
    safe_author: str,
    expense_date_fmt: str,
    money_fmt: str,
    reimb: str,
    safe_desc: str,
    safe_et: str,
    safe_sub: str,
    safe_vendor: str,
    safe_bp: str,
    safe_comment: str,
    dept: str,
    proj: str,
    pm: str,
    pd_fmt: str,
    rate_fmt: str,
    eq_fmt: str,
    open_link: str | None,
    actions_block: str,
    attachments_block: str,
) -> str:
    safe_id = html.escape(ctx.expense_id)
    footer_link_html = ""
    if open_link:
        footer_link_html = (
            f'<p style="margin:0 0 8px 0;"><a href="{html.escape(open_link, quote=True)}" '
            f'style="color:#2563eb;">Открыть заявку в веб-приложении</a> (по желанию).</p>'
        )
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Заявка {safe_id}</title>
</head>
<body style="margin:0;padding:0;background:#e2e8f0;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:linear-gradient(180deg,#1e3a8a 0%,#e2e8f0 220px);">
  <tr>
    <td align="center" style="padding:28px 12px 40px 12px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:640px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 20px 40px rgba(15,23,42,.12);">
        <tr>
          <td style="padding:28px 28px 20px 28px;background:linear-gradient(135deg,#1d4ed8 0%,#2563eb 50%,#3b82f6 100%);color:#fff;font-family:Segoe UI,Arial,sans-serif;">
            <p style="margin:0 0 6px 0;font-size:12px;letter-spacing:.12em;text-transform:uppercase;opacity:.9;">Согласование расхода</p>
            <h1 style="margin:0;font-size:26px;font-weight:700;letter-spacing:-.02em;">{safe_id}</h1>
            <p style="margin:12px 0 0 0;font-size:15px;opacity:.95;line-height:1.45;">Нужно решение модератора. Ниже — полные данные заявки и вложения.</p>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 28px 8px 28px;font-family:Segoe UI,Arial,sans-serif;">
            <p style="margin:0 0 12px 0;font-size:13px;font-weight:700;color:#0f172a;text-transform:uppercase;letter-spacing:.04em;">Автор и сроки</p>
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;background:#f8fafc;border-radius:12px;overflow:hidden;">
              {_detail_row("Автор", safe_author)}
              {_detail_row("Дата расхода", html.escape(expense_date_fmt))}
              {_detail_row("Срок оплаты", html.escape(pd_fmt))}
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 28px 8px 28px;font-family:Segoe UI,Arial,sans-serif;">
            <p style="margin:0 0 12px 0;font-size:13px;font-weight:700;color:#0f172a;text-transform:uppercase;letter-spacing:.04em;">Суммы</p>
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;background:#f1f5f9;border-radius:12px;overflow:hidden;">
              {_detail_row("Сумма (UZS)", html.escape(money_fmt))}
              {_detail_row("Курс", html.escape(rate_fmt))}
              {_detail_row("Эквивалент", html.escape(eq_fmt))}
              {_detail_row("Возмещаемый", html.escape(reimb))}
              {_detail_row("Способ оплаты", html.escape(pm))}
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 28px 8px 28px;font-family:Segoe UI,Arial,sans-serif;">
            <p style="margin:0 0 12px 0;font-size:13px;font-weight:700;color:#0f172a;text-transform:uppercase;letter-spacing:.04em;">Классификация</p>
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;background:#f8fafc;border-radius:12px;overflow:hidden;">
              {_detail_row("Тип", safe_et)}
              {_detail_row("Подтип", safe_sub)}
              {_detail_row("Подразделение", html.escape(dept))}
              {_detail_row("Проект", html.escape(proj))}
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 28px 8px 28px;font-family:Segoe UI,Arial,sans-serif;">
            <p style="margin:0 0 12px 0;font-size:13px;font-weight:700;color:#0f172a;text-transform:uppercase;letter-spacing:.04em;">Содержание</p>
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;background:#fffbeb;border-radius:12px;overflow:hidden;border:1px solid #fde68a;">
              {_detail_row("Описание", safe_desc)}
              {_detail_row("Контрагент", safe_vendor)}
              {_detail_row("Цель / назначение", safe_bp)}
              {_detail_row("Комментарий", safe_comment)}
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 28px 20px 28px;font-family:Segoe UI,Arial,sans-serif;">
            <p style="margin:0 0 12px 0;font-size:13px;font-weight:700;color:#0f172a;text-transform:uppercase;letter-spacing:.04em;">Вложения</p>
            {attachments_block}
          </td>
        </tr>
        <tr>
          <td style="padding:0 28px 28px 28px;">
            {actions_block}
          </td>
        </tr>
        <tr>
          <td style="padding:16px 28px;background:#f1f5f9;border-top:1px solid #e2e8f0;font-family:Segoe UI,Arial,sans-serif;font-size:12px;color:#64748b;">
            {footer_link_html}
            <p style="margin:0;">Письмо отправлено автоматически сервисом расходов Kosta Legal.</p>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
</body>
</html>"""


def _action_urls(
    settings: Settings,
    expense_id: str,
) -> tuple[str | None, str | None]:
    sec = (settings.expense_email_action_secret or "").strip()
    base_api = (settings.public_api_base_url or "").strip().rstrip("/")
    if not sec or not base_api:
        return None, None
    from infrastructure.email_action_token import sign_email_action_token

    try:
        ttl = int(settings.expense_email_action_ttl_seconds)
        t_ap = sign_email_action_token(sec, expense_id=expense_id, action="approve", ttl_seconds=ttl)
        t_rj = sign_email_action_token(sec, expense_id=expense_id, action="reject", ttl_seconds=ttl)
    except ValueError as e:
        _log.warning("email action links skipped: %s", e)
        return None, None

    want_confirm = bool(settings.expense_email_action_confirm_step)
    q_ap = f"token={quote(t_ap, safe='')}" + ("&confirm=1" if want_confirm else "")
    q_rj = f"token={quote(t_rj, safe='')}" + ("&confirm=1" if want_confirm else "")
    return (
        f"{base_api}/api/v1/expenses/{expense_id}/email-action?{q_ap}",
        f"{base_api}/api/v1/expenses/{expense_id}/email-action?{q_rj}",
    )


def _file_view_url(settings: Settings, expense_id: str, attachment_id: str) -> str | None:
    sec = (settings.expense_email_action_secret or "").strip()
    base_api = (settings.public_api_base_url or "").strip().rstrip("/")
    if not sec or not base_api:
        return None
    from infrastructure.email_action_token import sign_attachment_view_token

    try:
        ttl = int(settings.expense_email_action_ttl_seconds)
        tok = sign_attachment_view_token(
            sec,
            expense_id=expense_id,
            attachment_id=attachment_id,
            ttl_seconds=ttl,
        )
    except ValueError:
        return None
    return (
        f"{base_api}/api/v1/expenses/{expense_id}/attachments/{attachment_id}/email-file"
        f"?token={quote(tok, safe='')}"
    )


async def _send_moderation_message(settings: Settings, ctx: ExpenseModerationEmailContext) -> None:
    if not settings.expense_notify_on_submit:
        _log.debug("expense notify: EXPENSE_NOTIFY_ON_SUBMIT=false, skip")
        return

    if not _smtp_ready(settings):
        missing = _smtp_missing_env_names(settings)
        _log.warning(
            "expense notify: в контейнере/процессе expenses не заданы переменные %s — письмо не отправлено. "
            "Текущий EXPENSE_SMTP_HOST=%r (пустой=%s)",
            ", ".join(missing) if missing else "(неизвестно)",
            (settings.smtp_host or "")[:80],
            not bool((settings.smtp_host or "").strip()),
        )
        return
    recipients = resolve_expense_notify_recipients(
        settings,
        department_id=ctx.department_id,
        expense_type=ctx.expense_type,
        project_id=ctx.project_id,
        is_reimbursable=ctx.is_reimbursable,
    )
    if not recipients:
        _log.warning("expense notify: нет получателей (ROUTING / EXPENSE_NOTIFY_TO), skip")
        return

    expense_id = ctx.expense_id
    author_line = (ctx.author_name or "").strip() or "—"
    if ctx.author_email:
        author_line = f"{author_line} ({ctx.author_email})" if author_line != "—" else ctx.author_email

    reimb = "да" if ctx.is_reimbursable else "нет"
    desc = (ctx.description or "").strip() or "—"
    et = (ctx.expense_type or "").strip() or "—"
    sub = (ctx.expense_subtype or "").strip() or "—"
    vendor = (ctx.vendor or "").strip() or "—"
    bp = (ctx.business_purpose or "").strip() or "—"
    comment = (ctx.comment or "").strip() or "—"
    pm = (ctx.payment_method or "").strip() or "—"
    dept = (ctx.department_id or "").strip() or "—"
    proj = (ctx.project_id or "").strip() or "—"

    safe_desc = html.escape(desc).replace("\n", "<br/>")
    safe_et = html.escape(et)
    safe_sub = html.escape(sub)
    safe_vendor = html.escape(vendor)
    safe_bp = html.escape(bp).replace("\n", "<br/>")
    safe_comment = html.escape(comment).replace("\n", "<br/>")
    safe_author = html.escape(author_line)
    expense_date_fmt = _format_date(ctx.expense_date)
    pd_fmt = _format_date(ctx.payment_deadline)
    money_fmt = _format_money(ctx.amount_uzs)
    rate_fmt = _format_rate(ctx.exchange_rate)
    eq_fmt = _format_money(ctx.equivalent_amount)

    open_link = _build_open_link(settings, expense_id)
    link_plain = open_link or "(задайте FRONTEND_URL в env сервиса expenses)"

    email_ap, email_rj = _action_urls(settings, expense_id)
    if not (email_ap and email_rj):
        _log.debug(
            "email action: задайте EXPENSE_EMAIL_ACTION_SECRET и GATEWAY_BASE_URL — иначе в письме не будет кнопок согласования без входа"
        )

    media_root = Path(settings.media_path)
    inline_images: list[tuple[str, bytes, str]] = []
    file_attachments: list[tuple[str, bytes, str]] = []
    cid_counter = 0

    att_lines_plain: list[str] = []
    att_html_chunks: list[str] = []

    for att in ctx.attachments:
        view_u = _file_view_url(settings, expense_id, att.id)
        kind_ru = _kind_label(att.attachment_kind)
        label = html.escape(att.file_name or "файл")
        sz_kb = max(1, (att.size_bytes or 0) // 1024)
        att_lines_plain.append(
            f"- {att.file_name} ({kind_ru}, ~{sz_kb} KB)"
            + (f"\n  {view_u}" if view_u else "")
        )

        mt = (att.mime_type or "").strip().lower()
        p = media_root / att.storage_key
        is_any_image = mt.startswith("image/")
        is_inline_candidate = _is_inline_image_mime(mt) and p.is_file()
        if (
            is_inline_candidate
            and len(inline_images) < _INLINE_IMAGE_MAX
            and (att.size_bytes or 0) <= _INLINE_IMAGE_MAX_BYTES
        ):
            try:
                data = p.read_bytes()
            except OSError as e:
                _log.warning("expense mail: не прочитать вложение %s: %s", att.id, e)
                data = b""
            if data and len(data) <= _INLINE_IMAGE_MAX_BYTES:
                cid = f"att{cid_counter}"
                cid_counter += 1
                sub_m = mt.split("/")[-1] if "/" in mt else "jpeg"
                inline_images.append((cid, data, sub_m))
                att_html_chunks.append(
                    f'<div style="margin:0 0 16px 0;padding:12px;background:#f8fafc;border-radius:12px;border:1px solid #e2e8f0;">'
                    f'<p style="margin:0 0 8px 0;font-size:13px;color:#64748b;">{label} · {html.escape(kind_ru)}</p>'
                    f'<img src="cid:{cid}" alt="{label}" style="max-width:100%;height:auto;border-radius:8px;display:block;"/>'
                    f"</div>"
                )
                continue
        link_block = ""
        if view_u:
            su = html.escape(view_u, quote=True)
            link_block = f'<p style="margin:8px 0 0 0;"><a href="{su}" style="color:#2563eb;font-weight:600;">Открыть / скачать файл</a></p>'
        att_html_chunks.append(
            f'<div style="margin:0 0 12px 0;padding:14px;background:#f8fafc;border-radius:12px;border:1px solid #e2e8f0;">'
            f'<p style="margin:0;font-size:15px;font-weight:600;color:#0f172a;">{label}</p>'
            f'<p style="margin:6px 0 0 0;font-size:13px;color:#64748b;">{html.escape(kind_ru)} · ~{sz_kb} KB</p>'
            f"{link_block}"
            f"</div>"
        )
        if (
            not is_any_image
            and p.is_file()
            and (att.size_bytes or 0) <= 10 * 1024 * 1024
        ):
            try:
                raw_other = p.read_bytes()
            except OSError:
                raw_other = b""
            if raw_other:
                file_attachments.append(
                    (
                        att.file_name or "file.bin",
                        raw_other,
                        att.mime_type or "application/octet-stream",
                    )
                )
        if is_any_image and p.is_file() and (att.size_bytes or 0) > _INLINE_IMAGE_MAX_BYTES:
            try:
                data = p.read_bytes()
            except OSError:
                data = b""
            if data:
                fn = att.file_name or "attachment.bin"
                file_attachments.append((fn, data, att.mime_type or "application/octet-stream"))

    if att_html_chunks:
        attachments_block = "".join(att_html_chunks)
    else:
        attachments_block = (
            '<p style="margin:0;padding:16px;background:#f8fafc;border-radius:12px;color:#64748b;font-size:14px;">'
            "Файлы не прикреплены.</p>"
        )

    if email_ap and email_rj:
        actions_block = f"""
<div style="padding:24px;background:linear-gradient(180deg,#eef2ff 0%,#e0e7ff 100%);border-radius:16px;border:1px solid #c7d2fe;">
  <p style="margin:0 0 8px 0;font-family:Segoe UI,Arial,sans-serif;font-size:16px;font-weight:700;color:#1e1b4b;">Решение</p>
  <p style="margin:0 0 18px 0;font-size:14px;color:#475569;line-height:1.5;">
    Нажмите кнопку ниже: откроется короткая страница подтверждения на сервере (не приложение), затем действие будет выполнено. Отдельный вход не нужен.
  </p>
  {_button_row_html(email_ap, "✓ Утвердить", "#16a34a")}
  {_button_row_html(email_rj, "✕ Отклонить", "#dc2626")}
  <p style="margin:16px 0 0 0;font-size:12px;color:#64748b;line-height:1.45;">
    Если кнопки не активны в почтовом клиенте, скопируйте ссылку в браузер:<br/>
    <span style="word-break:break-all;color:#334155;">{html.escape(email_ap, quote=False)}</span>
  </p>
</div>"""
    else:
        actions_block = f"""
<div style="padding:22px;background:#fff7ed;border-radius:16px;border:1px solid #fdba74;">
  <p style="margin:0 0 8px 0;font-size:15px;font-weight:700;color:#9a3412;">Согласование по ссылке недоступно</p>
  <p style="margin:0;font-size:14px;color:#7c2d12;line-height:1.55;">
    Задайте в env сервиса <strong>EXPENSE_EMAIL_ACTION_SECRET</strong> и публичный URL API <strong>GATEWAY_BASE_URL</strong> (как в браузере для <code>/api/v1/...</code>).
    Тогда в письме появятся кнопки «Утвердить» / «Отклонить» без входа в SPA.
  </p>
  {"<p style=\"margin:12px 0 0 0;font-size:14px;\"><a href=\"" + html.escape(open_link, quote=True) + "\" style=\"color:#2563eb;font-weight:600;\">Открыть заявку в приложении</a></p>" if open_link else ""}
</div>"""

    html_body = _build_moderation_html(
        ctx=ctx,
        safe_author=safe_author,
        expense_date_fmt=expense_date_fmt,
        money_fmt=money_fmt,
        reimb=reimb,
        safe_desc=safe_desc,
        safe_et=safe_et,
        safe_sub=safe_sub,
        safe_vendor=safe_vendor,
        safe_bp=safe_bp,
        safe_comment=safe_comment,
        dept=dept,
        proj=proj,
        pm=pm,
        pd_fmt=pd_fmt,
        rate_fmt=rate_fmt,
        eq_fmt=eq_fmt,
        open_link=open_link,
        actions_block=actions_block,
        attachments_block=attachments_block,
    )

    subject = f"Заявка на расход {expense_id} — на согласование"
    plain_lines = [
        f"Заявка на согласование: {expense_id}",
        f"Автор: {author_line}",
        f"Дата расхода: {expense_date_fmt}",
        f"Срок оплаты: {pd_fmt}",
        f"Тип: {et} / {sub}",
        f"Сумма (UZS): {money_fmt}",
        f"Курс: {rate_fmt}",
        f"Эквивалент: {eq_fmt}",
        f"Возмещаемый: {reimb}",
        f"Контрагент: {vendor}",
        f"Описание: {desc}",
        "",
        "Вложения:",
        *(att_lines_plain if att_lines_plain else ["(нет)"]),
        "",
    ]
    if email_ap and email_rj:
        plain_lines.extend(
            [
                "Утвердить (сервер, без SPA):",
                email_ap,
                "",
                "Отклонить (сервер, без SPA):",
                email_rj,
                "",
            ]
        )
    if open_link:
        plain_lines.extend(["Открыть в приложении (опционально):", link_plain, ""])
    plain_lines.append("— Kosta Legal / расходы")

    text_body = "\n".join(plain_lines)

    msg_root = MIMEMultipart("mixed")
    msg_root["Subject"] = subject
    from_addr = (settings.expense_mail_from or settings.smtp_user or "").strip()
    msg_root["From"] = from_addr
    msg_root["To"] = ", ".join(recipients)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(text_body, "plain", "utf-8"))

    if inline_images:
        related = MIMEMultipart("related")
        related.attach(MIMEText(html_body, "html", "utf-8"))
        for cid, raw, sub in inline_images:
            img = MIMEImage(raw, _subtype=sub)
            img.add_header("Content-ID", f"<{cid}>")
            img.add_header("Content-Disposition", "inline", filename=f"{cid}.{sub}")
            related.attach(img)
        alt.attach(related)
    else:
        alt.attach(MIMEText(html_body, "html", "utf-8"))

    msg_root.attach(alt)

    for fname, raw, mtype in file_attachments:
        maintype, _, subtype = mtype.partition("/")
        if not subtype:
            maintype, subtype = "application", "octet-stream"
        part = MIMEBase(maintype, subtype)
        part.set_payload(raw)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=fname)
        msg_root.attach(part)

    _log.info(
        "expense notify: отправка SMTP expense_id=%s to=%s host=%s",
        expense_id,
        recipients,
        settings.smtp_host.strip(),
    )
    try:
        await aiosmtplib.send(
            msg_root,
            hostname=settings.smtp_host.strip(),
            port=int(settings.smtp_port),
            username=settings.smtp_user.strip(),
            password=settings.smtp_password,
            start_tls=bool(settings.smtp_use_tls),
        )
    except Exception as e:
        _log.error(
            "expense notify: ошибка SMTP expense_id=%s: %s: %s",
            expense_id,
            type(e).__name__,
            e,
        )
        raise
    _log.info("expense moderation mail sent to %s expense_id=%s", recipients, expense_id)


async def notify_expense_submitted(settings: Settings, ctx: ExpenseModerationEmailContext) -> None:
    """Письмо модераторам при отправке на согласование (submit → pending_approval)."""
    await _send_moderation_message(settings, ctx)


async def send_expense_smtp_test(settings: Settings) -> list[str]:
    """Тест SMTP: письмо «на согласование»."""
    if not _smtp_ready(settings):
        raise ValueError("Задайте EXPENSE_SMTP_HOST, EXPENSE_SMTP_USER, EXPENSE_SMTP_PASSWORD")

    ctx = ExpenseModerationEmailContext(
        expense_id="TEST-EXPENSE",
        description="Тестовое описание для проверки SMTP.",
        expense_date=date(2099, 1, 1),
        payment_deadline=None,
        amount_uzs=Decimal("1234567.89"),
        exchange_rate=Decimal("12500"),
        equivalent_amount=Decimal("98.76"),
        expense_type="office",
        expense_subtype=None,
        is_reimbursable=True,
        payment_method="card",
        department_id="dept-1",
        project_id="proj-1",
        vendor="ООО Тест",
        business_purpose="Проверка вёрстки письма",
        comment="—",
        author_email="author@example.com",
        author_name="Тестовый автор",
        attachments=[],
    )
    recipients = resolve_expense_notify_recipients(
        settings,
        department_id=ctx.department_id,
        expense_type=ctx.expense_type,
        project_id=ctx.project_id,
        is_reimbursable=ctx.is_reimbursable,
    )
    if not recipients:
        raise ValueError("Нет получателей: задайте EXPENSE_NOTIFY_ROUTING_JSON или EXPENSE_NOTIFY_TO")

    await _send_moderation_message(settings, ctx)
    _log.info("expense SMTP test sent to %s", recipients)
    return recipients
