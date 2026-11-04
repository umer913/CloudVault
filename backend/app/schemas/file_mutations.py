from pydantic import BaseModel, Field


class FilePatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    folder_id: int | None = None
