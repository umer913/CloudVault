from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AppError
from app.models import User
from app.rate_limit import limiter
from app.schemas.auth import RegisterIn, TokenOut, UserOut
from app.utils.dependencies import get_current_user
from app.utils.security import (
    DUMMY_HASH,
    create_access_token,
    hash_password,
    verify_password,
)


router = APIRouter()


@router.post("/register", response_model=UserOut, status_code=201)
@limiter.limit("20/minute")
def register(
    request: Request,
    body: RegisterIn,
    db: Session = Depends(get_db),
) -> User:
    email = str(body.email).strip().lower()
    email_taken = AppError(
        409,
        "EMAIL_TAKEN",
        "This email is already registered.",
    )

    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise email_taken

    user = User(
        name=body.name.strip(),
        email=email,
        password_hash=hash_password(body.password),
    )
    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise email_taken

    return user


@router.post("/login", response_model=TokenOut)
@limiter.limit("20/minute")
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenOut:
    email = form.username.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    password_hash = user.password_hash if user is not None else DUMMY_HASH
    valid = verify_password(form.password, password_hash)

    if user is None or not valid:
        raise AppError(
            401,
            "INVALID_CREDENTIALS",
            "Incorrect email or password.",
        )

    return TokenOut(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user