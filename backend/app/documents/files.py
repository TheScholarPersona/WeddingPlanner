"""Upload checks: allowed file types, content sniffing and safe file names."""

import unicodedata
from dataclasses import dataclass

from fastapi import UploadFile

from app.core import ratelimit
from app.core.config import get_settings
from app.core.errors import ProblemError

# Extension -> (content type, check of the first bytes). The type sent by the browser is
# ignored; files whose content does not match their extension are rejected.
_OOXML = b"PK\x03\x04"
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _text(head: bytes) -> bool:
    if b"\0" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as exc:
        # A multi-byte character may be cut off at the end of the sniffed prefix.
        return exc.start >= len(head) - 3
    return True


ALLOWED: dict[str, tuple[str, object]] = {
    "pdf": ("application/pdf", b"%PDF-"),
    "png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    "jpg": ("image/jpeg", b"\xff\xd8\xff"),
    "jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    "gif": ("image/gif", b"GIF8"),
    "webp": ("image/webp", lambda h: h[:4] == b"RIFF" and h[8:12] == b"WEBP"),
    "heic": ("image/heic", lambda h: h[4:8] == b"ftyp"),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        _OOXML,
    ),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", _OOXML),
    "pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        _OOXML,
    ),
    "doc": ("application/msword", _OLE),
    "xls": ("application/vnd.ms-excel", _OLE),
    "txt": ("text/plain; charset=utf-8", _text),
    "csv": ("text/csv; charset=utf-8", _text),
}


@dataclass
class CheckedFile:
    filename: str
    content_type: str
    data: bytes


def unsupported(message: str) -> ProblemError:
    return ProblemError(422, "unsupported_file", "File not accepted", message)


def safe_filename(name: str | None) -> str:
    name = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = unicodedata.normalize("NFC", name)
    name = "".join(c for c in name if unicodedata.category(c)[0] != "C" and c not in '"<>|*?:')
    name = name.strip().strip(".")
    if len(name) > 200:
        stem, dot, ext = name.rpartition(".")
        name = f"{stem[: 200 - len(ext) - 1]}{dot}{ext}" if dot else name[:200]
    return name or "file"


UPLOADS_PER_MINUTE = 30


async def read_upload(upload: UploadFile, user_id: object) -> CheckedFile:
    await ratelimit.enforce([f"upload:user:{user_id}"], UPLOADS_PER_MINUTE)
    limit = get_settings().max_upload_mb * 1024 * 1024
    chunks: list[bytes] = []
    size = 0
    while chunk := await upload.read(1024 * 1024):
        size += len(chunk)
        if size > limit:
            raise ProblemError(
                413,
                "file_too_large",
                "File too large",
                f"Files can be up to {get_settings().max_upload_mb} MB.",
            )
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise unsupported("The file is empty.")

    filename = safe_filename(upload.filename)
    extension = filename.rpartition(".")[2].lower() if "." in filename else ""
    allowed = ALLOWED.get(extension)
    if allowed is None:
        raise unsupported(
            "Upload PDF, Word, Excel, PowerPoint, text or image files (JPG, PNG, HEIC, WebP)."
        )
    content_type, check = allowed
    head = data[:512]
    ok = check(head) if callable(check) else head.startswith(check)  # type: ignore[arg-type]
    if not ok:
        raise unsupported("The file's content does not match its type.")
    return CheckedFile(filename=filename, content_type=content_type, data=data)
