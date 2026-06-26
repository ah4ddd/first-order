# seed_stocks.py is a setup script that inserts
# a predefined list of valid stocks into your
# database so users can reference existing stock
# records instead of creating arbitrary ticker symbols themselves.

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from .database import AsyncSessionLocal
from .db_models import Stock
from sqlalchemy import select

# Top stocks across your target markets
STOCKS = [
    # India (NSE)
    {"symbol": "RELIANCE.NS", "name": "Reliance Industries", "exchange": "NSE", "country": "IN"},
    {"symbol": "TCS.NS", "name": "Tata Consultancy Services", "exchange": "NSE", "country": "IN"},
    {"symbol": "HDFCBANK.NS", "name": "HDFC Bank", "exchange": "NSE", "country": "IN"},
    {"symbol": "INFY.NS", "name": "Infosys", "exchange": "NSE", "country": "IN"},
    {"symbol": "HAL.NS", "name": "Hindustan Aeronautics", "exchange": "NSE", "country": "IN"},
    {"symbol": "BEL.NS", "name": "Bharat Electronics", "exchange": "NSE", "country": "IN"},
    {"symbol": "CDSL.NS", "name": "CDSL", "exchange": "NSE", "country": "IN"},
    # USA (NYSE/NASDAQ)
    {"symbol": "AAPL", "name": "Apple Inc", "exchange": "NASDAQ", "country": "US"},
    {"symbol": "MSFT", "name": "Microsoft", "exchange": "NASDAQ", "country": "US"},
    {"symbol": "GOOGL", "name": "Alphabet", "exchange": "NASDAQ", "country": "US"},
    {"symbol": "NVDA", "name": "NVIDIA", "exchange": "NASDAQ", "country": "US"},
    {"symbol": "JPM", "name": "JPMorgan Chase", "exchange": "NYSE", "country": "US"},
    # Germany (XETRA)
    {"symbol": "VOW3.DE", "name": "Volkswagen", "exchange": "XETRA", "country": "DE"},
    {"symbol": "SAP.DE", "name": "SAP SE", "exchange": "XETRA", "country": "DE"},
    # Japan (TSE)
    {"symbol": "7203.T", "name": "Toyota Motor", "exchange": "TSE", "country": "JP"},
    # UK (LSE)
    {"symbol": "SHEL.L", "name": "Shell PLC", "exchange": "LSE", "country": "UK"},
    {"symbol": "HSBA.L", "name": "HSBC Holdings", "exchange": "LSE", "country": "UK"},
    # Hong Kong (HKEX)
    {"symbol": "0700.HK", "name": "Tencent Holdings", "exchange": "HKEX", "country": "HK"},
]


async def seed():
    # Creates a database session
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # Loop through all stocks
            for stock_data in STOCKS:
                # Check if stock already exists
                result = await session.execute(
                    select(Stock).where(Stock.symbol == stock_data["symbol"])
                )
                # if found: skip it
                if result.scalar_one_or_none():
                    print(f"Already exists: {stock_data['symbol']}")
                    continue
                # if not found: add to db
                session.add(Stock(**stock_data))
                print(f"Added: {stock_data['symbol']}")
        # Transaction commits automatically because of:
        #    async with session.begin():
        # which roughly behaves like:
        #    await session.commit()
        # at the end if everything succeeds.
        print("Seeding complete.")


if __name__ == "__main__":
    asyncio.run(seed())
