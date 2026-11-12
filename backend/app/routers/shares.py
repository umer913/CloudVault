from datetime import timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas.shares import ShareCreateIn, ShareCreatedOut, ShareOut
from app.services.share_service import (
    create_share,
    get_owned_share_with_name,
    list_owned_shares,
    revoke_share,
    rotate_share_token,
)
from app.utils.dependencies import get_current_user

router = APIRouter()


@router.post("", response_model=ShareCreatedOut, status_code=201)
def create(
    body: ShareCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ShareCreatedOut:
    share, token, original_name = create_share(
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
        original_name=original_name,
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
    return [
        ShareOut(
            id=share.id,
            file_id=share.file_id,
            original_name=original_name,
            permission=share.permission,
            expires_at=share.expires_at,
            revoked_at=share.revoked_at,
            created_at=share.created_at,
        )
        for share, original_name in list_owned_shares(db, user)
    ]


@router.get("/{share_id}", response_model=ShareOut)
def get_share(
    share_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ShareOut:
    share, original_name = get_owned_share_with_name(db, user, share_id)
    return ShareOut(
        id=share.id,
        file_id=share.file_id,
        original_name=original_name,
        permission=share.permission,
        expires_at=share.expires_at,
        revoked_at=share.revoked_at,
        created_at=share.created_at,
    )


@router.post("/{share_id}/link", response_model=ShareCreatedOut)
def rotate_link(
    share_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ShareCreatedOut:
    share, token, original_name = rotate_share_token(db, user, share_id)
    return ShareCreatedOut(
        id=share.id,
        file_id=share.file_id,
        original_name=original_name,
        permission=share.permission,
        expires_at=share.expires_at,
        revoked_at=share.revoked_at,
        created_at=share.created_at,
        token=token,
    )


@router.delete("/{share_id}", status_code=204)
def revoke(
    share_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    revoke_share(db, user, share_id)
