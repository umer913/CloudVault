from pydantic import BaseModel

from app.schemas.files import FileOut


class FileListOut(BaseModel):
    items: list[FileOut]
    total: int
    limit: int
    offset: int
