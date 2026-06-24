from pydantic import BaseModel, EmailStr
from datetime import datetime


# AUTH #
class UserRegister(BaseModel):
    email: EmailStr
    username: str
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    created_at: datetime
    # Allows this Pydantic schema to read data from Python objects
    # (e.g. SQLAlchemy model instances) instead of only dictionaries.
    # Commonly used in response schemas when returning database objects.
    model_config = {"from_attributes": True}

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: int | None = None


# STOCKS #
class StockResponse(BaseModel):
    id: int
    symbol: str
    name: str
    exchange: str
    country: str

    model_config = {"from_attributes": True}


# WATCHLIST #
class WatchlistItemResponse(BaseModel):
    id: int
    stock: StockResponse
    added_at: datetime

    model_config = {"from_attributes": True}


# RESEARCH NOTES #
class NoteCreate(BaseModel):
    title: str | None = None
    content: str

class NoteUpdate(BaseModel):
    title: str | None = None
    content: str | None = None

class NoteResponse(BaseModel):
    id: int
    stock: StockResponse
    title: str | None
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
