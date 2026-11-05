"""Mail transports. ``log`` writes messages to the application log; ``smtp`` uses an authenticated relay."""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Protocol

from erf.core.config import Settings

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OutgoingMail:
    to: list[str]
    cc: list[str]
    subject: str
    html: str
    text: str


class MailSender(Protocol):
    def send(self, mail: OutgoingMail) -> None: ...


class LogSender:
    """Development transport: nothing leaves the server."""

    def send(self, mail: OutgoingMail) -> None:
        log.info("EMAIL (log backend) to=%s cc=%s subject=%s", mail.to, mail.cc, mail.subject)


class SmtpSender:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, mail: OutgoingMail) -> None:
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
    return SmtpSender(settings) if settings.mail_backend == "smtp" else LogSender()
