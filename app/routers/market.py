from fastapi import APIRouter, HTTPException
from sqlalchemy import select
import yfinance as yf
from datetime import datetime, timezone
from typing import Any
import asyncio
import logging
import threading
from curl_cffi import requests

from ..database import DBDep
from ..db_models import Stock
from ..services.rss_news import get_symbol_rss_news

router = APIRouter(prefix="/market", tags=["market"])
logger = logging.getLogger(__name__)

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
_yahoo_request_limit = threading.BoundedSemaphore(4)

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


def _fetch_chart_info(symbol: str) -> dict:
    """
    Fetch Yahoo chart metadata, which does not require the crumb-protected
    quote-summary endpoint used by ticker.info.
    """
    history = None
    metadata = {}
    last_error = None

    for attempt in range(3):
        session = requests.Session(impersonate="chrome")
        try:
            with _yahoo_request_limit:
                ticker = yf.Ticker(symbol, session=session)
                history = ticker.history(period="5d", interval="1d", auto_adjust=False)
                metadata = ticker.history_metadata or {}
            if metadata or not history.empty:
                break
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Yahoo chart request failed for %s (attempt %s/3): %s",
                symbol,
                attempt + 1,
                exc,
            )
        finally:
            session.close()
    else:
        if last_error:
            raise last_error
        raise RuntimeError(f"Yahoo returned no chart data for {symbol} after 3 attempts")

    if history is None:
        raise RuntimeError(f"Yahoo returned no chart data for {symbol}")

    price = _safe_get(metadata, "regularMarketPrice")
    previous_close = _safe_get(metadata, "previousClose", "chartPreviousClose")
    latest = history.iloc[-1] if not history.empty else None

    if price is None and latest is not None:
        price = float(latest["Close"])
    if previous_close is None and len(history) > 1:
        previous_close = float(history["Close"].iloc[-2])

    change = (
        price - previous_close
        if price is not None and previous_close is not None
        else None
    )
    change_percent = (
        change / previous_close * 100
        if change is not None and previous_close
        else 0
    )

    return {
        "regularMarketPrice": price,
        "currentPrice": price,
        "previousClose": previous_close,
        "regularMarketChange": change,
        "regularMarketChangePercent": _safe_get(
            metadata, "regularMarketChangePercent", default=change_percent
        ),
        "currency": _safe_get(metadata, "currency", default=""),
        "longName": _safe_get(metadata, "longName", "shortName", default=symbol),
        "shortName": _safe_get(metadata, "shortName", "longName", default=symbol),
        "regularMarketVolume": _safe_get(
            metadata,
            "regularMarketVolume",
            default=float(latest["Volume"]) if latest is not None else None,
        ),
        "marketCap": None,
        "regularMarketDayHigh": _safe_get(
            metadata,
            "regularMarketDayHigh",
            default=float(latest["High"]) if latest is not None else None,
        ),
        "regularMarketDayLow": _safe_get(
            metadata,
            "regularMarketDayLow",
            default=float(latest["Low"]) if latest is not None else None,
        ),
        "fiftyTwoWeekHigh": _safe_get(metadata, "fiftyTwoWeekHigh"),
        "fiftyTwoWeekLow": _safe_get(metadata, "fiftyTwoWeekLow"),
        "exchange": _safe_get(metadata, "exchangeName"),
        "fullExchangeName": _safe_get(metadata, "fullExchangeName", "exchangeName"),
        "marketState": _get_market_state(metadata),
        "sector": None,
        "industry": None,
    }


def _fetch_ticker_info(symbol: str) -> dict:
    """Prefer Yahoo's full quote details, falling back to chart data."""
    session = requests.Session(impersonate="chrome")
    try:
        ticker = yf.Ticker(symbol, session=session)
        info = ticker.info
        if _safe_get(info, "regularMarketPrice", "currentPrice", "previousClose") is not None:
            return info
        logger.warning("Yahoo quote summary had no price for %s; using chart data", symbol)
    except Exception as exc:
        logger.warning("Yahoo quote summary failed for %s; using chart data: %s", symbol, exc)
    finally:
        session.close()

    return _fetch_chart_info(symbol)


def _get_market_state(metadata: dict) -> str:
    current_time = datetime.now(timezone.utc).timestamp()
    trading_periods = metadata.get("currentTradingPeriod") or {}

    for period_name, state in (
        ("pre", "PREPRE"),
        ("regular", "REGULAR"),
        ("post", "POSTPOST"),
    ):
        period = trading_periods.get(period_name) or {}
        start = period.get("start")
        end = period.get("end")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)):
            if start <= current_time < end:
                return state

    return "CLOSED"


def _fetch_ticker_news(symbol: str) -> list:
    """Synchronous yfinance news fetch."""
    session = requests.Session(impersonate="chrome")
    try:
        ticker = yf.Ticker(symbol, session=session)
        return ticker.get_news(count=10, tab="news")
    finally:
        session.close()


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
        info = await asyncio.to_thread(_fetch_chart_info, symbol)

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
    Snapshot of major global indices using Yahoo chart data.
    Fetches at most four indices concurrently.
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
        except Exception as exc:
            logger.warning("Could not fetch market overview data for %s: %s", symbol, exc)
            return market_name, {"symbol": symbol, "error": "unavailable"}

    # Limit concurrent Yahoo requests to avoid bursts from a single overview load.
    semaphore = asyncio.Semaphore(4)

    async def bounded_fetch(market_name: str, symbol: str) -> tuple[str, dict]:
        async with semaphore:
            return await fetch_one(market_name, symbol)

    results_list = await asyncio.gather(
        *[bounded_fetch(name, sym) for name, sym in indices.items()]
    )

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
