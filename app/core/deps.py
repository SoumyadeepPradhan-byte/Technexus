"""
app/core/deps.py  –  "DEPENDENCIES": WHO IS CALLING, AND ARE THEY ALLOWED?
============================================================================
FastAPI's `Depends(...)` lets us say "before running this endpoint, run this helper
and give me its result". We use it for login checks:

    user: User = Depends(get_current_user)            → any logged-in user
    user: User = Depends(require_roles("doctor"))     → only doctors (and admin)

If the check fails, FastAPI returns 401 (not logged in) or 403 (wrong role) and the
endpoint body never runs. This is the whole "role-based access" feature.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_token
from app.models.core import User

# Tells Swagger where the login form posts to, so the green "Authorize" button works.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_PREFIX}/auth/token")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """Read the token from the Authorization header → look the user up in the DB → return them."""
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def require_roles(*roles: str):
    """
    A function that BUILDS a dependency. `require_roles("doctor", "health_worker")` returns a
    checker that only lets those roles through. Admin is always allowed.
    """

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role != "admin" and user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role: {', '.join(roles)}")
        return user

    return checker
