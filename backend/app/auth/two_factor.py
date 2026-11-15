"""Two-factor authentication with time-based one-time passwords (TOTP, RFC 6238).

The secret is stored encrypted (app.core.crypto). Ten one-time recovery codes are created when
2FA is switched on; only their hashes are stored and they are shown exactly once.
"""

import secrets
from datetime import UTC, datetime

import pyotp
import segno
from pyotp.totp import TOTP
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.models import RecoveryCode, User
from app.core.crypto import decrypt, encrypt
from app.core.errors import ProblemError
from app.core.security import hash_token

ISSUER = "Wedding Planning Platform"
RECOVERY_CODES = 10

INVALID_CODE = ProblemError(
    400, "invalid_code", "Code not valid", "The code is not valid. Check the time on your phone."
)


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_recovery(code: str) -> str:
    return "".join(c for c in code.lower() if c.isalnum())


def _new_recovery_code() -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"  # no look-alikes (0/o, 1/l/i)
    raw = "".join(secrets.choice(alphabet) for _ in range(10))
    return f"{raw[:5]}-{raw[5:]}"


def _totp(user: User) -> TOTP | None:
    if not user.totp_secret_enc:
        return None
    secret = decrypt(user.totp_secret_enc)
    return TOTP(secret) if secret else None


async def _audit(db: AsyncSession, user: User, action: str) -> None:
    await audit.record(
        db, action=action, resource_type="user", resource_id=user.id, actor_user_id=user.id
    )


async def verify(db: AsyncSession, user: User, code: str) -> bool:
    """A current authenticator code, or an unused recovery code (which is then used up)."""
    code = code.strip().replace(" ", "")
    if code.isdigit() and len(code) == 6:
        totp = _totp(user)
        return bool(totp and user.two_factor_enabled and totp.verify(code, valid_window=1))
    normalized = _normalize_recovery(code)
    if len(normalized) != 10:
        return False
    row = (
        await db.execute(
            select(RecoveryCode).where(
                RecoveryCode.user_id == user.id,
                RecoveryCode.code_hash == hash_token(normalized),
                RecoveryCode.used_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    row.used_at = _now()
    await _audit(db, user, "auth.recovery_code_used")
    return True


async def start_setup(db: AsyncSession, user: User) -> tuple[str, str, str]:
    """A new secret (not yet active). Returns (secret, otpauth URI, QR code as SVG data URI)."""
    if user.two_factor_enabled:
        raise ProblemError(
            409, "two_factor_enabled", "Already on", "Two-factor authentication is already on."
        )
    secret = pyotp.random_base32()
    user.totp_secret_enc = encrypt(secret)
    uri = TOTP(secret).provisioning_uri(name=user.email, issuer_name=ISSUER)
    qr = segno.make(uri, error="m").svg_data_uri(scale=5, border=2)
    return secret, uri, qr


async def _new_recovery_codes(db: AsyncSession, user: User) -> list[str]:
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    codes = [_new_recovery_code() for _ in range(RECOVERY_CODES)]
    for code in codes:
        db.add(RecoveryCode(user_id=user.id, code_hash=hash_token(_normalize_recovery(code))))
    await db.flush()
    return codes


async def enable(db: AsyncSession, user: User, code: str) -> list[str]:
    totp = _totp(user)
    if user.two_factor_enabled or totp is None:
        raise ProblemError(
            409, "setup_not_started", "Start again", "Start the setup again to get a new code."
        )
    if not totp.verify(code.strip().replace(" ", ""), valid_window=1):
        raise INVALID_CODE
    user.totp_enabled_at = _now()
    codes = await _new_recovery_codes(db, user)
    await _audit(db, user, "auth.two_factor_enabled")
    return codes


async def disable(db: AsyncSession, user: User) -> None:
    user.totp_secret_enc = None
    user.totp_enabled_at = None
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    await _audit(db, user, "auth.two_factor_disabled")


async def regenerate_codes(db: AsyncSession, user: User) -> list[str]:
    if not user.two_factor_enabled:
        raise ProblemError(
            409, "two_factor_disabled", "Not on", "Two-factor authentication is not on."
        )
    codes = await _new_recovery_codes(db, user)
    await _audit(db, user, "auth.recovery_codes_regenerated")
    return codes


async def remaining_codes(db: AsyncSession, user: User) -> int:
    rows = await db.execute(
        select(RecoveryCode.id).where(
            RecoveryCode.user_id == user.id, RecoveryCode.used_at.is_(None)
        )
    )
    return len(rows.all())
