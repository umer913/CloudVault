from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ShareCreateIn(BaseModel):
    file_id: int
    permission: str
    expires_at: datetime
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_values(self) -> "ShareCreateIn":
        if self.permission not in {"view", "download"}:
            raise ValueError("permission must be view or download")
        return self


class ShareOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_id: int
    original_name: str
    permission: str
    expires_at: datetime
    revoked_at: datetime | None
    created_at: datetime


class ShareCreatedOut(ShareOut):
    token: str


class PublicShareOut(BaseModel):
    file_id: int
    original_name: str
    size: int
    mime_type: str
    permission: str
    expires_at: datetime
    password_required: bool
