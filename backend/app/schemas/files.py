from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_name: str
    extension: str
    size: int
    mime_type: str
    checksum: str
    folder_id: int | None
    created_at: datetime
    updated_at: datetime