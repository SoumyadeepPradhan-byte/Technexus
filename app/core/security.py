"""
app/core/security.py  –  PASSWORDS AND LOGIN TOKENS
=====================================================
Two jobs:

1. Passwords are NEVER stored as plain text. We store a bcrypt *hash* - a scrambled
   version that can't be reversed. On login we hash what the user typed and compare.

2. After a successful login we hand the user a JWT (JSON Web Token) - a signed string
   that says "user 5, role planner, valid until 6pm". The frontend sends it back on
   every request in the header   Authorization: Bearer <token>   and we trust it
   because only we know SECRET_KEY, so nobody else can forge one.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:      # malformed hash in the DB → treat as wrong password, don't crash
        return False


def create_access_token(sub: str, role: str) -> str:
    """`sub` (subject) = the user id as a string. Standard JWT naming."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": sub, "role": role, "exp": expire}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    """Raises an exception if the token is fake, tampered with, or expired."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
