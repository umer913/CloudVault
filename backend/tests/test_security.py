from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import settings
from app.utils.security import (
    ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_round_trip() -> None:
    password_hash = hash_password("password123")
    assert verify_password("password123", password_hash)
    assert not verify_password("wrong-password", password_hash)


def test_access_token_contains_user_and_expiry() -> None:
    token = create_access_token(42)
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["exp"] > datetime.now(timezone.utc).timestamp()


def test_expired_token_is_rejected() -> None:
    token = jwt.encode(
        {
            "sub": "42",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token)


def test_token_with_wrong_signature_is_rejected() -> None:
    token = jwt.encode(
        {
            "sub": "42",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        "wrong-secret-that-is-at-least-32-bytes",
        algorithm=ALGORITHM,
    )
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token)
