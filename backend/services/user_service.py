"""User account persistence + authentication — the app-login half, distinct from teacher voice enrollment."""

from sqlalchemy.orm import Session as DbSession

from backend.core.security import hash_password, verify_password
from backend.models.user import User


def get_user_by_email(db: DbSession, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def register_user(db: DbSession, email: str, password: str) -> User:
    if get_user_by_email(db, email) is not None:
        raise ValueError(f"An account with email '{email}' already exists.")

    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: DbSession, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user
