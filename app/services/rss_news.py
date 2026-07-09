import feedparser
import asyncio
from datetime import datetime, timezone


# RSS feeds by market/topic — all free, no API key, no rate limits
RSS_FEEDS = {
    "global": [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069",
    ],
    "india": [
        "https://economictimes.indiatimes.com/markets/rss.cms",
        "https://www.moneycontrol.com/rss/latestnews.xml",
    ],
    "us": [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069",
    ],
}


def _parse_feed(url: str) -> list[dict]:
    """Synchronous RSS fetch and parse."""
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:5]:  # max 5 per feed
            items.append({
                "title": entry.get("title", ""),
                "summary": entry.get("summary", "")[:300],  # truncate long summaries # type: ignore
                "url": entry.get("link", ""),
                "published_at": entry.get("published", ""),
                "source": feed.feed.get("title", url), # type: ignore
            })
        return items
    except Exception:
        return []


async def get_rss_news(market: str = "global") -> list[dict]:
    """
    Fetch news from RSS feeds for a given market.
    Runs multiple feeds in parallel, deduplicates by title.
    """
    feeds = RSS_FEEDS.get(market, RSS_FEEDS["global"])

    # Fetch all feeds simultaneously
    results = await asyncio.gather(
        *[asyncio.to_thread(_parse_feed, url) for url in feeds]
    )

    # Flatten and deduplicate by title
    seen_titles = set()
    news = []
    for feed_items in results:
        for item in feed_items:
            title_key = item["title"].lower()[:50]
            if title_key not in seen_titles and item["title"]:
                seen_titles.add(title_key)
                news.append(item)

    return news[:10]  # max 10 total


async def search_rss_news(query: str) -> list[dict]:
    """
    Search RSS news by keyword across all feeds.
    Simple title/summary matching — no API needed.
    """
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
