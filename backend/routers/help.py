"""
Help & documentation endpoints.
Static docs are baked into the frontend.
This router handles admin-editable custom notes stored in the settings file.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from ..core.auth import get_current_user, require_super_admin, User
from ..core.access import require_permission
from ..core.settings_store import load_settings, SETTINGS_FILE
import json, os

router = APIRouter(prefix="/api/help", tags=["help"])


class CustomNote(BaseModel):
    id: str           # slug, e.g. "epsilon-guide"
    title: str
    content: str      # markdown
    section: str      # 'resistant' | 'general' | 'setup'
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


class CustomNoteCreate(BaseModel):
    id: Optional[str] = None
    title: str
    content: str
    section: str = "general"


def _load_notes() -> dict:
    s = load_settings()
    return s.get("help_notes", {})


def _save_notes(notes: dict):
    if not os.path.exists(SETTINGS_FILE):
        s = {}
    else:
        with open(SETTINGS_FILE) as f:
            s = json.load(f)
    s["help_notes"] = notes
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=2)


@router.get("/notes", response_model=List[CustomNote])
def list_notes(_: User = Depends(get_current_user)):
    notes = _load_notes()
    return list(notes.values())


@router.post("/notes", response_model=CustomNote, status_code=201)
def create_note(
    data: CustomNoteCreate,
    current_user: User = Depends(require_permission("help.edit")),
):
    notes = _load_notes()
    slug  = data.id or data.title.lower().replace(" ", "-").replace("/","")[:40]
    # ensure unique
    if slug in notes:
        slug = f"{slug}-{len(notes)}"

    note = {
        "id":         slug,
        "title":      data.title,
        "content":    data.content,
        "section":    data.section,
        "updated_at": datetime.utcnow().isoformat(),
        "updated_by": current_user.full_name,
    }
    notes[slug] = note
    _save_notes(notes)
    return note


@router.patch("/notes/{note_id}", response_model=CustomNote)
def update_note(
    note_id: str,
    data: CustomNoteCreate,
    current_user: User = Depends(require_permission("help.edit")),
):
    notes = _load_notes()
    if note_id not in notes:
        from fastapi import HTTPException
        raise HTTPException(404, "Note not found")
    notes[note_id].update({
        "title":      data.title,
        "content":    data.content,
        "section":    data.section,
        "updated_at": datetime.utcnow().isoformat(),
        "updated_by": current_user.full_name,
    })
    _save_notes(notes)
    return notes[note_id]


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(
    note_id: str,
    _: User = Depends(require_permission("help.edit")),
):
    notes = _load_notes()
    notes.pop(note_id, None)
    _save_notes(notes)
