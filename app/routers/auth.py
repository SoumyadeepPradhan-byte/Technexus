"""
app/routers/auth.py  –  LOGIN, REGISTER, WHO-AM-I
==================================================
Rural users log in with PHONE NUMBER + a short PIN (email is optional). Tokens last 30 days
so nobody is forced to re-login on a weak network.

    /auth/login  - JSON body {phone_or_email, password}  → for the app
    /auth/token  - form body, only so Swagger's "Authorize" button works (hidden from docs)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.models.core import ROLES
from app.schemas import LoginRequest, TokenOut, UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["Auth & Users"])


def _login(db: Session, ident: str, password: str) -> TokenOut:
    ident = ident.strip().lower()
    user = db.query(User).filter(or_(User.phone == ident, User.email == ident)).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid phone/email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")
    return TokenOut(access_token=create_access_token(str(user.id), user.role), user=UserOut.model_validate(user))


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: UserCreate, db: Session = Depends(get_db)):
    if data.role not in ROLES:
        raise HTTPException(400, f"role must be one of {ROLES}")
    if db.query(User).filter(User.phone == data.phone).first():
        raise HTTPException(409, "Phone already registered")
    user = User(name=data.name, phone=data.phone, email=(data.email or "").lower() or None,
                hashed_password=hash_password(data.password), role=data.role,
                preferred_language=data.preferred_language, region_id=data.region_id)
    db.add(user); db.commit(); db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    """JSON login with phone number or email."""
    return _login(db, data.phone_or_email, data.password)


@router.post("/token", response_model=TokenOut, include_in_schema=False)
def token(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    return _login(db, form.username, form.password)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(role: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_roles("hospital_admin"))):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    return q.all()


@router.get("/roles")
def roles():
    return {"roles": list(ROLES)}
