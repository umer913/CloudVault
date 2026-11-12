from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import File, Share, User

_hasher = PasswordHash.recommended()
_MAX_SHARE_LIFETIME = timedelta(days=30)
_PREVIEWABLE = {"pdf", "png", "jpg", "jpeg", "txt"}


def create_share(
    db: Session,
    user: User,
    *,
    file_id: int,
    permission: str,
    expires_at: datetime,
    password: str | None,
) -> tuple[Share, str, str]:
    file_record = _owned_file(db, user, file_id)
    now = datetime.now(timezone.utc)
    expiry = _ensure_utc(expires_at)

    if expiry <= now or expiry > now + _MAX_SHARE_LIFETIME:
        raise AppError(
            422,
            "INVALID_EXPIRY",
            "Share expiry must be in the future and within 30 days.",
        )
    if permission not in {"view", "download"}:
        raise AppError(422, "INVALID_PERMISSION", "Invalid share permission.")
    if permission == "view" and file_record.extension not in _PREVIEWABLE:
        raise AppError(
            422,
            "PREVIEW_NOT_SUPPORTED",
            "View sharing is only available for previewable files.",
        )

    token = secrets.token_urlsafe(32)
    share = Share(
        file_id=file_id,
        token_hash=hashlib.sha256(token.encode()).hexdigest(),
        permission=permission,
        password_hash=_hasher.hash(password) if password else None,
        expires_at=expiry,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    return share, token, file_record.original_name


def list_owned_shares(db: Session, user: User) -> list[tuple[Share, str]]:
    now = datetime.now(timezone.utc)
    return list(
        db.execute(
            select(Share, File.original_name)
            .join(File, File.id == Share.file_id)
            .where(
                File.user_id == user.id,
                Share.revoked_at.is_(None),
                Share.expires_at > now,
            )
            .order_by(Share.created_at.desc(), Share.id.desc())
        )
    )


def rotate_share_token(
    db: Session,
    user: User,
    share_id: int,
) -> tuple[Share, str, str]:
    share = get_owned_share(db, user, share_id)
    if share.revoked_at is not None or _ensure_utc(share.expires_at) <= datetime.now(
        timezone.utc
    ):
        raise AppError(404, "SHARE_NOT_FOUND", "Share not found.")

    file_record = db.get(File, share.file_id)
    if file_record is None:
        raise AppError(404, "FILE_NOT_FOUND", "File not found.")

    token = secrets.token_urlsafe(32)
    share.token_hash = hashlib.sha256(token.encode()).hexdigest()
    db.commit()
    db.refresh(share)
    return share, token, file_record.original_name


def get_owned_share(db: Session, user: User, share_id: int) -> Share:
    share = db.scalar(
        select(Share)
        .join(File, File.id == Share.file_id)
        .where(Share.id == share_id, File.user_id == user.id)
    )
    if share is None:
        raise AppError(404, "SHARE_NOT_FOUND", "Share not found.")
    return share


def get_owned_share_with_name(
    db: Session,
    user: User,
    share_id: int,
) -> tuple[Share, str]:
    result = db.execute(
        select(Share, File.original_name)
        .join(File, File.id == Share.file_id)
        .where(Share.id == share_id, File.user_id == user.id)
    ).first()
    if result is None:
        raise AppError(404, "SHARE_NOT_FOUND", "Share not found.")
    return result


def revoke_share(db: Session, user: User, share_id: int) -> None:
    share = get_owned_share(db, user, share_id)
    share.revoked_at = datetime.now(timezone.utc)
    db.commit()


def get_public_share(db: Session, token: str) -> tuple[Share, File]:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    row = db.execute(
        select(Share, File)
        .join(File, File.id == Share.file_id)
        .where(Share.token_hash == token_hash)
    ).first()
    if row is None:
        raise AppError(404, "SHARE_NOT_FOUND", "Share not found.")

    share, file_record = row
    now = datetime.now(timezone.utc)
    if share.revoked_at is not None or _ensure_utc(share.expires_at) <= now:
        raise AppError(404, "SHARE_NOT_FOUND", "Share not found.")
    return share, file_record


def verify_share_password(share: Share, password: str | None) -> None:
    if share.password_hash is not None and (
        not password or not _hasher.verify(password, share.password_hash)
    ):
        raise AppError(
            401,
            "PASSWORD_REQUIRED",
            "A valid share password is required.",
        )


def _owned_file(db: Session, user: User, file_id: int) -> File:
    file_record = db.scalar(
        select(File).where(File.id == file_id, File.user_id == user.id)
    )
    if file_record is None:
        raise AppError(404, "FILE_NOT_FOUND", "File not found.")
    return file_record


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise AppError(422, "INVALID_EXPIRY", "Expiry must include a timezone.")
    return value.astimezone(timezone.utc)
