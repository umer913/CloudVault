from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.files import FileOut


class FolderCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: int | None = None


class FolderPatchIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class FolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parent_id: int | None
    created_at: datetime


class FolderContentsOut(FolderOut):
    breadcrumbs: list[FolderOut]
    folders: list[FolderOut]
    files: list[FileOut]
