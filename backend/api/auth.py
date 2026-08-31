"""Registration + login. Every other route requires the bearer token issued here."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session as DbSession

from backend.api.deps import get_db
from backend.core.config import settings
from backend.core.rate_limit import limiter
from backend.core.security import create_access_token
from backend.schemas.auth import Token, UserCreate, UserOut
from backend.services import user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: DbSession = Depends(get_db)):
    try:
        user = user_service.register_user(db, payload.email, payload.password)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    return user.to_dict()


@router.post("/login", response_model=Token)
@limiter.limit(settings.rate_limit_login)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: DbSession = Depends(get_db)):
    # OAuth2PasswordRequestForm's field is called "username" by spec; we authenticate by email.
    user = user_service.authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(subject=user.id))
