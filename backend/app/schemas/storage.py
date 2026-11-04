from pydantic import BaseModel


class StorageUsageOut(BaseModel):
    used_bytes: int
    quota_bytes: int
    remaining_bytes: int
    percent_used: float
