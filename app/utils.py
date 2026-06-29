import yfinance as yf
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .db_models import Stock


def _fetch_basic_info(symbol: str) -> dict:
    """Synchronous yfinance call for basic stock info."""
    ticker = yf.Ticker(symbol)
    info = ticker.info
    return {
        "name": info.get("longName") or info.get("shortName") or symbol,
        "exchange": info.get("exchange") or info.get("fullExchangeName") or "UNKNOWN",
        "currency": info.get("currency") or "UNKNOWN",
    }


def _infer_country(symbol: str) -> str:
    """
    Infer country from Yahoo Finance symbol suffix.
    Not perfect but covers the major markets.
    """
    suffix_map = {
        ".NS": "IN", ".BO": "IN",
        ".DE": "DE",
        ".L":  "UK",
        ".T":  "JP",
        ".HK": "HK",
        ".SS": "CN", ".SZ": "CN",
        ".TW": "TW",
        ".KS": "KR", ".KQ": "KR",
        ".PA": "FR",
        ".AS": "NL",
        ".TO": "CA", ".V": "CA",
        ".AX": "AU",
    }
    for suffix, country in suffix_map.items():
        if symbol.endswith(suffix):
            return country
    return "US"  # no suffix = assume US market


async def get_or_create_stock(symbol: str, db: AsyncSession) -> Stock:
    """
    Try to find stock by symbol in DB.
    If not found, fetch basic info from yfinance and create it.
    Returns the Stock object either way.

    This is the 'get or create' pattern — extremely common in production.
    It means your database self-populates as users reference new stocks,
    instead of requiring manual seeding for every possible ticker.
    """
    symbol = symbol.upper()

    # Try to find existing
    result = await db.execute(select(Stock).where(Stock.symbol == symbol))
    stock = result.scalar_one_or_none()

    if stock:
        return stock

    # Not in DB — fetch from yfinance and create it
    try:
        info = await asyncio.to_thread(_fetch_basic_info, symbol)
    except Exception:
        # yfinance failed — create a minimal record anyway
        # Better to have incomplete data than to block note creation
        info = {"name": symbol, "exchange": "UNKNOWN", "currency": "UNKNOWN"}

    # Infer country from symbol suffix
    country = _infer_country(symbol)

    new_stock = Stock(
        symbol=symbol,
        name=info["name"],
        exchange=info["exchange"],
        country=country,
    )
    db.add(new_stock)
    await db.commit()
    await db.refresh(new_stock)
    return new_stock
