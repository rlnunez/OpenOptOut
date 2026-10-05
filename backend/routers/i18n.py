"""
Internationalization (i18n) API Router (Roadmap Item 17).

Endpoints:
  GET  /api/i18n/languages             — list available & enabled languages
  GET  /api/i18n/translations/{locale} — get translated dictionary for a locale
  GET  /api/i18n/dictionary            — get master schema with locations & descriptions
  POST /api/i18n/languages             — admin: register a new language
  PUT  /api/i18n/languages/{code}/toggle — admin: enable/disable a language
  PUT  /api/i18n/translations/{locale} — admin: replace/update custom translations
  GET  /api/i18n/user/preference       — get current user's language & tutorial status
  POST /api/i18n/user/preference       — update current user's preferred language
  POST /api/i18n/user/tutorial-complete — mark guided tutorial complete
"""

import logging
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import get_db, User
from ..core.auth import get_current_user, require_super_admin
from ..core.access import require_permission
from ..core import i18n

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/i18n", tags=["i18n"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class LanguageOut(BaseModel):
    code: str
    name: str
    native_name: str
    is_rtl: bool
    source: str
    enabled: bool


class CreateLanguageRequest(BaseModel):
    code: str
    name: str
    native_name: Optional[str] = None
    is_rtl: bool = False


class ToggleLanguageRequest(BaseModel):
    enabled: bool


class TranslationsUpdateRequest(BaseModel):
    translations: Dict[str, str]


class UserPreferenceRequest(BaseModel):
    language: str


class UserPreferenceOut(BaseModel):
    preferred_language: str
    tutorial_completed: bool


# ── Public / All-User Endpoints ───────────────────────────────────────────────

@router.get("/languages", response_model=List[LanguageOut])
def list_languages():
    """Returns all configured languages and their enabled status."""
    return i18n.get_available_languages()


@router.get("/translations/{locale}")
def get_translations(locale: str):
    """
    Returns resolved translation key-value mapping for the requested locale.
    Falls back to English defaults for untranslated keys.
    """
    resolved = i18n.get_translations_for_locale(locale)
    return {
        "locale": locale.lower(),
        "is_rtl": i18n.is_rtl_language(locale),
        "translations": resolved,
    }


# ── Authenticated User Preferences ────────────────────────────────────────────

@router.get("/user/preference", response_model=UserPreferenceOut)
def get_user_preference(current_user: User = Depends(get_current_user)):
    """Fetch current user's saved language preference and tutorial state."""
    return UserPreferenceOut(
        preferred_language=getattr(current_user, "preferred_language", "en") or "en",
        tutorial_completed=bool(getattr(current_user, "tutorial_completed", False)),
    )


@router.post("/user/preference", response_model=UserPreferenceOut)
def set_user_preference(
    req: UserPreferenceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Persist current user's preferred language."""
    code = req.language.lower().strip()
    available = {l["code"]: l for l in i18n.get_available_languages()}

    if code not in available or not available[code]["enabled"]:
        raise HTTPException(400, f"Language '{code}' is not currently available or enabled.")

    current_user.preferred_language = code
    db.commit()
    return UserPreferenceOut(
        preferred_language=current_user.preferred_language,
        tutorial_completed=bool(getattr(current_user, "tutorial_completed", False)),
    )


@router.post("/user/tutorial-complete")
def complete_tutorial(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark the user's welcome tour as completed."""
    current_user.tutorial_completed = True
    db.commit()
    return {"ok": True, "tutorial_completed": True}


# ── Administrative Translation & Language Management ─────────────────────────

@router.get("/dictionary")
def get_dictionary(
    current_user: User = Depends(require_permission("settings.system")),
):
    """Returns the master schema of all translatable keys with screen locations."""
    return i18n.get_dictionary()


@router.post("/languages", response_model=LanguageOut)
def create_language(
    req: CreateLanguageRequest,
    current_user: User = Depends(require_permission("settings.system")),
):
    """Register a new language code in the system."""
    try:
        lang = i18n.register_custom_language(
            code=req.code,
            name=req.name,
            native_name=req.native_name or req.name,
            is_rtl=req.is_rtl,
        )
        return lang
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Failed to add language. Please check that language code and name are valid.",
        )


@router.put("/languages/{code}/toggle")
def toggle_language(
    code: str,
    req: ToggleLanguageRequest,
    current_user: User = Depends(require_permission("settings.system")),
):
    """Enable or disable a language for the platform."""
    try:
        updated = i18n.toggle_language_enabled(code, req.enabled)
        return {"ok": True, "languages": updated}
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Language not found or could not be toggled.",
        )


@router.put("/translations/{locale}")
def update_translations(
    locale: str,
    req: TranslationsUpdateRequest,
    current_user: User = Depends(require_permission("settings.system")),
):
    """
    Save custom translation string replacements for a language.
    Super admins and managers use this in the in-system translation editor.
    """
    updated_dict = i18n.set_custom_translation_strings(locale, req.translations)
    return {
        "ok": True,
        "locale": locale.lower(),
        "is_rtl": i18n.is_rtl_language(locale),
        "translations": updated_dict,
    }
