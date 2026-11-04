from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File as UploadFileField,
    Form,
    Query,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AppError
from app.models import User
from app.schemas.file_list import FileListOut
from app.schemas.file_mutations import FilePatchIn
from app.schemas.files import FileOut
from app.services.file_service import (
    delete_file,
    get_owned_file,
    list_files,
    update_file,
    upload_file,
)
from app.services.supabase_storage_service import StorageError, SupabaseStorage
from app.utils.dependencies import get_current_user


router = APIRouter()


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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileOut:
    if not file.filename:
        raise AppError(422, "INVALID_FILENAME", "A filename is required.")

    with SupabaseStorage() as storage:
        record = upload_file(
            db,
            user,
            filename=file.filename,
            content=file.file,
            folder_id=folder_id,
            storage=storage,
        )
    return record