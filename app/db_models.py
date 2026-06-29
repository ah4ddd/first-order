from typing import Optional, List
from sqlalchemy import (
    String, Text, ForeignKey, DateTime, UniqueConstraint
)

# Mapped[...] is the Python Type (The Left Side)
# mapped_column() is the SQL Configuration (The Right Side)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from .database import Base


# get current time
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


"""
NOTES:
Mapped[int] is a Python type hint that SQLAlchemy actually reads.
Editor now knows user.id is an int, not Any.
Mapped[str] without Optional automatically means nullable=False.
Mapped[Optional[str]] automatically means nullable=True.
No more manually writing nullable=False everywhere —
the type hint IS the constraint.
This is the modern way. Every new project should use this.
"""


class User(Base):
    __tablename__ = "users"

    # id: int automatically configures Integer and autoincrement=True
    id: Mapped[int] = mapped_column(primary_key=True)

    # Omitting Optional implies nullable=False automatically
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)

    # Pass your callable directly to server_default or default
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Use explicit type hints for relationships (List["Model"])
    watchlist_items: Mapped[List["WatchlistItem"]] = relationship(back_populates="user")
    notes: Mapped[List["ResearchNote"]] = relationship(back_populates="user")


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    exchange: Mapped[str] = mapped_column(String(50))  # NSE, NYSE, XETRA
    country: Mapped[str] = mapped_column(String(10))   # IN, US, DE

    watchlist_items: Mapped[List["WatchlistItem"]] = relationship(back_populates="stock")
    notes: Mapped[List["ResearchNote"]] = relationship(back_populates="stock")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "stock_id"),)

    user: Mapped["User"] = relationship(back_populates="watchlist_items")
    stock: Mapped["Stock"] = relationship(back_populates="watchlist_items")


class ResearchNote(Base):
    __tablename__ = "research_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    title: Mapped[Optional[str]] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)

    # Price snapshot at the moment of note creation
    price_at_creation: Mapped[Optional[float]] = mapped_column(default=None)
    currency: Mapped[Optional[str]] = mapped_column(String(10), default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped["User"] = relationship(back_populates="notes")
    stock: Mapped["Stock"] = relationship(back_populates="notes")
