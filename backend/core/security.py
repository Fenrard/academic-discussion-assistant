"""
Password hashing + JWT issuing/verification, and the get_current_user
dependency every route now requires. FastAPI's own documented pattern
(OAuth2PasswordBearer + JWT) — nothing bespoke.

Uses the `bcrypt` library directly rather than passlib's CryptContext:
passlib 1.7.4 (last released 2020, unmaintained) breaks against bcrypt
>=4.1's changed version metadata (`AttributeError: module 'bcrypt' has
no attribute '__about__'`) — confirmed against the bcrypt version this
project installs. Calling bcrypt directly avoids depending on a known-
broken compatibility shim.
"""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session as DbSession

from backend.database.db import get_db
from backend.models.user import User

# In production this MUST be set via env var — a random default here would
# silently issue tokens no restart could invalidate consistently across
# multiple worker processes. Fails loudly instead of guessing wrong.
_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12  # 12h — mobile app, not a browser session

_BCRYPT_MAX_BYTES = 72  # bcrypt's own hard limit

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def _get_secret_key() -> str:
    if not _SECRET_KEY:
        raise RuntimeError(
            "JWT_SECRET_KEY environment variable is not set. Generate one with "
            "'python -c \"import secrets; print(secrets.token_hex(32))\"' and set it "
            "before starting the server — auth cannot run with no key."
        )
    return _SECRET_KEY


def hash_password(plain_password: str) -> str:
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {"sub": subject, "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, _get_secret_key(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    """Returns the subject (user id) from a valid token, or raises jwt's own exceptions."""
    payload = jwt.decode(token, _get_secret_key(), algorithms=[JWT_ALGORITHM])
    return payload["sub"]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(token: str | None = Depends(oauth2_scheme), db: DbSession = Depends(get_db)) -> User:
    if token is None:
        raise _unauthorized("Not authenticated.")

    try:
        user_id = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token has expired.")
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid token.")

    user = db.get(User, user_id)
    if user is None:
        raise _unauthorized("User no longer exists.")
    return user


def get_current_user_from_token_string(token: str, db: DbSession) -> User:
    """Same as get_current_user, for the WebSocket path — no Depends() chain available there."""
    if not token:
        raise ValueError("No token provided.")
    user_id = decode_access_token(token)  # lets jwt's exceptions propagate; caller decides how to respond
    user = db.get(User, user_id)
    if user is None:
        raise ValueError("User no longer exists.")
    return user
