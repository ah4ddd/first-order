from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from typing import Annotated, AsyncGenerator
from fastapi import Depends
from .config import get_settings

settings = get_settings()

# Async engine (talks to PostgreSQL without blocking)
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

# Base Class all models inherit from
class Base(DeclarativeBase):
    pass


# Yield dependency - opens session, gives it to endpoint, closes after
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    print("Creating database session...")
    async with AsyncSessionLocal() as session:
        yield session
    print("Closing database session...")


# Alias
DBDep = Annotated[AsyncSession, Depends(get_db)]
