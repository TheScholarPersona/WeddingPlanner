"""Symmetric encryption for secrets kept in the database (e.g. two-factor keys)."""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


@lru_cache
def _fernet(secret: str) -> Fernet:
    key = hashlib.sha256(f"wedding-platform:db-secrets:{secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str) -> str:
    return _fernet(get_settings().secret_key).encrypt(value.encode()).decode()


def decrypt(value: str) -> str | None:
    try:
        return _fernet(get_settings().secret_key).decrypt(value.encode()).decode()
    except InvalidToken:
        return None
