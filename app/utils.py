import yfinance as yf
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .db_models import Stock


def _fetch_basic_info(symbol: str) -> dict:
    """Fetch basic stock info with browser-like session to reduce rate limiting."""
    ticker = yf.Ticker(symbol)
    # Access the session yfinance uses and add browser headers
    try:
        session = ticker.session
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })
    except Exception:
        pass

    info = ticker.info
    return {
        "name": info.get("longName") or info.get("shortName") or symbol,
        "exchange": info.get("exchange") or info.get("fullExchangeName") or "UNKNOWN",
        "currency": info.get("currency") or "UNKNOWN",
        "price": (
            info.get("regularMarketPrice")
            or info.get("currentPrice")
            or info.get("previousClose")
        ),
    }


async def get_or_create_stock(symbol: str, db: AsyncSession) -> Stock:
    symbol = symbol.upper()

    result = await db.execute(select(Stock).where(Stock.symbol == symbol))
    stock = result.scalar_one_or_none()

    if stock:
        return stock

    try:
        info = await asyncio.to_thread(_fetch_basic_info, symbol)
    except Exception:
        info = {"name": symbol, "exchange": "UNKNOWN", "currency": "UNKNOWN", "price": None}

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


def _infer_country(symbol: str) -> str:
    suffix_map = {
        ".NS": "IN", ".BO": "IN",
        ".DE": "DE", ".L": "UK",
        ".T": "JP", ".HK": "HK",
        ".SS": "CN", ".SZ": "CN",
        ".TW": "TW", ".KS": "KR",
        ".KQ": "KR", ".PA": "FR",
        ".AS": "NL", ".TO": "CA",
        ".V": "CA", ".AX": "AU",
    }
    for suffix, country in suffix_map.items():
        if symbol.endswith(suffix):
            return country
    return "US"
