from fastapi import APIRouter, HTTPException
# yfinance works by pretending to be a browser
# This process is called scraping or more accurately: Unofficial API access
import yfinance as yf
from datetime import datetime, timezone
from typing import Any

router = APIRouter(prefix="/market", tags=["market"])

# Simple in-memory cache: {symbol: {"data": {...}, "cached_at": datetime}}
_price_cache: dict[str, dict] = {}
_news_cache: dict[str, dict] = {}

CACHE_TTL_SECONDS = 60  # price cache lives 60 seconds
NEWS_CACHE_TTL_SECONDS = 300  # news cache lives 5 minutes


def _is_cache_valid(cache: dict, symbol: str, ttl: int) -> bool:
    """Check if cached data exists and hasn't expired."""
    if symbol not in cache:
        return False
    age = (datetime.now(timezone.utc) - cache[symbol]["cached_at"]).total_seconds()
    return age < ttl


def _safe_get(data: dict, *keys: str, default: Any = None) -> Any:
    """Safely get a value from a dict, returning default if missing or None."""
    for key in keys:
        val = data.get(key)
        if val is not None:
            return val
    return default


"""
# NOTES: Why some Indian stocks fail?
Because Yahoo uses exchange suffixes.
US:
    AAPL
    META
    NVDA

India NSE:
    RELIANCE.NS
    TCS.NS
    INFY.NS
    HDFCBANK.NS

BSE:
    RELIANCE.BO
    TCS.BO

If you do: RELIANCE
Yahoo searches US exchange first.

Result: not found

Examples:
✅ Works:
    SBIN.NS
    BEL.NS
    HAL.NS
    IRFC.NS
    IREDA.NS

❌ Doesn't:
    SBIN
    BEL
    HAL
    IRFC
    IREDA

There is another issue.
Some Indian stocks:
    have bad Yahoo coverage
    have delayed data
    have no news feed
    have incomplete metadata

Especially:
    SME stocks
    microcaps
    recently listed companies
"""
@router.get("/price/{symbol}")
async def get_stock_price(symbol: str):
    """
    Get live price data for a stock symbol.
    Works for any yfinance-supported symbol:
    Indian: RELIANCE.NS | US: AAPL | German: VOW3.DE | Japanese: 7203.T
    """
    symbol = symbol.upper()

    # Return cached data if still fresh
    if _is_cache_valid(_price_cache, symbol, CACHE_TTL_SECONDS):
        return {**_price_cache[symbol]["data"], "cached": True}

    try:
        ticker = yf.Ticker(symbol) # create an object
        info = ticker.info # where internet request happens

        # yfinance returns {"trailingPegRatio": None} for invalid symbols
        # The clearest signal a symbol is invalid is missing regularMarketPrice
        price = _safe_get(info, "regularMarketPrice", "currentPrice", "previousClose")
        if price is None:
            raise HTTPException(
                status_code=404,
                detail=f"Symbol '{symbol}' not found or market is closed"
            )

        data = {
            "symbol": symbol,
            "name": _safe_get(info, "longName", "shortName", default=symbol),
            "price": price,
            "currency": _safe_get(info, "currency", default="USD"),
            "change": _safe_get(info, "regularMarketChange", default=0),
            "change_percent": _safe_get(info, "regularMarketChangePercent", default=0),
            "volume": _safe_get(info, "regularMarketVolume", default=0),
            "market_cap": _safe_get(info, "marketCap", default=None),
            "day_high": _safe_get(info, "regularMarketDayHigh", default=None),
            "day_low": _safe_get(info, "regularMarketDayLow", default=None),
            "fifty_two_week_high": _safe_get(info, "fiftyTwoWeekHigh", default=None),
            "fifty_two_week_low": _safe_get(info, "fiftyTwoWeekLow", default=None),
            "exchange": _safe_get(info, "exchange", "fullExchangeName", default=None),
            "market_state": _safe_get(info, "marketState", default="UNKNOWN"),
            "cached": False,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        # Store in cache
        _price_cache[symbol] = {
            "data": data,
            "cached_at": datetime.now(timezone.utc)
        }

        return data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to fetch data for {symbol}: {str(e)}"
        )


@router.get("/news/{symbol}")
async def get_stock_news(symbol: str):
    """
    Get recent news for a stock symbol.
    Uses yfinance's built-in news feed — no API key required.
    """
    symbol = symbol.upper()

    if _is_cache_valid(_news_cache, symbol, NEWS_CACHE_TTL_SECONDS):
        return {"symbol": symbol, "news": _news_cache[symbol]["data"], "cached": True}

    try:
        ticker = yf.Ticker(symbol)
        # returns raw ugly Yahoo data
        raw_news = ticker.news  # list of news dicts

        if not raw_news:
            return {"symbol": symbol, "news": [], "cached": False}

        # Clean and normalize the news structure
        # Take inconsistent external data & convert it into predictable structure
        news = []
        for item in raw_news[:10]:  # max 10 headlines
            content = item.get("content", {})
            news.append({
                "title": content.get("title") or item.get("title", "No title"),
                "summary": content.get("summary") or "",
                "url": (
                    content.get("canonicalUrl", {}).get("url")
                    or item.get("link", "")
                ),
                "published_at": content.get("pubDate") or item.get("providerPublishTime", ""),
                "source": (
                    content.get("provider", {}).get("displayName")
                    or item.get("publisher", "Unknown")
                ),
            })

        _news_cache[symbol] = {
            "data": news,
            "cached_at": datetime.now(timezone.utc)
        }

        return {"symbol": symbol, "news": news, "cached": False}

    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to fetch news for {symbol}: {str(e)}"
        )


@router.get("/overview")
async def market_overview():
    """
    Quick snapshot of major market indices.
    Shows the health of each market at a glance.
    """
    indices = {
        "India (NIFTY 50)": "^NSEI",
        "India (SENSEX)": "^BSESN",
        "USA (S&P 500)": "^GSPC",
        "USA (NASDAQ)": "^IXIC",
        "Germany (DAX)": "^GDAXI",
        "Japan (Nikkei)": "^N225",
        "UK (FTSE 100)": "^FTSE",
        "Hong Kong (HSI)": "^HSI",
    }

    results = {}
    for market_name, symbol in indices.items():
        try:
            info = yf.Ticker(symbol).info
            price = _safe_get(info, "regularMarketPrice", "previousClose")
            results[market_name] = {
                "symbol": symbol,
                "price": price,
                "change_percent": _safe_get(
                    info, "regularMarketChangePercent", default=0
                ),
                "currency": _safe_get(info, "currency", default=""),
            }
        except Exception:
            results[market_name] = {"symbol": symbol, "error": "unavailable"}

    return {"overview": results, "fetched_at": datetime.now(timezone.utc).isoformat()}
