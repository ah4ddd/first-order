import asyncio
import logging
from urllib.parse import quote_plus

import feedparser
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# RSS feeds by market/topic - all free, no API key.
RSS_FEEDS = {
    "global": [
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069",
    ],
    "india": [
        "https://www.moneycontrol.com/rss/latestnews.xml",
    ],
    "us": [
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069",
    ],
}

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}

QUOTE_PAGE_PATTERNS = (
    "stock price, news, quote",
    "stock price, quote",
    "stock price -",
    "stock price |",
    "stock quote, history",
    "share price, news",
    "share price -",
    "share price |",
    "forecast - price target",
    "forecast \u2014 price target",
    "price target - prediction",
    "price target \u2014 prediction",
)


def _clean_text(value: str | None, max_length: int | None = None) -> str:
    if not value:
        return ""

    text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    text = " ".join(text.split())
    if max_length and len(text) > max_length:
        return text[:max_length].rstrip()
    return text


def _entry_source(entry: dict, feed: feedparser.FeedParserDict, fallback_url: str) -> str:
    source = entry.get("source")
    if isinstance(source, dict) and source.get("title"):
        return source["title"]

    feed_metadata = feed.get("feed")
    if isinstance(feed_metadata, dict) and feed_metadata.get("title"):
        return feed_metadata["title"]
    return fallback_url


def _parse_feed(url: str, limit: int = 10) -> list[dict]:
    """Synchronous RSS fetch and parse with timeout."""
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=8)
        response.raise_for_status()
        feed = feedparser.parse(response.content)

        items = []
        for entry in feed.entries[:limit]:
            title = _clean_text(entry.get("title", ""))
            link = entry.get("link", "")
            if not title or not link:
                continue
            if any(pattern in title.lower() for pattern in QUOTE_PAGE_PATTERNS):
                continue

            items.append({
                "title": title,
                "summary": _clean_text(entry.get("summary"), max_length=300),
                "url": link,
                "published_at": entry.get("published", ""),
                "source": _entry_source(entry, feed, url),
            })
        return items
    except requests.RequestException as exc:
        logger.warning("Could not fetch RSS news feed %s: %s", url, exc)
        return []


def _dedupe(items: list[dict], limit: int = 10) -> list[dict]:
    seen = set()
    news = []

    for item in items:
        key = (item.get("url") or item.get("title", "")).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        news.append(item)
        if len(news) >= limit:
            break

    return news


def _google_news_url(query: str) -> str:
    return (
        "https://news.google.com/rss/search?q="
        f"{quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    )


def _yahoo_symbol_news_url(symbol: str) -> str:
    return (
        "https://feeds.finance.yahoo.com/rss/2.0/headline?"
        f"s={quote_plus(symbol)}&region=US&lang=en-US"
    )


async def get_rss_news(market: str = "global") -> list[dict]:
    """
    Fetch news from RSS feeds for a given market.
    Runs multiple feeds in parallel, deduplicates by title.
    """
    feeds = RSS_FEEDS.get(market, RSS_FEEDS["global"])

    results = await asyncio.gather(
        *[asyncio.to_thread(_parse_feed, url, 5) for url in feeds]
    )

    return _dedupe([item for feed_items in results for item in feed_items])


async def get_symbol_rss_news(symbol: str, company_name: str | None = None) -> list[dict]:
    """
    Fetch stock-specific news without relying on yfinance's broken JSON news endpoint.

    Provider order:
    1. Yahoo Finance ticker RSS, which still works for many symbols.
    2. Google News RSS search for ticker/company terms.
    3. Broad business RSS keyword search.
    """
    symbol = symbol.upper()
    base_symbol = symbol.split(".")[0]
    search_terms = []

    if company_name and company_name.upper() != symbol:
        search_terms.append(f"{company_name} news")
        search_terms.append(f"{company_name} stock")
    search_terms.append(f"{symbol} stock")
    if base_symbol != symbol:
        search_terms.append(f"{base_symbol} stock")

    urls = [_yahoo_symbol_news_url(symbol)]
    urls.extend(_google_news_url(term) for term in search_terms)

    results = await asyncio.gather(
        *[asyncio.to_thread(_parse_feed, url, 10) for url in urls]
    )

    news = _dedupe([item for feed_items in results for item in feed_items])
    if news:
        return news

    # Last resort: search the broad curated feeds.
    return await search_rss_news(company_name or base_symbol)


async def search_rss_news(query: str) -> list[dict]:
    """
    Search RSS news by keyword across all feeds.
    Uses Google News RSS first, then broad feed title/summary matching.
    """
    query = query.strip()
    if not query:
        return []

    google_items = await asyncio.to_thread(_parse_feed, _google_news_url(query), 10)
    if google_items:
        return _dedupe(google_items)

    all_news = await get_rss_news("global")
    india_news = await get_rss_news("india")
    all_items = all_news + india_news

    query_lower = query.lower()
    matches = [
        item for item in all_items
        if query_lower in item["title"].lower()
        or query_lower in item["summary"].lower()
    ]

    return matches[:10]
