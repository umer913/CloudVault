from __future__ import annotations

import hashlib
import logging
import uuid
from typing import BinaryIO

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError
from app.models import File, Folder, User
from app.services.supabase_storage_service import (
    StorageError,
    StorageObjectTooLarge,
    SupabaseStorage,
)
from app.utils.validation import (
    ValidatedUpload,
    file_extension,
    sanitize_filename,
    validate_upload,
)

logger = logging.getLogger(__name__)

_TYPE_EXTENSIONS = {
    "documents": {"pdf", "docx", "txt"},
    "images": {"png", "jpg", "jpeg"},
    "archives": {"zip"},
    "data": {"csv", "json"},
}
def list_files(
    db: Session,
    user: User,
    *,
    folder_id: int | None,
    query: str | None,
    file_type: str | None,
    sort: str,
    order: str,
    limit: int,
    offset: int,
) -> tuple[list[File], int]:
    filters = [File.user_id == user.id, File.folder_id == folder_id]
    if query:
        escaped = (
            query.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        filters.append(File.original_name.ilike(f"%{escaped}%", escape="\\"))
    if file_type is not None:
        extensions = _TYPE_EXTENSIONS[file_type]
        filters.append(File.extension.in_(extensions))

    sort_column = {
        "name": File.original_name,
        "created_at": File.created_at,
        "size": File.size,
    }[sort]
    sort_expression = sort_column.desc() if order == "desc" else sort_column.asc()

    statement = (
        select(File)
        .where(*filters)
        .order_by(sort_expression, File.id.asc())
        .offset(offset)
        .limit(limit)
    )
    items = list(db.scalars(statement))
    total = db.scalar(select(func.count(File.id)).where(*filters)) or 0
    return items, total


def get_owned_file(db: Session, user: User, file_id: int) -> File:
    record = db.scalar(
        select(File).where(File.id == file_id, File.user_id == user.id)
    )
    if record is None:
        raise AppError(404, "FILE_NOT_FOUND", "File not found.")
    return record


def update_file(
    db: Session,
    user: User,
    file_id: int,
    *,
    name: str | None,
    folder_id: int | None,
    folder_id_provided: bool,
) -> File:
    record = get_owned_file(db, user, file_id)
    changes = {}

    if name is not None:
        validated_name = sanitize_filename(name)
        changes["original_name"] = validated_name
        changes["extension"] = file_extension(validated_name)

    if folder_id_provided:
        if folder_id is not None:
            target = db.scalar(
                select(Folder).where(
                    Folder.id == folder_id,
                    Folder.user_id == user.id,
                )
            )
            if target is None:
                raise AppError(404, "FOLDER_NOT_FOUND", "Folder not found.")
        changes["folder_id"] = folder_id

    if not changes:
        return record

    for field, value in changes.items():
        setattr(record, field, value)
    try:
        db.commit()
        db.refresh(record)
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            409,
            "DUPLICATE_NAME",
            "A file with this name already exists in that folder.",
        ) from exc
    return record


def delete_file(
    db: Session,
    user: User,
    file_id: int,
    storage: SupabaseStorage,
) -> None:
    record = get_owned_file(db, user, file_id)
    storage_key = record.storage_key
    size = record.size
    db.delete(record)
    db.execute(
        update(User)
        .where(User.id == user.id)
        .values(used_bytes=User.used_bytes - size)
    )
    db.commit()
    try:
        storage.delete(storage_key)
    except StorageError:
        logger.exception("Failed to delete file object after metadata deletion.")


def upload_file(
    db: Session,
    user: User,
    *,
    filename: str,
    content: BinaryIO,
    folder_id: int | None,
    storage: SupabaseStorage,
    progress_callback=None,
) -> File:
    if folder_id is not None:
        folder = db.scalar(
            select(Folder).where(
                Folder.id == folder_id,
                Folder.user_id == user.id,
            )
        )
        if folder is None:
            raise AppError(404, "FOLDER_NOT_FOUND", "Folder not found.")

    validated, size, checksum = _inspect_upload(filename, content)
    if size > settings.MAX_UPLOAD_BYTES:
        raise AppError(
            413,
            "FILE_TOO_LARGE",
            "The file exceeds the maximum upload size.",
        )

    quota_update = db.execute(
        update(User)
        .where(
            User.id == user.id,
            User.used_bytes + size <= User.storage_quota,
        )
        .values(used_bytes=User.used_bytes + size)
    )
    if quota_update.rowcount != 1:
        raise AppError(
            413,
            "QUOTA_EXCEEDED",
            "The upload exceeds your storage quota.",
        )

    storage_key = f"{user.id}/{uuid.uuid4().hex}.bin"
    uploaded = False
    try:
        content.seek(0)
        storage.upload(
            storage_key,
            content,
            content_type=validated.mime_type,
            size=size,
            progress_callback=progress_callback,
        )
        uploaded = True

        file_record = File(
            user_id=user.id,
            folder_id=folder_id,
            original_name=validated.original_name,
            extension=validated.extension,
            storage_key=storage_key,
            size=size,
            mime_type=validated.mime_type,
            checksum=checksum,
        )
        db.add(file_record)
        db.commit()
        db.refresh(file_record)
        return file_record
    except IntegrityError as exc:
        db.rollback()
        if uploaded:
            _delete_after_failure(storage, storage_key)
        raise AppError(
            409,
            "DUPLICATE_NAME",
            "A file with this name already exists in that folder.",
        ) from exc
    except StorageError as exc:
        db.rollback()
        if uploaded:
            _delete_after_failure(storage, storage_key)
        logger.exception(
            "Storage upload failed for file %s (%d bytes).",
            validated.original_name,
            size,
        )
        if isinstance(exc, StorageObjectTooLarge):
            raise AppError(
                413,
                "STORAGE_SIZE_LIMIT",
                "Supabase Storage rejected this file because it exceeds "
                "the configured Storage size limit.",
            ) from exc
        raise AppError(
            502,
            "STORAGE_UNAVAILABLE",
            "File storage is temporarily unavailable.",
        ) from exc
    except SQLAlchemyError:
        db.rollback()
        if uploaded:
            _delete_after_failure(storage, storage_key)
        raise


def complete_direct_upload(
    db: Session,
    user: User,
    *,
    filename: str,
    size: int,
    folder_id: int | None,
    mime_type: str,
    extension: str,
    storage_key: str,
    checksum: str,
) -> File:
    if folder_id is not None:
        folder = db.scalar(
            select(Folder).where(
                Folder.id == folder_id,
                Folder.user_id == user.id,
            )
        )
        if folder is None:
            raise AppError(404, "FOLDER_NOT_FOUND", "Folder not found.")

    if size > settings.MAX_UPLOAD_BYTES:
        raise AppError(
            413,
            "FILE_TOO_LARGE",
            "The file exceeds the maximum upload size.",
        )

    quota_update = db.execute(
        update(User)
        .where(
            User.id == user.id,
            User.used_bytes + size <= User.storage_quota,
        )
        .values(used_bytes=User.used_bytes + size)
    )
    if quota_update.rowcount != 1:
        raise AppError(
            413,
            "QUOTA_EXCEEDED",
            "The upload exceeds your storage quota.",
        )

    file_record = File(
        user_id=user.id,
        folder_id=folder_id,
        original_name=filename,
        extension=extension,
        storage_key=storage_key,
        size=size,
        mime_type=mime_type,
        checksum=checksum,
    )
    try:
        db.add(file_record)
        db.commit()
        db.refresh(file_record)
        return file_record
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            409,
            "DUPLICATE_NAME",
            "A file with this name already exists in that folder.",
        ) from exc
    except SQLAlchemyError:
        db.rollback()
        raise


def _inspect_upload(
    filename: str,
    content: BinaryIO,
) -> tuple[ValidatedUpload, int, str]:
    content.seek(0)
    validated = validate_upload(filename, content)
    content.seek(0)

    digest = hashlib.sha256()
    size = 0
    while chunk := content.read(1024 * 1024):
        size += len(chunk)
        if size > settings.MAX_UPLOAD_BYTES:
            break
        digest.update(chunk)
    content.seek(0)
    return validated, size, digest.hexdigest()


def _delete_after_failure(storage: SupabaseStorage, storage_key: str) -> None:
    try:
        storage.delete(storage_key)
    except StorageError:
        logger.exception(
            "Failed to clean up uploaded object after database failure."
        )