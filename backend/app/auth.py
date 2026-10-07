"""Authentication primitives and the authenticated-user boundary."""

from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, WebSocket, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from .config import config
from .database import get_db
from .models.sql_models import User

password_hasher = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return password_hasher.verify(password, password_hash)
    except Exception:
        return False


def _auth_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_access_token(user_id: int) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires_in = config.access_token_expire_minutes * 60
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "type": "access",
    }
    return jwt.encode(payload, config.auth_secret_key, algorithm="HS256"), expires_in


def _decode_access_token(token: str) -> int:
    try:
        payload = jwt.decode(token, config.auth_secret_key, algorithms=["HS256"])
    except (jwt.InvalidTokenError, TypeError, ValueError) as exc:
        raise _auth_error() from exc
    if payload.get("type") != "access":
        raise _auth_error()
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdigit() or int(subject) <= 0:
        raise _auth_error()
    return int(subject)


def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise _auth_error()
    user_id = _decode_access_token(token)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise _auth_error()
    return user


def get_current_user_id(user: User = Depends(get_current_user)) -> int:
    return user.id


def authenticate_credentials(
    db: Session, identifier: str, password: str
) -> User | None:
    normalized = identifier.strip().lower()
    user = db.query(User).filter(User.login_identifier == normalized).first()
    if (
        user is None
        or not verify_password(password, user.password_hash)
        or not user.is_active
    ):
        return None
    return user


async def authenticate_websocket(websocket: WebSocket, db: Session) -> User:
    header = websocket.headers.get("authorization", "")
    token = (
        header[7:].strip()
        if header.lower().startswith("bearer ")
        else websocket.query_params.get("token")
    )
    if not token:
        await websocket.close(code=1008)
        raise _auth_error()
    try:
        user_id = _decode_access_token(token)
    except HTTPException:
        await websocket.close(code=1008)
        raise
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        await websocket.close(code=1008)
        raise _auth_error()
    return user
