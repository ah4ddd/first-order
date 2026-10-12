from fastapi import APIRouter, HTTPException
from sqlalchemy import select
import yfinance as yf
from datetime import datetime, timezone
from typing import Any
import asyncio
import logging
from curl_cffi import requests

from ..database import DBDep
from ..db_models import Stock
from ..services.rss_news import get_symbol_rss_news

router = APIRouter(prefix="/market", tags=["market"])
logger = logging.getLogger(__name__)

# Initialize the real browser-impersonating proxy engine
stealth_session = requests.Session(impersonate="chrome")

# Create a shared session with cookie persistence across all yfinance calls
# This means the crumb gets fetched ONCE and reused,
# reducing the chance of being blockedw


## In-memory cache ##
# dict structure: {symbol: {"data": {...}, "cached_at": datetime}}
# Why dict and not Redis? Because Redis requires a running server and costs money.
# For a portfolio project with light traffic, a module-level dict is perfectly fine.
# These dicts live for the entire lifetime of the server process.
_price_cache: dict[str, dict] = {}
_news_cache: dict[str, dict] = {}
_overview_cache: dict[str, Any] = {}  # single cache entry for the overview

PRICE_TTL = 60        # 60 seconds — price changes but not every second
NEWS_TTL = 300        # 5 minutes — news doesn't change that fast
OVERVIEW_TTL = 120    # 2 minutes — indices don't need ultra-fresh updates

# Why the _ underscore?
# This is one of Python's biggest conventions.
# Single underscore means:
# Internal use only or Private-ish.

# Helpers #
def _is_cache_valid(cache: dict, key: str, ttl: int) -> bool:
    """True if cache[key] exists and was set less than ttl seconds ago."""
    if key not in cache:
        return False
    age = (datetime.now(timezone.utc) - cache[key]["cached_at"]).total_seconds()
    return age < ttl


def _safe_get(data: dict, *keys: str, default: Any = None) -> Any:
    """
    Try each key in order, return first non-None value found.
    Why: yfinance returns different keys for different exchanges.
    US stocks have 'regularMarketPrice'. Some others only have 'currentPrice'.
    This handles all variations without crashing.
    """
    for key in keys:
        val = data.get(key)
        if val is not None:
            return val
    return default


def _fetch_ticker_info(symbol: str) -> dict:
    """
    Synchronous yfinance call — must be wrapped with asyncio.to_thread.

    Why separate function?
    asyncio.to_thread needs a plain callable with no async.
    yfinance is synchronous (blocking) — it opens an HTTP connection,
    waits for Yahoo's response, parses HTML. Doing this directly inside
    an async def blocks the entire event loop. to_thread pushes it to
    a threadpool so the event loop stays free to handle other requests.
    """
    # Inject the browser session to keep Render from getting immediate 401 blocks
    ticker = yf.Ticker(symbol, session=stealth_session)
    return ticker.info


def _fetch_ticker_news(symbol: str) -> list:
    """Synchronous yfinance news fetch."""
    ticker = yf.Ticker(symbol, session=stealth_session)
    return ticker.get_news(count=10, tab="news")


def _normalize_published_at(value: Any) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    return str(value or "")


def _normalize_yfinance_news_item(item: dict) -> dict | None:
    content = item.get("content") or {}
    canonical_url = content.get("canonicalUrl") or {}
    provider = content.get("provider") or {}

    title = content.get("title") or item.get("title")
    url = canonical_url.get("url") or item.get("link") or item.get("url")

    if not title or not url:
        return None

    return {
        "title": title,
        "summary": content.get("summary") or item.get("summary") or "",
        "url": url,
        "published_at": _normalize_published_at(
            content.get("pubDate") or item.get("providerPublishTime")
        ),
        "source": provider.get("displayName") or item.get("publisher", "Yahoo Finance"),
        "via": "yfinance",
    }


async def _get_company_name_for_news(symbol: str) -> str | None:
    cached_price = _price_cache.get(symbol, {}).get("data", {})
    cached_name = cached_price.get("name")
    if cached_name and cached_name != symbol:
        return cached_name

    try:
        info = await asyncio.to_thread(_fetch_ticker_info, symbol)
    except Exception as exc:
        logger.warning("Could not look up company name for %s: %s", symbol, exc)
        return None

    name = _safe_get(info, "longName", "shortName")
    return name if name and name != symbol else None


# Exchange suffix reference #
"""
Yahoo Finance symbol suffixes by market:

INDIA
    NSE:    .NS   (RELIANCE.NS, TCS.NS, INFY.NS)
    BSE:    .BO   (RELIANCE.BO) — usually same price, NSE preferred

USA
    No suffix needed (AAPL, MSFT, NVDA, META)

GERMANY
    XETRA:  .DE   (VOW3.DE, SAP.DE, BMW.DE)

JAPAN
    TSE:    .T    (7203.T = Toyota, 6758.T = Sony)

UK
    LSE:    .L    (SHEL.L, HSBA.L, BP.L)

HONG KONG
    HKEX:   .HK   (0700.HK = Tencent, 9988.HK = Alibaba)

CHINA (mainland)
    Shanghai: .SS (600519.SS = Kweichow Moutai, 601398.SS = ICBC)
    Shenzhen: .SZ (000001.SZ = Ping An Bank)

TAIWAN
    TWSE:   .TW   (2330.TW = TSMC, 2317.TW = Foxconn)

SOUTH KOREA
    KRX:    .KS   (005930.KS = Samsung, 000660.KS = SK Hynix)

FRANCE / EURONEXT
    Euronext Paris: .PA  (MC.PA = LVMH, AI.PA = Air Liquide, OR.PA = L'Oreal)
    Euronext Amsterdam: .AS (ASML.AS = ASML, HEIA.AS = Heineken)

CANADA
    TSX:    .TO   (RY.TO = Royal Bank, SU.TO = Suncor)
    TSXV:   .V    (venture exchange, small caps)

KNOWN LIMITATIONS
    SME stocks on NSE/BSE: incomplete or missing data
    Recently listed companies: no historical data yet
    Microcaps across all markets: sparse coverage
    Chinese ADRs traded in US have no suffix (BABA, JD, PDD)
"""


@router.get("/stocks/search")
async def search_stocks(q: str, db: DBDep):
    """Search stocks by symbol or name. Public endpoint, no auth needed."""
    result = await db.execute(
        select(Stock).where(
            Stock.symbol.ilike(f"%{q}%") | Stock.name.ilike(f"%{q}%")
        ).limit(20)
    )
    return result.scalars().all()


@router.get("/price/{symbol}")
async def get_stock_price(symbol: str):
    """
    Live price data for any yfinance-supported symbol.

    Examples:
        /market/price/AAPL          US — Apple
        /market/price/RELIANCE.NS   India NSE — Reliance
        /market/price/2330.TW       Taiwan — TSMC
        /market/price/005930.KS     Korea — Samsung
        /market/price/600519.SS     China Shanghai — Moutai
        /market/price/ASML.AS       Euronext — ASML
        /market/price/RY.TO         Canada — Royal Bank
        /market/price/MC.PA         France — LVMH
    """
    symbol = symbol.upper()

    if _is_cache_valid(_price_cache, symbol, PRICE_TTL):
        return {**_price_cache[symbol]["data"], "cached": True}

    try:
        # Run blocking yfinance call in threadpool — keeps event loop free
        info = await asyncio.to_thread(_fetch_ticker_info, symbol)

        price = _safe_get(info, "regularMarketPrice", "currentPrice", "previousClose")
        if price is None:
            raise HTTPException(
                status_code=404,
                detail=f"Symbol '{symbol}' not found or no price data available. "
                       f"Tip: Indian stocks need .NS suffix (e.g. RELIANCE.NS)"
            )

        data = {
            "symbol": symbol,
            "name": _safe_get(info, "longName", "shortName", default=symbol),
            "price": price,
            "currency": _safe_get(info, "currency", default="USD"),
            "change": _safe_get(info, "regularMarketChange", default=0),
            "change_percent": _safe_get(info, "regularMarketChangePercent", default=0),
            "volume": _safe_get(info, "regularMarketVolume", default=0),
            "market_cap": _safe_get(info, "marketCap"),
            "day_high": _safe_get(info, "regularMarketDayHigh"),
            "day_low": _safe_get(info, "regularMarketDayLow"),
            "fifty_two_week_high": _safe_get(info, "fiftyTwoWeekHigh"),
            "fifty_two_week_low": _safe_get(info, "fiftyTwoWeekLow"),
            "exchange": _safe_get(info, "exchange", "fullExchangeName"),
            "market_state": _safe_get(info, "marketState", default="UNKNOWN"),
            "sector": _safe_get(info, "sector"),
            "industry": _safe_get(info, "industry"),
            "cached": False,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        _price_cache[symbol] = {"data": data, "cached_at": datetime.now(timezone.utc)}
        return data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch {symbol}: {str(e)}")


@router.get("/news/{symbol}")
async def get_stock_news(symbol: str):
    """
    Get recent news for a stock symbol.
    Primary: yfinance news feed.
    Fallback: RSS feeds searched by company name.
    """
    symbol = symbol.upper()

    if _is_cache_valid(_news_cache, symbol, NEWS_TTL):
        cached = _news_cache[symbol]
        return {
            "symbol": symbol,
            "news": cached["data"],
            "cached": True,
            "source": cached["source"],
        }

    # Try yfinance first
    try:
        raw_news = await asyncio.to_thread(_fetch_ticker_news, symbol)
        if raw_news:
            news = [
                normalized
                for item in raw_news[:10]
                if (normalized := _normalize_yfinance_news_item(item))
            ]

            if news:
                _news_cache[symbol] = {
                    "data": news,
                    "source": "yfinance",
                    "cached_at": datetime.now(timezone.utc),
                }
                return {
                    "symbol": symbol,
                    "news": news,
                    "cached": False,
                    "source": "yfinance",
                }
    except Exception as exc:
        logger.warning("YFinance news fetch failed for %s: %s", symbol, exc)

    company_name = await _get_company_name_for_news(symbol)
    rss_news = await get_symbol_rss_news(symbol, company_name=company_name)

    if rss_news:
        for item in rss_news:
            item["via"] = "rss"
        _news_cache[symbol] = {
            "data": rss_news,
            "source": "rss_fallback",
            "cached_at": datetime.now(timezone.utc),
        }
        return {"symbol": symbol, "news": rss_news, "cached": False, "source": "rss_fallback"}

    return {"symbol": symbol, "news": [], "cached": False}


@router.get("/overview")
async def market_overview():
    """
    Live snapshot of major global indices.
    All indices fetched in parallel — total time ~500ms regardless of count.
    """
    # Single cache entry for the whole overview response
    if _is_cache_valid(_overview_cache, "overview", OVERVIEW_TTL):
        return {**_overview_cache["overview"]["data"], "cached": True}

    indices = {
        # South Asia
        "India (NIFTY 50)":     "^NSEI",
        "India (SENSEX)":       "^BSESN",
        # North America
        "USA (S&P 500)":        "^GSPC",
        "USA (NASDAQ)":         "^IXIC",
        "Canada (TSX)":         "^GSPTSE",
        # Europe
        "Germany (DAX)":        "^GDAXI",
        "UK (FTSE 100)":        "^FTSE",
        "France (CAC 40)":      "^FCHI",
        "Euronext (AEX)":       "^AEX",
        # Asia Pacific
        "Japan (Nikkei 225)":   "^N225",
        "Hong Kong (HSI)":      "^HSI",
        "China (Shanghai)":     "000001.SS",
        "Taiwan (TWII)":        "^TWII",
        "South Korea (KOSPI)":  "^KS11",
    }

    async def fetch_one(market_name: str, symbol: str) -> tuple[str, dict]:
        """
        Fetch a single index inside a coroutine.
        Returns (market_name, result_dict) tuple so we can rebuild the dict after gather.

        Why tuple return?
        asyncio.gather runs all coroutines simultaneously and returns a list
        of results in the same order. We need to know WHICH result belongs
        to WHICH market name, so we return both together.
        """
        try:
            info = await asyncio.to_thread(_fetch_ticker_info, symbol)
            price = _safe_get(info, "regularMarketPrice", "previousClose")
            return market_name, {
                "symbol": symbol,
                "price": price,
                "change_percent": round(
                    _safe_get(info, "regularMarketChangePercent", default=0), 4
                ),
                "currency": _safe_get(info, "currency", default=""),
                "market_state": _safe_get(info, "marketState", default="UNKNOWN"),
            }
        except Exception:
            return market_name, {"symbol": symbol, "error": "unavailable"}

    # asyncio.gather fires ALL fetch_one coroutines at the same time.
    # Instead of: fetch India (500ms) → fetch USA (500ms) → ... = 7000ms total
    # You get:    fetch all simultaneously = ~500ms total (slowest single call)
    results_list = await asyncio.gather(
        *[fetch_one(name, sym) for name, sym in indices.items()]
    ) # complexity: O(1)

    # Rebuild into dict from list of (name, data) tuples
    overview_data = {name: data for name, data in results_list}

    response = {
        "overview": overview_data,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "cached": False,
    }

    _overview_cache["overview"] = {
        "data": response,
        "cached_at": datetime.now(timezone.utc)
    }

    return response
