from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..database import DBDep
from ..db_models import ResearchNote, Stock
from ..models import NoteCreate, NoteUpdate, NoteResponse
from ..dependencies import CurrentUser
from datetime import datetime, timezone

router = APIRouter(prefix="/notes", tags=["notes"])


@router.post("/{stock_id}", response_model=NoteResponse, status_code=201)
async def create_note(stock_id: int, note_data: NoteCreate, current_user: CurrentUser, db: DBDep):
    """
    Create a research note for a specific stock.
    Notes are private — only the author can see them.
    """
    # Verify stock exists
    stock = await db.get(Stock, stock_id)
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")

    note = ResearchNote(
        user_id=current_user.id,
        stock_id=stock_id,
        title=note_data.title,
        content=note_data.content,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)

    # Reload with stock relationship for response
    result = await db.execute(
        select(ResearchNote)
        .where(ResearchNote.id == note.id)
        .options(selectinload(ResearchNote.stock))
    )
    return result.scalar_one()


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


@router.get("/{stock_id}", response_model=list[NoteResponse])
async def get_notes_for_stock(stock_id: int, current_user: CurrentUser, db: DBDep):
    """
    Get all notes the current user has written for a specific stock.
    """
    stock = await db.get(Stock, stock_id)
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not found")

    result = await db.execute(
        select(ResearchNote)
        .where(
            ResearchNote.user_id == current_user.id,
            ResearchNote.stock_id == stock_id,
        )
        .options(selectinload(ResearchNote.stock))
        .order_by(ResearchNote.updated_at.desc())
    )
    return result.scalars().all()


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(note_id: int, note_data: NoteUpdate, current_user: CurrentUser, db: DBDep):
    """
    Update a research note. Only the author can update their own notes.
    Uses PATCH — send only the fields you want to change.
    """
    result = await db.execute(
        select(ResearchNote)
        .where(ResearchNote.id == note_id)
        .options(selectinload(ResearchNote.stock))
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    # Security check — users can only edit their OWN notes
    if note.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your note")

    # Only update fields that were actually sent
    update_data = note_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(note, field, value)

    # Manually update timestamp since onupdate doesn't always fire in async
    note.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(note)

    # Re-fetch with relationship
    result = await db.execute(
        select(ResearchNote)
        .where(ResearchNote.id == note.id)
        .options(selectinload(ResearchNote.stock))
    )
    return result.scalar_one()


@router.delete("/{note_id}", status_code=204)
async def delete_note(note_id: int, current_user: CurrentUser, db: DBDep):
    """
    Delete a research note. Only the author can delete their own notes.
    Returns 204 No Content on success.
    """
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
