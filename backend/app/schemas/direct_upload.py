from pydantic import BaseModel, Field


class DirectUploadStartIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=1)
    folder_id: int | None = None
    content_head: str = Field(min_length=1, max_length=12_000)


class DirectUploadStartOut(BaseModel):
    token: str
    part_size: int
    parts: list[dict[str, int | str]]


class DirectUploadPart(BaseModel):
    part_number: int = Field(ge=1, le=10_000)
    etag: str = Field(min_length=1, max_length=200)


class DirectUploadCompleteIn(BaseModel):
    parts: list[DirectUploadPart] = Field(min_length=1, max_length=10_000)
