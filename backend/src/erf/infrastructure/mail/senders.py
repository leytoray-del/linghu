"""Mail transports. ``log`` writes messages to the application log; ``smtp`` uses an authenticated relay."""

from __future__ import annotations

import html
import logging
import smtplib
from dataclasses import dataclass, field, replace
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Protocol

from erf.core.config import Settings

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Attachment:
    filename: str
    content_type: str
    """For example "text/calendar; method=PUBLISH; charset=UTF-8"."""
    content: str


@dataclass(frozen=True, slots=True)
class OutgoingMail:
    to: list[str]
    cc: list[str]
    subject: str
    html: str
    text: str
    attachments: list[Attachment] = field(default_factory=list)


class MailSender(Protocol):
    def send(self, mail: OutgoingMail) -> None: ...


def redirect(mail: OutgoingMail, address: str) -> OutgoingMail:
    """Send a message to one test mailbox and state who the real recipients were."""
    intended = f"To: {', '.join(mail.to)}" + (f" | Cc: {', '.join(mail.cc)}" if mail.cc else "")
    note = f"Demo mode: this email was redirected. Intended recipients: {intended}"
    banner = (
        '<div style="background:#fff4e5;border:1px solid #e9a94a;padding:8px 12px;margin:0 0 12px;'
        f'font:13px Segoe UI,Arial,sans-serif;color:#5a3b00">{html.escape(note)}</div>'
    )
    start = mail.html.find("<body")
    marker = mail.html.find(">", start) + 1 if start >= 0 else 0
    return replace(
        mail,
        to=[address],
        cc=[],
        subject=f"[Demo → {', '.join(mail.to)}] {mail.subject}"[:250],
        html=mail.html[:marker] + banner + mail.html[marker:],
        text=f"{note}\n\n{mail.text}",
    )


class LogSender:
    """Development transport: nothing leaves the server."""

    def __init__(self, settings: Settings | None = None):
        self.redirect_to = settings.mail_redirect_to if settings else None

    def send(self, mail: OutgoingMail) -> None:
        if self.redirect_to:
            mail = redirect(mail, self.redirect_to)
        log.info(
            "EMAIL (log backend) to=%s cc=%s subject=%s attachments=%s",
            mail.to,
            mail.cc,
            mail.subject,
            [a.filename for a in mail.attachments],
        )


class SmtpSender:
    def __init__(self, settings: Settings):
        self.settings = settings

    def build(self, mail: OutgoingMail) -> EmailMessage:
        if self.settings.mail_redirect_to:
            mail = redirect(mail, self.settings.mail_redirect_to)
        msg = EmailMessage()
        msg["From"] = self.settings.mail_from
        msg["To"] = ", ".join(mail.to)
        if mail.cc:
            msg["Cc"] = ", ".join(mail.cc)
        msg["Subject"] = mail.subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()
        msg.set_content(mail.text)
        msg.add_alternative(mail.html, subtype="html")
        for a in mail.attachments:
            main, _, rest = a.content_type.partition("/")
            subtype = rest.split(";", 1)[0].strip()
            params = dict(
                p.strip().split("=", 1) for p in rest.split(";")[1:] if "=" in p and "charset" not in p
            )
            msg.add_attachment(
                a.content.encode("utf-8"), maintype=main, subtype=subtype, filename=a.filename, params=params
            )
        return msg

    def send(self, mail: OutgoingMail) -> None:
        msg = self.build(mail)
        s = self.settings
        if s.smtp_port == 465:
            client: smtplib.SMTP = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds)
        else:
            client = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds)
        with client:
            if s.smtp_port != 465 and s.smtp_starttls:
                client.starttls()
            if s.smtp_username:
                client.login(s.smtp_username, s.smtp_password or "")
            client.send_message(msg)


def build_sender(settings: Settings) -> MailSender:
    return SmtpSender(settings) if settings.mail_backend == "smtp" else LogSender(settings)
