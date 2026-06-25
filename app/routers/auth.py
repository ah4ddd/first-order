from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy import select
from pwdlib import PasswordHash
from datetime import datetime, timedelta, timezone
from typing import Annotated
import jwt
from fastapi.security import OAuth2PasswordRequestForm
from ..database import DBDep
from ..db_models import User
from ..models import UserRegister, UserResponse, Token
from ..config import get_settings
from ..dependencies import CurrentUser

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummypassword")


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(user_data: UserRegister, db: DBDep):
    # FIX: Use .scalars().first() to avoid 500 crashes if multiple rows match
    result = await db.execute(
        select(User).where(
            (User.email == user_data.email) | (User.username == user_data.username)
        )
    )
    existing_user = result.scalars().first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or username already taken"
        )

    new_user = User(
        email=user_data.email,
        username=user_data.username,
        password_hash=password_hash.hash(user_data.password),
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user


# FIX: Changed input model to UserLogin so username isn't forced during login
@router.post("/login", response_model=Token)
async def login(
    db: DBDep,
    # FIX: Use OAuth2 Form data instead of a JSON Pydantic model
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
):
    # Find user by email (OAuth2 form passes the input into form_data.username)
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalars().first()

    # Timing attack prevention — always run verification
    if not user:
        password_hash.verify(form_data.password, DUMMY_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    if not password_hash.verify(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    token = create_access_token(user.id)
    return Token(access_token=token, token_type="bearer")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: CurrentUser):
    return current_user
