"""Image checks and derived versions for moodboards.

Uploaded originals are kept as they are (the team can download them). Thumbnails (400 px) and
display versions (1600 px) are re-encoded as WebP from the pixels only, so they carry no
metadata: phone photos often contain GPS coordinates and camera serial numbers.
"""

import io
from dataclasses import dataclass

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from app.core import ratelimit
from app.core.errors import ProblemError
from app.documents.files import safe_filename

register_heif_opener()
# Refuse "decompression bombs": a small file that unpacks into a gigantic bitmap.
Image.MAX_IMAGE_PIXELS = 60_000_000

MAX_IMAGE_MB = 15
MAX_FILES_PER_UPLOAD = 20
UPLOADS_PER_MINUTE = 30
THUMB_PX = 400
DISPLAY_PX = 1600

ALLOWED = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "heic": "image/heic",
    "heif": "image/heif",
}
FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "HEIF": "image/heic"}


@dataclass
class CheckedImage:
    filename: str
    content_type: str
    data: bytes
    width: int
    height: int


@dataclass
class Derived:
    thumb: bytes
    display: bytes


def unsupported(message: str) -> ProblemError:
    return ProblemError(422, "unsupported_image", "Image not accepted", message)


def _open(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Image.DecompressionBombError as exc:
        raise unsupported("This image is too large to process.") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise unsupported("The file is not a readable image.") from exc
    return image


async def read_images(files: list[UploadFile], user_id: object) -> list[CheckedImage]:
    if not files:
        raise unsupported("Choose at least one image.")
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise unsupported(f"Upload up to {MAX_FILES_PER_UPLOAD} images at a time.")
    await ratelimit.enforce([f"moodboard-upload:user:{user_id}"], UPLOADS_PER_MINUTE)
    checked: list[CheckedImage] = []
    limit = MAX_IMAGE_MB * 1024 * 1024
    for upload in files:
        data = await upload.read(limit + 1)
        if len(data) > limit:
            raise ProblemError(
                413,
                "file_too_large",
                "Image too large",
                f"Images can be up to {MAX_IMAGE_MB} MB.",
            )
        filename = safe_filename(upload.filename)
        extension = filename.rpartition(".")[2].lower() if "." in filename else ""
        if extension not in ALLOWED:
            raise unsupported("Upload JPG, PNG, WebP or HEIC images.")
        image = _open(data)
        detected = FORMATS.get(image.format or "")
        if detected is None or (
            detected != ALLOWED[extension] and "heic" not in detected + extension
        ):
            raise unsupported("The file's content does not match its type.")
        width, height = ImageOps.exif_transpose(image).size
        checked.append(
            CheckedImage(
                filename=filename,
                content_type=detected,
                data=data,
                width=width,
                height=height,
            )
        )
    return checked


def _resized(image: Image.Image, longest: int) -> bytes:
    copy = image.copy()
    copy.thumbnail((longest, longest), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    # Only pixels are written: no EXIF, GPS or ICC/XMP metadata.
    copy.save(out, format="WEBP", quality=82, method=4)
    return out.getvalue()


def derive(data: bytes) -> Derived:
    image = ImageOps.exif_transpose(_open(data))  # respect the phone's rotation, then drop EXIF
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    return Derived(thumb=_resized(image, THUMB_PX), display=_resized(image, DISPLAY_PX))
