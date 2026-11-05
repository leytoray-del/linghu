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


def assignment_event(request: ResourceRequest, *, now_utc: datetime, link: str, sequence: int = 0) -> str:
    """An all-day event spanning the planned period. It is marked as free time so that a long assignment
    does not block the whole calendar."""
    assert request.planned_start and request.planned_end
    engineers = [
        f"{a.engineer.display_name} ({a.allocation_pct}%)"
        for a in request.allocations
        if a.status != "RELEASED"
    ]
    description = "\n".join(
        [
            f"Request: {request.display_no}",
            f"Client: {request.client_name or '-'}",
            f"Engineers: {', '.join(engineers) or '-'}",
            f"Requested by: {request.requester.display_name}",
            "",
            f"Schedule: {request.task_schedule or '-'}",
            "",
            link,
        ]
    )
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "METHOD:PUBLISH",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{request.display_no}@erf",
        f"SEQUENCE:{sequence}",
        f"DTSTAMP:{now_utc.strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;VALUE=DATE:{request.planned_start.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{(request.planned_end + timedelta(days=1)).strftime('%Y%m%d')}",
        f"SUMMARY:{_escape(f'{request.display_no} {request.project_name} ({request.client_name})')}",
        f"DESCRIPTION:{_escape(description)}",
        f"URL:{link}",
        "TRANSP:TRANSPARENT",
        "STATUS:CONFIRMED",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
