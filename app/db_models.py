from sqlalchemy import (
    Column, Integer, String, Text,
    ForeignKey, DateTime, UniqueConstraint
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base


# get current time
def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    # Relationships
    # connect to WatchlistItem. On the WatchlistItem side,
    # look for an attribute called: user
    watchlist_items = relationship("WatchlistItem", back_populates="user")
    notes = relationship("ResearchNote", back_populates="user")


class Stock(Base):
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    exchange = Column(String(50), nullable=False)  # NSE, NYSE, XETRA
    country = Column(String(10), nullable=False)   # IN, US, DE

    watchlist_items = relationship("WatchlistItem", back_populates="stock")
    notes = relationship("ResearchNote", back_populates="stock")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Foreign key is link between tables
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=False)
    added_at = Column(DateTime(timezone=True), default=utcnow)

    # One user can't add the same stock twice
    __table_args__ = (UniqueConstraint("user_id", "stock_id"),)

    # connect to User. On the User side,
    # look for an attribute called: watchlist_items
    # user <-> watchlist_items
    # These are opposite ends of the same connection.
    user = relationship("User", back_populates="watchlist_items")
    stock = relationship("Stock", back_populates="watchlist_items")


class ResearchNote(Base):
    __tablename__ = "research_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=False)
    title = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="notes")
    stock = relationship("Stock", back_populates="notes")
