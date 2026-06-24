from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import jwt
from jwt.exceptions import InvalidTokenError

from .database import get_db
from .config import get_settings
from .db_models import User
from .models import TokenData

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm]
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        token_data = TokenData(user_id=int(user_id))
    except (InvalidTokenError, ValueError):
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == token_data.user_id))
    user = result.scalars().first()

    if user is None:
        raise credentials_exception
    return user


# Type alias — use this in every protected route
CurrentUser = Annotated[User, Depends(get_current_user)]
