import yfinance as yf
from curl_cffi import requests
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .db_models import Stock

def _fetch_basic_info(symbol: str) -> dict:
    """Fetch basic stock info through Yahoo's chart endpoint."""
    session = requests.Session(impersonate="chrome")
    try:
        ticker = yf.Ticker(symbol, session=session)
        # Use fast_info to bypass heavy anti-scraping blocks triggered by ticker.info
        fast_info = ticker.fast_info

        # Fallback to basic string manipulation if fast_info fields are missing
        name = symbol
        if hasattr(ticker, 'history_metadata') and ticker.history_metadata:
            name = ticker.history_metadata.get("longName", symbol)

        return {
            "name": name,
            "exchange": fast_info.get("exchange") or "UNKNOWN",
            "currency": fast_info.get("currency") or "UNKNOWN",
            "price": fast_info.get("lastPrice") or fast_info.get("previousClose"),
        }
    except Exception:
        # Fallback strategy if fast_info fails completely due to tighter cloud bans
        return {
            "name": symbol,
            "exchange": "UNKNOWN",
            "currency": "UNKNOWN",
            "price": None
        }
    finally:
        session.close()


async def get_or_create_stock(symbol: str, db: AsyncSession) -> Stock:
    symbol = symbol.upper()

    result = await db.execute(select(Stock).where(Stock.symbol == symbol))
    stock = result.scalar_one_or_none()
    if stock:
        return stock

    # New symbol — validate it actually exists before creating
    try:
        info = await asyncio.to_thread(_fetch_basic_info, symbol)
        if info["name"] == symbol and info["exchange"] == "UNKNOWN":
            raise ValueError(
                f"'{symbol}' not found. Use proper format: "
                f"RELIANCE.NS (India), SAP.DE (Germany), AAPL (US), 7203.T (Japan)"
            )
    except ValueError:
        raise
    except Exception:
        info = {"name": symbol, "exchange": "UNKNOWN", "currency": "UNKNOWN"}

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
