from fastapi import APIRouter, HTTPException
import yfinance as yf
from datetime import datetime, timezone
from typing import Any
import asyncio

router = APIRouter(prefix="/market", tags=["market"])

# In-memory cache #
# dict structure: {symbol: {"data": {...}, "cached_at": datetime}}
# Why dict and not Redis? Because Redis requires a running server and costs money.
# For a portfolio project with light traffic, a module-level dict is perfectly fine.
# These dicts live for the entire lifetime of the server process.
_price_cache: dict[str, dict] = {}
_news_cache: dict[str, dict] = {}
_overview_cache: dict[str, Any] = {}  # single cache entry for the overview

PRICE_TTL = 60        # 60 seconds — price changes but not every second
NEWS_TTL = 300        # 5 minutes — news doesn't change that fast
OVERVIEW_TTL = 120    # 2 minutes — indices refresh slightly faster


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
    ticker = yf.Ticker(symbol)
    return ticker.info


def _fetch_ticker_news(symbol: str) -> list:
    """Synchronous news fetch - same reason as above."""
    ticker = yf.Ticker(symbol)
    return ticker.news or []


# Exchange suffix reference
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
    Recent news headlines for a stock symbol.
    Uses yfinance built-in news — no API key required.
    """
    symbol = symbol.upper()

    if _is_cache_valid(_news_cache, symbol, NEWS_TTL):
        return {"symbol": symbol, "news": _news_cache[symbol]["data"], "cached": True}

    try:
        raw_news = await asyncio.to_thread(_fetch_ticker_news, symbol)

        if not raw_news:
            return {"symbol": symbol, "news": [], "cached": False}

        news = []
        for item in raw_news[:10]:
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

        _news_cache[symbol] = {"data": news, "cached_at": datetime.now(timezone.utc)}
        return {"symbol": symbol, "news": news, "cached": False}

    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch news for {symbol}: {str(e)}")


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
