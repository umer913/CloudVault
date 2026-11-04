from fastapi import APIRouter, Depends

from app.models import User
from app.schemas.storage import StorageUsageOut
from app.utils.dependencies import get_current_user


router = APIRouter()


@router.get("/usage", response_model=StorageUsageOut)
def usage(user: User = Depends(get_current_user)) -> StorageUsageOut:
    remaining = max(user.storage_quota - user.used_bytes, 0)
    percent = (
        (user.used_bytes / user.storage_quota) * 100
        if user.storage_quota
        else 0.0
    )
    return StorageUsageOut(
        used_bytes=user.used_bytes,
        quota_bytes=user.storage_quota,
        remaining_bytes=remaining,
        percent_used=round(percent, 2),
    )
