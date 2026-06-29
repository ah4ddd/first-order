from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..database import DBDep
from ..db_models import WatchlistItem, Stock
from ..models import WatchlistItemResponse
from ..dependencies import CurrentUser

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

"""
# NOTES:
The one concept to explain — selectinload:
When you fetch a WatchlistItem, SQLAlchemy by default does NOT automatically load the related Stock object.
If you try to access item.stock without loading it first, you get a lazy loading error in async mode.
selectinload(WatchlistItem.stock) tells SQLAlchemy: "when you fetch WatchlistItems,
also fetch their related Stock objects in a second efficient query."
Two queries total, but your response has full stock data.
This is how you handle relationships in async SQLAlchemy — always explicit, never lazy.
"""


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



