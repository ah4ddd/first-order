# First-Order 📈

Global stock market research and watchlist platform.

**Live:** https://first-order-a3v1.onrender.com/docs

## What it does
- Track stocks across 14 global markets (US, Germany, Japan, INDIA, UK, HK, China, Taiwan, Korea, France, Netherlands, Canada)
- Personal watchlist — add any Yahoo Finance symbol instantly
- Live price data with sector/industry classification
- Market news per stock
- Global market overview (14 indices in parallel)
- Research notes with price snapshot at creation time

## Tech Stack
FastAPI · PostgreSQL · SQLAlchemy 2.0 (async) · Alembic · JWT · Argon2 · Docker · Render

## Architecture highlights
- Async SQLAlchemy with proper session management via yield dependencies
- In-memory caching with TTL for external API calls
- Parallel index fetching via asyncio.gather
- Auto-creates stock records on first reference (no manual seeding needed)
- Price captured at note creation time for historical context
- RSS fallback for news when primary source rate-limits

## Run locally

```bash
docker compose up --build
docker compose exec api alembic upgrade head
docker compose exec api python -m app.seed_stocks
```

