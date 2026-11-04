from datetime import timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas.shares import ShareCreateIn, ShareCreatedOut, ShareOut
from app.services.share_service import (
    create_share,
    get_owned_share,
    list_owned_shares,
    revoke_share,
)
from app.utils.dependencies import get_current_user

router = APIRouter()


@router.post("", response_model=ShareCreatedOut, status_code=201)
def create(
    body: ShareCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ShareCreatedOut:
    share, token = create_share(
        db,
        user,
        file_id=body.file_id,
        permission=body.permission,
        expires_at=body.expires_at,
        password=body.password,
    )
    return ShareCreatedOut(
        id=share.id,
        file_id=share.file_id,
        permission=share.permission,
        expires_at=share.expires_at,
        revoked_at=share.revoked_at,
        created_at=share.created_at,
        token=token,
    )


@router.get("", response_model=list[ShareOut])
def list_shares(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ShareOut]:
    return list_owned_shares(db, user)


@router.get("/{share_id}", response_model=ShareOut)
def get_share(
    share_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ShareOut:
    return get_owned_share(db, user, share_id)


@router.delete("/{share_id}", status_code=204)
def revoke(
    share_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    revoke_share(db, user, share_id)
