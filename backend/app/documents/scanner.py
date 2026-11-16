"""Virus scanning with ClamAV (clamd INSTREAM protocol over TCP)."""

import asyncio
import struct
from typing import Literal

from app.core.config import get_settings

ScanResult = Literal["clean", "infected"]
CHUNK = 64 * 1024


class ScanError(Exception):
    pass


async def scan_bytes(data: bytes) -> ScanResult:
    """Send the file to clamd and return its verdict. Raises ScanError if clamd fails."""
    settings = get_settings()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(settings.clamav_host, settings.clamav_port), timeout=10
        )
    except (OSError, TimeoutError) as exc:
        raise ScanError(f"ClamAV not reachable: {exc}") from exc
    try:
        writer.write(b"zINSTREAM\0")
        for start in range(0, len(data), CHUNK):
            chunk = data[start : start + CHUNK]
            writer.write(struct.pack("!L", len(chunk)) + chunk)
        writer.write(struct.pack("!L", 0))
        await writer.drain()
        reply = (await asyncio.wait_for(reader.read(4096), timeout=120)).rstrip(b"\0").strip()
    except (OSError, TimeoutError) as exc:
        raise ScanError(f"ClamAV scan failed: {exc}") from exc
    finally:
        writer.close()
    if reply.endswith(b"OK"):
        return "clean"
    if reply.endswith(b"FOUND"):
        return "infected"
    raise ScanError(f"Unexpected ClamAV reply: {reply[:200]!r}")


RETRY_DELAY_SECONDS = 30


def retry_later(ctx: dict[str, object]) -> bool:
    """In the worker: ClamAV not reachable (e.g. still starting) is retried before giving up.

    Tests and inline runs pass an empty ctx: there the scan fails at once.
    """
    job_try = ctx.get("job_try")
    max_tries = ctx.get("max_tries", 3)
    return isinstance(job_try, int) and isinstance(max_tries, int) and job_try < max_tries
