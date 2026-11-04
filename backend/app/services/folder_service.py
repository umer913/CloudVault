from __future__ import annotations

import logging

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import File, Folder, User
from app.services.supabase_storage_service import StorageError, SupabaseStorage
from app.utils.validation import sanitize_filename

logger = logging.getLogger(__name__)


def get_owned_folder(db: Session, user: User, folder_id: int) -> Folder:
    folder = db.scalar(
        select(Folder).where(Folder.id == folder_id, Folder.user_id == user.id)
    )
    if folder is None:
        raise AppError(404, "FOLDER_NOT_FOUND", "Folder not found.")
    return folder


def create_folder(
    db: Session,
    user: User,
    *,
    name: str,
    parent_id: int | None,
) -> Folder:
    clean_name = sanitize_filename(name)
    if parent_id is not None:
        get_owned_folder(db, user, parent_id)

    folder = Folder(user_id=user.id, parent_id=parent_id, name=clean_name)
    db.add(folder)
    try:
        db.commit()
        db.refresh(folder)
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            409,
            "DUPLICATE_NAME",
            "A folder with this name already exists here.",
        ) from exc
    return folder


def list_folders(
    db: Session,
    user: User,
    *,
    parent_id: int | None,
) -> list[Folder]:
    if parent_id is not None:
        get_owned_folder(db, user, parent_id)
    return list(
        db.scalars(
            select(Folder)
            .where(Folder.user_id == user.id, Folder.parent_id == parent_id)
            .order_by(Folder.name.asc(), Folder.id.asc())
        )
    )


def get_folder_contents(
    db: Session,
    user: User,
    folder_id: int,
) -> tuple[Folder, list[Folder], list[File], list[Folder]]:
    folder = get_owned_folder(db, user, folder_id)
    children = list(
        db.scalars(
            select(Folder)
            .where(
                Folder.user_id == user.id,
                Folder.parent_id == folder.id,
            )
            .order_by(Folder.name.asc(), Folder.id.asc())
        )
    )
    files = list(
        db.scalars(
            select(File)
            .where(File.user_id == user.id, File.folder_id == folder.id)
            .order_by(File.original_name.asc(), File.id.asc())
        )
    )

    chain: list[Folder] = []
    current = folder
    while current.parent_id is not None:
        parent = db.scalar(
            select(Folder).where(
                Folder.id == current.parent_id,
                Folder.user_id == user.id,
            )
        )
        if parent is None:
            break
        chain.append(parent)
        current = parent
    chain.reverse()
    return folder, children, files, chain


def rename_folder(
    db: Session,
    user: User,
    folder_id: int,
    *,
    name: str,
) -> Folder:
    folder = get_owned_folder(db, user, folder_id)
    folder.name = sanitize_filename(name)
    try:
        db.commit()
        db.refresh(folder)
    except IntegrityError as exc:
        db.rollback()
        raise AppError(
            409,
            "DUPLICATE_NAME",
            "A folder with this name already exists here.",
        ) from exc
    return folder


def delete_folder(
    db: Session,
    user: User,
    folder_id: int,
    *,
    recursive: bool,
    storage: SupabaseStorage,
) -> None:
    folder = get_owned_folder(db, user, folder_id)
    descendants = _descendant_ids(db, user.id, folder.id)
    folder_ids = [folder.id, *descendants]

    file_records = list(
        db.scalars(select(File).where(File.user_id == user.id, File.folder_id.in_(folder_ids)))
    )
    if not recursive and (descendants or file_records):
        raise AppError(
            409,
            "FOLDER_NOT_EMPTY",
            "The folder is not empty. Use recursive=true to delete it.",
        )

    keys = [record.storage_key for record in file_records]
    total_size = sum(record.size for record in file_records)
    if file_records:
        db.execute(delete(File).where(File.id.in_([record.id for record in file_records])))
    db.execute(delete(Folder).where(Folder.id.in_(folder_ids)))
    if total_size:
        db.execute(
            update(User)
            .where(User.id == user.id)
            .values(used_bytes=User.used_bytes - total_size)
        )
    db.commit()

    for key in keys:
        try:
            storage.delete(key)
        except StorageError:
            logger.exception("Failed to delete object after folder deletion.")


def _descendant_ids(db: Session, user_id: int, folder_id: int) -> list[int]:
    descendants: list[int] = []
    pending = [folder_id]
    while pending:
        children = list(
            db.scalars(
                select(Folder.id).where(
                    Folder.user_id == user_id,
                    Folder.parent_id.in_(pending),
                )
            )
        )
        descendants.extend(children)
        pending = children
    return descendants
