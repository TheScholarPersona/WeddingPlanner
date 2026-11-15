"""A minimal iCalendar (RFC 5545) writer for subscription feeds."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta


@dataclass
class IcsEntry:
    uid: str
    summary: str
    start: datetime | date
    end: datetime | date
    location: str | None = None
    url: str | None = None
    status: str | None = None  # CONFIRMED / CANCELLED


def _escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "")
    )


def _fold(line: str) -> list[str]:
    """Lines are limited to 75 octets; continuation lines start with a space."""
    out: list[str] = []
    current = ""
    for char in line:
        limit = 75 if not out else 74
        if len((current + char).encode()) > limit:
            out.append(current)
            current = char
        else:
            current += char
    out.append(current)
    return [out[0], *(" " + part for part in out[1:])]


def _value(moment: datetime | date) -> tuple[str, str]:
    if isinstance(moment, datetime):
        return "", moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return ";VALUE=DATE", moment.strftime("%Y%m%d")


def build(name: str, entries: list[IcsEntry], now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Wedding Planning Platform//Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(name)}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    for entry in entries:
        start_param, start = _value(entry.start)
        end_param, end = _value(entry.end)
        lines += [
            "BEGIN:VEVENT",
            f"UID:{entry.uid}",
            f"DTSTAMP:{stamp}",
            f"DTSTART{start_param}:{start}",
            f"DTEND{end_param}:{end}",
            f"SUMMARY:{_escape(entry.summary)}",
        ]
        if entry.location:
            lines.append(f"LOCATION:{_escape(entry.location)}")
        if entry.url:
            lines.append(f"URL:{entry.url}")
        if entry.status:
            lines.append(f"STATUS:{entry.status}")
        lines.append(
            "TRANSP:TRANSPARENT"
            if isinstance(entry.start, date) and not isinstance(entry.start, datetime)
            else "TRANSP:OPAQUE"
        )
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "".join(part + "\r\n" for line in lines for part in _fold(line))


def all_day_end(day: date) -> date:
    """DTEND of an all-day entry is exclusive."""
    return day + timedelta(days=1)
