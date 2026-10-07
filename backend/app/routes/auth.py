"""Local username/password authentication endpoints."""

import hmac
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import (
    authenticate_credentials,
    create_access_token,
    get_current_user,
    hash_password,
)
from ..config import config
from ..database import get_db, utc_now
from ..models.sql_models import User
from ..utils.security import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=512)


class BootstrapRequest(Credentials):
    bootstrap_token: str = Field(min_length=1, max_length=512)


class UserResponse(BaseModel):
    id: int
    identifier: str
    name: str
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


def _normalize(identifier: str) -> str:
    return identifier.strip().lower()


def _safe_user(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        identifier=user.login_identifier or "",
        name=user.name,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
@limiter.limit("5/minute")
def register(request: Request, credentials: Credentials, db: Session = Depends(get_db)):
    identifier = _normalize(credentials.identifier)
    if db.query(User).filter(User.login_identifier == identifier).first() is not None:
        raise HTTPException(
            status_code=409, detail="Registration could not be completed"
        )
    user = User(
        name=identifier.split("@", 1)[0][:100],
        login_identifier=identifier,
        password_hash=hash_password(credentials.password),
        is_active=True,
        created_at=utc_now(),
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Registration could not be completed"
        ) from exc
    return _safe_user(user)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, credentials: Credentials, db: Session = Depends(get_db)):
    user = authenticate_credentials(db, credentials.identifier, credentials.password)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token, expires_in = create_access_token(user.id)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return _safe_user(user)


@router.post("/bootstrap", response_model=UserResponse)
@limiter.limit("3/hour")
def bootstrap(
    request: Request, credentials: BootstrapRequest, db: Session = Depends(get_db)
):
    if not config.auth_bootstrap_token or not hmac.compare_digest(
        credentials.bootstrap_token, config.auth_bootstrap_token
    ):
        raise HTTPException(status_code=404, detail="Bootstrap unavailable")
    legacy_users = (
        db.query(User)
        .filter(User.login_identifier.is_(None))
        .order_by(User.id.asc())
        .all()
    )
    if len(legacy_users) != 1:
        raise HTTPException(status_code=409, detail="Bootstrap is not available")
    user = legacy_users[0]
    user.login_identifier = _normalize(credentials.identifier)
    user.password_hash = hash_password(credentials.password)
    user.is_active = True
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Bootstrap could not be completed"
        ) from exc
    return _safe_user(user)
