from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AppError
from app.schemas.shares import PublicShareOut
from app.services.share_service import (
    get_public_share,
    verify_share_password,
)
from app.services.active_storage import create_storage
from app.services.supabase_storage_service import StorageError

router = APIRouter()


def SupabaseStorage():
    return create_storage()
_PREVIEWABLE = {"pdf", "png", "jpg", "jpeg", "txt"}


@router.get("/{token}", response_model=PublicShareOut)
def metadata(
    token: str,
    x_share_password: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> PublicShareOut:
    share, file_record = get_public_share(db, token)
    verify_share_password(share, x_share_password)
    return PublicShareOut(
        file_id=file_record.id,
        original_name=file_record.original_name,
        size=file_record.size,
        mime_type=file_record.mime_type,
        permission=share.permission,
        expires_at=share.expires_at,
        password_required=share.password_hash is not None,
    )


@router.get("/{token}/content")
def content(
    token: str,
    inline: bool = Query(default=False),
    x_share_password: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    share, file_record = get_public_share(db, token)
    verify_share_password(share, x_share_password)
    if share.permission == "view":
        inline = True
    if inline and file_record.extension not in _PREVIEWABLE:
        raise AppError(
            422,
            "PREVIEW_NOT_SUPPORTED",
            "This file type cannot be previewed.",
        )

    storage = SupabaseStorage()
    try:
        if not storage.exists(file_record.storage_key):
            storage.close()
            raise AppError(404, "SHARE_NOT_FOUND", "Share not found.")
    except StorageError as exc:
        storage.close()
        raise AppError(
            502,
            "STORAGE_UNAVAILABLE",
            "File storage is temporarily unavailable.",
        ) from exc

    disposition = "inline" if inline else "attachment"
    filename = quote(file_record.original_name, safe="")

    def body():
        try:
            yield from storage.iter_download(file_record.storage_key)
        finally:
            storage.close()

    return StreamingResponse(
        body(),
        media_type=file_record.mime_type,
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{filename}",
            "Content-Length": str(file_record.size),
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "no-store",
        },
    )
