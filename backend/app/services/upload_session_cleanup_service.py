from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UploadSession
from app.services.b2_storage_service import B2Storage
from app.services.supabase_storage_service import StorageError


@dataclass(frozen=True)
class UploadSessionCleanupReport:
    scanned: int
    expired: int
    aborted: int
    failed: int


def cleanup_upload_sessions(
    db: Session,
    storage: B2Storage,
    *,
    dry_run: bool = True,
) -> UploadSessionCleanupReport:
    now = datetime.now(timezone.utc)
    sessions = list(
        db.scalars(
            select(UploadSession).where(
                UploadSession.status.in_(("active", "completing")),
                UploadSession.expires_at <= now,
            )
        )
    )
    expired = 0
    aborted = 0
    failed = 0

    for session in sessions:
        expired += 1
        if dry_run:
            continue
        try:
            storage.abort_multipart_upload(
                session.storage_key,
                upload_id=session.provider_upload_id,
            )
            session.status = "expired"
            aborted += 1
        except StorageError:
            failed += 1

    if not dry_run:
        db.commit()
    return UploadSessionCleanupReport(
        scanned=len(sessions),
        expired=expired,
        aborted=aborted,
        failed=failed,
    )
