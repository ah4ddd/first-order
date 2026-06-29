from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..database import DBDep
from ..db_models import WatchlistItem, Stock
from ..models import WatchlistItemResponse
from ..dependencies import CurrentUser
from ..utils import get_or_create_stock

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("/", response_model=list[WatchlistItemResponse])
async def get_watchlist(current_user: CurrentUser, db: DBDep):
    """Get the current user's full watchlist with stock details."""
    result = await db.execute(
        select(WatchlistItem)
        .where(WatchlistItem.user_id == current_user.id)
        .options(selectinload(WatchlistItem.stock))
        .order_by(WatchlistItem.added_at.desc())
    )
    return result.scalars().all()


@router.post("/{symbol}", response_model=WatchlistItemResponse, status_code=201)
async def add_to_watchlist(symbol: str, current_user: CurrentUser, db: DBDep):
    """
    Add any stock to watchlist by symbol.
    If stock isn't in our database yet, it gets created automatically.

    Examples:
        POST /watchlist/AAPL
        POST /watchlist/RELIANCE.NS
        POST /watchlist/2330.TW
        POST /watchlist/005930.KS
    """
    stock = await get_or_create_stock(symbol, db)

    # Check not already in watchlist
    result = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.user_id == current_user.id,
            WatchlistItem.stock_id == stock.id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"{symbol} is already in your watchlist")

    item = WatchlistItem(user_id=current_user.id, stock_id=stock.id)
    db.add(item)
    await db.commit()
    await db.refresh(item)

    result = await db.execute(
        select(WatchlistItem)
        .where(WatchlistItem.id == item.id)
        .options(selectinload(WatchlistItem.stock))
    )
    return result.scalar_one()


@router.delete("/{symbol}", status_code=204)
async def remove_from_watchlist(symbol: str, current_user: CurrentUser, db: DBDep):
    """
    Remove a stock from watchlist by symbol.
    """
    symbol = symbol.upper()

    # Find the stock first
    result = await db.execute(select(Stock).where(Stock.symbol == symbol))
    stock = result.scalar_one_or_none()

    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {symbol} not found")

    # Find the watchlist item
    result = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.user_id == current_user.id,
            WatchlistItem.stock_id == stock.id,
        )
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail=f"{symbol} is not in your watchlist")

    await db.delete(item)
    await db.commit()
