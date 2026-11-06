"""iCalendar (RFC 5545) files for confirmed assignments, so engineers can add them to Outlook in one click."""

from __future__ import annotations

from datetime import datetime, timedelta

from erf.db.models import ResourceRequest

PRODID = "-//Engineering Resource Requests//ERF//EN"


def _escape(value: str) -> str:
    """Escape TEXT values: backslash, semicolon, comma and line breaks."""
    out = value.replace("\\", "\\\\")
    for ch in (";", ","):
        out = out.replace(ch, "\\" + ch)
    return out.replace("\r\n", "\\n").replace("\n", "\\n")


def _param(value: str) -> str:
    """Parameter values such as CN=... are quoted, not escaped, when they contain : ; or , (RFC 5545 3.1)."""
    value = value.replace('"', "'").replace("\r", " ").replace("\n", " ")
    return f'"{value}"' if any(ch in value for ch in ":;,") else value


def _fold(line: str) -> str:
    """Fold content lines longer than 75 octets, as the standard requires."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts: list[str] = []
    current = b""
    for ch in line:
        b = ch.encode("utf-8")
        limit = 75 if not parts else 74
        if len(current) + len(b) > limit:
            parts.append(current.decode("utf-8"))
            current = b""
        current += b
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def assignment_invite(
    request: ResourceRequest,
    *,
    engineer_name: str,
    engineer_email: str,
    allocation_pct: int,
    method: str,
    organizer_name: str,
    organizer_email: str,
    sequence: int,
    now_utc: datetime,
    link: str,
) -> str:
    """A personal calendar invitation (METHOD:REQUEST) or cancellation (METHOD:CANCEL) for one engineer.

    Mail servers such as Exchange add a REQUEST to the recipient's calendar as tentative, so it also
    appears in Teams. Later messages with the same UID and a higher SEQUENCE update or remove the entry.
    The event is all-day across the planned period and shown as free, so it does not block the calendar.
    """
    assert method in ("REQUEST", "CANCEL")
    assert request.planned_start and request.planned_end
    cancelled = method == "CANCEL"
    description = "\n".join(
        [
            f"Request: {request.display_no}",
            f"Client: {request.client_name or '-'}",
            f"Your allocation: {allocation_pct}% of your time",
            f"Requested by: {request.requester.display_name}",
            "",
            f"Schedule: {request.task_schedule or '-'}",
            "",
            link,
        ]
    )
    summary = f"{request.display_no} {request.project_name} ({request.client_name}) - {allocation_pct}%"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        f"METHOD:{method}",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{request.display_no}@erf",
        f"SEQUENCE:{sequence}",
        f"DTSTAMP:{now_utc.strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;VALUE=DATE:{request.planned_start.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{(request.planned_end + timedelta(days=1)).strftime('%Y%m%d')}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(description)}",
        f"URL:{link}",
        f"ORGANIZER;CN={_param(organizer_name)}:mailto:{organizer_email}",
        f"ATTENDEE;CN={_param(engineer_name)};ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=FALSE:mailto:{engineer_email}",
        "TRANSP:TRANSPARENT",
        "X-MICROSOFT-CDO-BUSYSTATUS:FREE",
        "X-MICROSOFT-CDO-ALLDAYEVENT:TRUE",
        "CLASS:PUBLIC",
        f"STATUS:{'CANCELLED' if cancelled else 'CONFIRMED'}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
