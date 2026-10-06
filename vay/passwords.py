"""Password hashing. bcrypt for new hashes; SHA-256 hex still verifies for legacy users."""

from __future__ import annotations

import hashlib
import os
import re

import bcrypt

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.I)


def hash_password(value: str) -> str:
    raw = str(value or "").encode("utf-8")
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("ascii")


def password_ok(provided: str, expected) -> bool:
    expected = str(expected or "")
    if not expected:
        return False
    raw = str(provided or "").encode("utf-8")
    if expected.startswith("$2"):
        try:
            return bcrypt.checkpw(raw, expected.encode("ascii"))
        except (ValueError, TypeError):
            return False
    if _SHA256_RE.fullmatch(expected):
        digest = hashlib.sha256(raw).hexdigest()
        return digest == expected.lower()
    return False


def needs_rehash(stored) -> bool:
    stored = str(stored or "")
    return bool(stored) and not stored.startswith("$2")


def bootstrap_password() -> str:
    return (os.environ.get("VAY_BOOTSTRAP_PASSWORD") or "admin123").strip() or "admin123"


def bootstrap_must_change() -> bool:
    return not (os.environ.get("VAY_BOOTSTRAP_PASSWORD") or "").strip()
