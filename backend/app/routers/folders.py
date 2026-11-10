from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AppError
from app.models import File, Folder, User
from app.schemas.folders import (
    FolderContentsOut,
    FolderCreateIn,
    FolderOut,
    FolderPatchIn,
    FolderTreeOut,
)
from app.schemas.files import FileOut
from app.services.folder_service import (
    create_folder,
    delete_folder,
    get_folder_contents,
    get_owned_folder,
    list_folders,
    rename_folder,
)
from app.services.active_storage import create_storage
from app.utils.dependencies import get_current_user


router = APIRouter()


def SupabaseStorage():
    return create_storage()


@router.post("", response_model=FolderOut, status_code=201)
def create(
    body: FolderCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FolderOut:
    return create_folder(
        db,
        user,
        name=body.name,
        parent_id=body.parent_id,
    )


@router.get("", response_model=list[FolderOut])
def list_children(
    parent_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FolderOut]:
    return list_folders(db, user, parent_id=parent_id)


@router.get("/tree", response_model=list[FolderTreeOut])
def list_tree(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FolderTreeOut]:
    folders = list(db.scalars(
        select(Folder)
        .where(Folder.user_id == user.id)
        .order_by(Folder.parent_id.asc(), Folder.name.asc(), Folder.id.asc())
    ))
    files = list(db.scalars(
        select(File)
        .where(File.user_id == user.id, File.folder_id.is_not(None))
        .order_by(File.original_name.asc(), File.id.asc())
    ))
    files_by_folder: dict[int, list[File]] = {}
    for file in files:
        files_by_folder.setdefault(file.folder_id, []).append(file)
    return [
        FolderTreeOut(
            **FolderOut.model_validate(folder).model_dump(),
            files=[
                FileOut.model_validate(file)
                for file in files_by_folder.get(folder.id, [])
            ],
        )
        for folder in folders
    ]


@router.get("/{folder_id}", response_model=FolderContentsOut)
def get_contents(
    folder_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FolderContentsOut:
    folder, children, files, breadcrumbs = get_folder_contents(
        db, user, folder_id
    )
    return FolderContentsOut(
        id=folder.id,
        name=folder.name,
        parent_id=folder.parent_id,
        created_at=folder.created_at,
        breadcrumbs=[
            FolderOut.model_validate(item) for item in breadcrumbs
        ],
        folders=[FolderOut.model_validate(item) for item in children],
        files=files,
    )


@router.patch("/{folder_id}", response_model=FolderOut)
def rename(
    folder_id: int,
    body: FolderPatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FolderOut:
    return rename_folder(db, user, folder_id, name=body.name)


@router.delete("/{folder_id}", status_code=204)
def remove(
    folder_id: int,
    recursive: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    with SupabaseStorage() as storage:
        delete_folder(
            db,
            user,
            folder_id,
            recursive=recursive,
            storage=storage,
        )
