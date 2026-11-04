from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import File, User
from app.services.supabase_storage_service import StorageError, SupabaseStorage


@dataclass(frozen=True)
class CleanupReport:
    scanned: int
    orphaned: int
    deleted: int


def cleanup_orphan_objects(
    db: Session,
    storage: SupabaseStorage,
    *,
    dry_run: bool = True,
    page_size: int = 1000,
) -> CleanupReport:
    """Find server-managed objects without file metadata.

    Only objects beneath user IDs that still exist in the database are
    considered. This avoids deleting unrelated objects in a shared bucket.
    """
    known_keys = set(db.scalars(select(File.storage_key)))
    scanned = 0
    orphaned = 0
    deleted = 0

    user_ids = db.scalars(select(User.id)).all()
    for user_id in user_ids:
        offset = 0
        while True:
            objects = storage.list_objects(
                prefix=f"{user_id}/",
                limit=page_size,
                offset=offset,
            )
            if not objects:
                break

            for item in objects:
                name = item.get("name")
                if not isinstance(name, str):
                    continue
                key = name if name.startswith(f"{user_id}/") else f"{user_id}/{name}"
                try:
                    storage.validate_key(key)
                except StorageError:
                    continue

                scanned += 1
                if key in known_keys:
                    continue
                orphaned += 1
                if not dry_run:
                    storage.delete(key)
                    deleted += 1

            if len(objects) < page_size:
                break
            offset += page_size

    return CleanupReport(scanned=scanned, orphaned=orphaned, deleted=deleted)
