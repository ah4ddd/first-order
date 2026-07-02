from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone
import asyncio
from ..database import DBDep
from ..db_models import ResearchNote
from ..models import NoteCreate, NoteUpdate, NoteResponse
from ..dependencies import CurrentUser
from ..utils import get_or_create_stock
from .market import _fetch_ticker_info

router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("/", response_model=list[NoteResponse])
async def get_all_my_notes(current_user: CurrentUser, db: DBDep):
    """
    Get ALL research notes for the current user across all stocks.
    Useful for a "my research" dashboard view.
    """
    result = await db.execute(
        select(ResearchNote)
        .where(ResearchNote.user_id == current_user.id)
        .options(selectinload(ResearchNote.stock))
        .order_by(ResearchNote.updated_at.desc())
    )
    return result.scalars().all()


@router.get("/stock/{symbol}", response_model=list[NoteResponse])
async def get_notes_for_stock(symbol: str, current_user: CurrentUser, db: DBDep):
    """
    All notes the current user wrote about a specific stock.
    Uses symbol instead of integer ID — no need to remember numbers.
    """
    symbol = symbol.upper()
    result = await db.execute(
        select(ResearchNote)
        .join(ResearchNote.stock)
        .where(
            ResearchNote.user_id == current_user.id,
        )
        .where(ResearchNote.stock.has(symbol=symbol))
        .options(selectinload(ResearchNote.stock))
        .order_by(ResearchNote.updated_at.desc())
    )
    notes = result.scalars().all()

    if not notes:
        return []  # empty list is fine, not a 404
    return notes


@router.post("/{symbol}", response_model=NoteResponse, status_code=201)
async def create_note(symbol: str, note_data: NoteCreate, current_user: CurrentUser, db: DBDep):
    """
    Create a research note for any stock symbol.

    If the stock isn't in our database yet, we fetch its info
    from yfinance and create it automatically. This means you can
    write notes about ANY Yahoo Finance symbol, not just pre-seeded ones.

    Examples:
        POST /notes/HDFCBANK.NS
        POST /notes/AAPL
        POST /notes/2330.TW
        POST /notes/005930.KS
        POST /notes/ASML.AS
    """
    stock = await get_or_create_stock(symbol, db)

    # Attempt to capture current price — non-blocking, fails silently
    price_at_creation = None
    currency = None
    try:
        info = await asyncio.to_thread(_fetch_ticker_info, symbol.upper())
        price_at_creation = (
            info.get("regularMarketPrice")
            or info.get("currentPrice")
            or info.get("previousClose")
        )
        currency = info.get("currency")
    except Exception:
        pass  # price capture failing should never block note creation

    note = ResearchNote(
        user_id=current_user.id,
        stock_id=stock.id,
        title=note_data.title,
        content=note_data.content,
        price_at_creation=price_at_creation,
        currency=currency,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)

    result = await db.execute(
        select(ResearchNote)
        .where(ResearchNote.id == note.id)
        .options(selectinload(ResearchNote.stock))
    )
    return result.scalar_one()


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(note_id: int, note_data: NoteUpdate, current_user: CurrentUser, db: DBDep):
    """
    Update a note by its ID.
    Note IDs are returned in every note response — no need to memorize them.
    Only the author can update their notes.
    """
    result = await db.execute(
        select(ResearchNote)
        .where(ResearchNote.id == note_id)
        .options(selectinload(ResearchNote.stock))
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    if note.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your note")

    update_data = note_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(note, field, value)

    note.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(note)

    result = await db.execute(
        select(ResearchNote)
        .where(ResearchNote.id == note.id)
        .options(selectinload(ResearchNote.stock))
    )
    return result.scalar_one()


@router.delete("/{note_id}", status_code=204)
async def delete_note(note_id: int, current_user: CurrentUser, db: DBDep):
    """Delete a note. Only the author can delete their own notes."""
    result = await db.execute(
        select(ResearchNote).where(ResearchNote.id == note_id)
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    if note.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your note")

    await db.delete(note)
    await db.commit()
