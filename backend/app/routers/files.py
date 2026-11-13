import base64
import binascii
from datetime import datetime, timedelta, timezone
import tempfile
import uuid
from urllib.parse import quote

import jwt
from fastapi import (
    APIRouter,
    Depends,
    File as UploadFileField,
    Form,
    Header,
    Query,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.errors import AppError
from app.models import Folder, User
from app.models import UploadSession
from app.schemas.file_list import FileListOut
from app.schemas.direct_upload import (
    DirectUploadCompleteIn,
    DirectUploadStartIn,
    DirectUploadStartOut,
)
from app.schemas.file_mutations import FilePatchIn
from app.schemas.files import FileOut
from app.services.file_service import (
    complete_direct_upload,
    delete_file,
    get_owned_file,
    list_files,
    _inspect_upload,
    update_file,
    upload_file,
)
from app.services.active_storage import create_storage
from app.services.b2_storage_service import B2Storage
from app.services.supabase_storage_service import StorageError
from app.services.upload_progress import (
    finish_upload,
    get_upload,
    start_upload,
    update_upload,
)
from app.utils.dependencies import get_current_user
from app.utils.security import ALGORITHM
from app.utils.validation import validate_upload_header


router = APIRouter()


def SupabaseStorage():
    return create_storage()


def _direct_upload_token(*, user_id: int, session_id: str) -> str:
    return jwt.encode(
        {
            "typ": "direct-upload",
            "sub": str(user_id),
            "session_id": session_id,
            "exp": datetime.now(timezone.utc)
            + timedelta(minutes=settings.DIRECT_UPLOAD_SESSION_TTL_MINUTES),
        },
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )


def _direct_upload_payload(token: str, user: User) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        if payload.get("typ") != "direct-upload" or int(payload["sub"]) != user.id:
            raise ValueError
        return payload
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise AppError(
            400,
            "INVALID_UPLOAD_TOKEN",
            "The direct upload session is invalid or expired.",
        ) from exc


@router.post("/direct-upload/start", response_model=DirectUploadStartOut)
def start_direct_upload(
    body: DirectUploadStartIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DirectUploadStartOut:
    if body.size > settings.MAX_UPLOAD_BYTES:
        raise AppError(413, "FILE_TOO_LARGE", "The file exceeds the maximum upload size.")
    if body.folder_id is not None and db.scalar(
        select(Folder).where(
            Folder.id == body.folder_id,
            Folder.user_id == user.id,
        )
    ) is None:
        raise AppError(404, "FOLDER_NOT_FOUND", "Folder not found.")

    content_head = body.content_head
    try:
        head = base64.b64decode(content_head, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AppError(422, "INVALID_UPLOAD", "The upload header is invalid.") from exc

    validated = validate_upload_header(body.filename, head)
    storage = SupabaseStorage()
    if not isinstance(storage, B2Storage):
        storage.close()
        raise AppError(
            409,
            "DIRECT_UPLOAD_UNAVAILABLE",
            "Direct uploads require Backblaze B2 storage.",
        )

    storage_key = f"{user.id}/{uuid.uuid4().hex}.bin"
    upload_id: str | None = None
    try:
        upload_id = storage.create_multipart_upload(
            storage_key,
            content_type=validated.mime_type,
        )
        part_size = settings.B2_MULTIPART_CHUNK_BYTES
        part_count = (body.size + part_size - 1) // part_size
        parts = [
            {
                "part_number": part_number,
                "url": storage.create_part_url(
                    storage_key,
                    upload_id=upload_id,
                    part_number=part_number,
                ),
            }
            for part_number in range(1, part_count + 1)
        ]
        session_id = str(uuid.uuid4())
        db.add(
            UploadSession(
                id=session_id,
                user_id=user.id,
                storage_key=storage_key,
                provider_upload_id=upload_id,
                filename=validated.original_name,
                extension=validated.extension,
                mime_type=validated.mime_type,
                size=body.size,
                folder_id=body.folder_id,
                status="active",
                expires_at=datetime.now(timezone.utc)
                + timedelta(minutes=settings.DIRECT_UPLOAD_SESSION_TTL_MINUTES),
            )
        )
        db.commit()
        token = _direct_upload_token(user_id=user.id, session_id=session_id)
        return DirectUploadStartOut(token=token, part_size=part_size, parts=parts)
    except StorageError as exc:
        if upload_id is not None:
            try:
                storage.abort_multipart_upload(
                    storage_key,
                    upload_id=upload_id,
                )
            except StorageError:
                pass
        raise AppError(502, "STORAGE_UNAVAILABLE", "File storage is temporarily unavailable.") from exc
    except SQLAlchemyError:
        db.rollback()
        if upload_id is not None:
            try:
                storage.abort_multipart_upload(
                    storage_key,
                    upload_id=upload_id,
                )
            except StorageError:
                pass
        raise
    finally:
        storage.close()


@router.post("/direct-upload/complete", response_model=FileOut, status_code=201)
def complete_direct_upload_route(
    body: DirectUploadCompleteIn,
    token: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileOut:
    payload = _direct_upload_payload(token, user)
    session = db.get(UploadSession, payload.get("session_id"))
    if session is None or session.user_id != user.id:
        raise AppError(400, "INVALID_UPLOAD_TOKEN", "The direct upload session is invalid.")
    if session.status != "active":
        raise AppError(409, "UPLOAD_SESSION_CLOSED", "The upload session is no longer active.")
    if session.expires_at <= datetime.now(timezone.utc):
        session.status = "expired"
        db.commit()
        raise AppError(410, "UPLOAD_SESSION_EXPIRED", "The upload session has expired.")
    session.status = "completing"
    db.commit()
    expected_parts = (
        session.size + settings.B2_MULTIPART_CHUNK_BYTES - 1
    ) // settings.B2_MULTIPART_CHUNK_BYTES
    parts = sorted(body.parts, key=lambda part: part.part_number)
    if [part.part_number for part in parts] != list(range(1, expected_parts + 1)):
        session.status = "active"
        db.commit()
        raise AppError(422, "INVALID_UPLOAD_PARTS", "All upload parts are required in order.")

    storage = SupabaseStorage()
    if not isinstance(storage, B2Storage):
        storage.close()
        raise AppError(409, "DIRECT_UPLOAD_UNAVAILABLE", "Direct uploads require Backblaze B2 storage.")
    try:
        storage.complete_multipart_upload(
            session.storage_key,
            upload_id=session.provider_upload_id,
            parts=[
                {"PartNumber": part.part_number, "ETag": part.etag}
                for part in parts
            ],
        )
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as content:
            stored_size = 0
            for chunk in storage.iter_download(session.storage_key):
                content.write(chunk)
                stored_size += len(chunk)
            if stored_size != session.size:
                raise AppError(
                    502,
                    "STORAGE_CORRUPTED",
                    "The stored upload size does not match the original file.",
                )
            validated, checked_size, checksum = _inspect_upload(
                session.filename,
                content,
            )
            if checked_size != session.size:
                raise AppError(
                    422,
                    "INVALID_UPLOAD",
                    "The uploaded file content is invalid.",
                )
        record = complete_direct_upload(
            db,
            user,
            filename=session.filename,
            size=session.size,
            folder_id=session.folder_id,
            mime_type=validated.mime_type,
            extension=validated.extension,
            storage_key=session.storage_key,
            checksum=checksum,
        )
        session.status = "completed"
        db.commit()
        return record
    except StorageError as exc:
        try:
            storage.delete(session.storage_key)
        except StorageError:
            try:
                storage.abort_multipart_upload(
                    session.storage_key,
                    upload_id=session.provider_upload_id,
                )
            except StorageError:
                pass
        raise AppError(502, "STORAGE_UNAVAILABLE", "File storage is temporarily unavailable.") from exc
    except AppError:
        try:
            storage.delete(session.storage_key)
        except StorageError:
            pass
        raise
    except SQLAlchemyError:
        try:
            storage.delete(session.storage_key)
        except StorageError:
            pass
        raise
    finally:
        storage.close()


@router.post("/direct-upload/abort", status_code=204)
def abort_direct_upload(
    token: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    payload = _direct_upload_payload(token, user)
    session = db.get(UploadSession, payload.get("session_id"))
    if session is None or session.user_id != user.id:
        raise AppError(400, "INVALID_UPLOAD_TOKEN", "The direct upload session is invalid.")
    if session.status in {"completed", "aborted", "expired"}:
        return
    storage = SupabaseStorage()
    if not isinstance(storage, B2Storage):
        storage.close()
        return
    try:
        storage.abort_multipart_upload(
        session.storage_key,
        upload_id=session.provider_upload_id,
        )
        session.status = "aborted"
        db.commit()
    except StorageError as exc:
        raise AppError(502, "STORAGE_UNAVAILABLE", "File storage is temporarily unavailable.") from exc
    finally:
        storage.close()


@router.get("", response_model=FileListOut)
def list_user_files(
    folder_id: int | None = Query(default=None),
    q: str | None = Query(default=None, max_length=255),
    type: str | None = Query(default=None, alias="type"),
    sort: str = Query(default="created_at"),
    order: str = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileListOut:
    if type not in {None, "documents", "images", "archives", "data"}:
        raise AppError(422, "INVALID_TYPE", "Unsupported file type filter.")
    if sort not in {"name", "created_at", "size"}:
        raise AppError(422, "INVALID_SORT", "Unsupported sort field.")
    if order not in {"asc", "desc"}:
        raise AppError(422, "INVALID_ORDER", "Order must be asc or desc.")

    items, total = list_files(
        db,
        user,
        folder_id=folder_id,
        query=q,
        file_type=type,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    return FileListOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/{file_id}", response_model=FileOut)
def get_file(
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileOut:
    return get_owned_file(db, user, file_id)


@router.get("/{file_id}/download")
def download_file(
    file_id: int,
    inline: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    record = get_owned_file(db, user, file_id)
    if inline and record.extension not in {"pdf", "png", "jpg", "jpeg", "txt"}:
        raise AppError(
            422,
            "PREVIEW_NOT_SUPPORTED",
            "This file type cannot be previewed.",
        )

    storage = SupabaseStorage()
    try:
        if not storage.exists(record.storage_key):
            storage.close()
            raise AppError(404, "FILE_NOT_FOUND", "File not found.")
    except StorageError as exc:
        storage.close()
        raise AppError(
            502,
            "STORAGE_UNAVAILABLE",
            "File storage is temporarily unavailable.",
        ) from exc

    disposition = "inline" if inline else "attachment"
    safe_filename = quote(record.original_name, safe="")

    def body():
        try:
            yield from storage.iter_download(record.storage_key)
        finally:
            storage.close()

    return StreamingResponse(
        body(),
        media_type=record.mime_type,
        headers={
            "Content-Disposition": (
                f"{disposition}; filename*=UTF-8''{safe_filename}"
            ),
            "Content-Length": str(record.size),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{file_id}/signed-url")
def signed_url(
    file_id: int,
    inline: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    record = get_owned_file(db, user, file_id)
    if inline and record.extension not in {"pdf", "png", "jpg", "jpeg", "txt"}:
        raise AppError(
            422,
            "PREVIEW_NOT_SUPPORTED",
            "This file type cannot be previewed.",
        )
    storage = SupabaseStorage()
    try:
        if not storage.exists(record.storage_key):
            raise AppError(404, "FILE_NOT_FOUND", "File not found.")
        return {
            "url": storage.create_signed_url(
                record.storage_key,
                expires_in=300,
                download_filename=None if inline else record.original_name,
            )
        }
    except StorageError as exc:
        raise AppError(
            502,
            "STORAGE_UNAVAILABLE",
            "File storage is temporarily unavailable.",
        ) from exc
    finally:
        storage.close()


@router.patch("/{file_id}", response_model=FileOut)
def patch_file(
    file_id: int,
    body: FilePatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileOut:
    changes = body.model_dump(exclude_unset=True)
    return update_file(
        db,
        user,
        file_id,
        name=changes.get("name"),
        folder_id=changes.get("folder_id"),
        folder_id_provided="folder_id" in changes,
    )


@router.delete("/{file_id}", status_code=204)
def remove_file(
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    with SupabaseStorage() as storage:
        delete_file(db, user, file_id, storage)


@router.post("/upload", response_model=FileOut, status_code=201)
def upload(
    file: UploadFile = UploadFileField(...),
    folder_id: int | None = Form(default=None),
    x_upload_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileOut:
    if not file.filename:
        raise AppError(422, "INVALID_FILENAME", "A filename is required.")

    if x_upload_id:
        start_upload(x_upload_id, user.id)

    def report_progress(loaded: int, total: int, phase: str) -> None:
        if x_upload_id:
            update_upload(x_upload_id, loaded=loaded, total=total, phase=phase)

    with SupabaseStorage() as storage:
        record = upload_file(
            db,
            user,
            filename=file.filename,
            content=file.file,
            folder_id=folder_id,
            storage=storage,
            progress_callback=report_progress,
        )
    if x_upload_id:
        update_upload(x_upload_id, loaded=1, total=1, phase="complete")
        finish_upload(x_upload_id, complete=True)
    return record


@router.get("/upload-progress/{upload_id}")
def upload_progress(
    upload_id: str,
    user: User = Depends(get_current_user),
) -> dict[str, object]:
    progress = get_upload(upload_id, user.id)
    if progress is None:
        raise AppError(404, "UPLOAD_NOT_FOUND", "Upload progress was not found.")
    return {
        "loaded": progress.loaded,
        "total": progress.total,
        "phase": progress.phase,
        "complete": progress.complete,
    }