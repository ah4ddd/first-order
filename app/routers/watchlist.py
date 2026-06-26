from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..database import DBDep
from ..db_models import WatchlistItem, Stock
from ..models import WatchlistItemResponse
from ..dependencies import CurrentUser

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("/", response_model=list[WatchlistItemResponse])
async def get_watchlist(current_user: CurrentUser, db: DBDep):
    """Get the current user's full watchlist."""
    result = await db.execute(
        select(WatchlistItem)
        .where(WatchlistItem.user_id == current_user.id)
        .options(selectinload(WatchlistItem.stock))  # load stock in same query
        .order_by(WatchlistItem.added_at.desc())
    )
    return result.scalars().all()


@router.post("/{stock_id}", response_model=WatchlistItemResponse, status_code=201)
async def add_to_watchlist(stock_id: int, current_user: CurrentUser, db: DBDep):
    """Add a stock to the user's watchlist."""
    # Check stock exists
    stock = await db.get(Stock, stock_id)
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")

    # Check not already in watchlist
    result = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.user_id == current_user.id,
            WatchlistItem.stock_id == stock_id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Stock already in watchlist")

    item = WatchlistItem(user_id=current_user.id, stock_id=stock_id)
    db.add(item)
    await db.commit()
    await db.refresh(item)

    # Reload with stock relationship
    result = await db.execute(
        select(WatchlistItem)
        .where(WatchlistItem.id == item.id)
        .options(selectinload(WatchlistItem.stock))
    )
    return result.scalar_one()


@router.delete("/{stock_id}", status_code=204)
async def remove_from_watchlist(stock_id: int, current_user: CurrentUser, db: DBDep):
    """Remove a stock from the user's watchlist."""
    result = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.user_id == current_user.id,
            WatchlistItem.stock_id == stock_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Stock not in watchlist")

    await db.delete(item)
    await db.commit()


@router.get("/stocks/search", tags=["stocks"])
async def search_stocks(q: str, db: DBDep):
    """Search stocks by symbol or name. Public endpoint, no auth needed."""
    result = await db.execute(
        select(Stock).where(
            Stock.symbol.ilike(f"%{q}%") | Stock.name.ilike(f"%{q}%")
        ).limit(20)
    )
    return result.scalars().all()
