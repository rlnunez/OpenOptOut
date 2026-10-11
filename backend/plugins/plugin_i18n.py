"""
Translations for the text plugins show people: a plugin's description on the
Plugins page, a broker's "what to do" instructions, and the instruction a form
flow shows when it stops for a person (`pause_for_human`).

Text is looked up by plugin id and key. Conventional keys:

    description          manifest.json "description"
    instructions         spec.json "instructions"
    steps.<i>.text       the text of pause_for_human step number <i> (from 0)

A spec may also name its own key, so translations survive steps being added
or reordered:  "instructions": {"$t": "how_to", "default": "Open the page..."}.

Lookup order for language L (first hit wins), per
docs/CATALOG_AND_LOCALIZATION_DESIGN.md §3.3:

  1. An admin's override: settings i18n.custom_translations[L]["plugin:<id>:<key>"]
  2. Language packs: <pack>/plugins/<plugin_id>.json for L — an installed pack
     first, then the built-in pack (unless an admin turned it off)
  3. The plugin's own locales/<L>.json
  4. The plugin's locales/<default_locale>.json
  5. The text written in the manifest or spec

L is tried as written and then by its base language ("pt-BR", then "pt").

Text sent to a broker is never looked up here: the language of an opt-out
letter is the broker's legal language (core/legal_letters.py), not the
language a person reads the app in. Text a form step matches on the broker's
page (click_matching, expect_success) is not translated either.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

LOCALE_CODE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
OVERRIDE_PREFIX = "plugin:"
MAX_LOCALE_FILE_BYTES = 512 * 1024

_cache: Dict[str, tuple] = {}


def normalize(lang: str) -> str:
    """'pt_BR' / 'PT-br' -> 'pt-br' (lookups are case-insensitive)."""
    return (lang or "").strip().replace("_", "-").lower()


def lang_chain(lang: str) -> list[str]:
    """'pt-br' -> ['pt-br', 'pt']; '' -> []."""
    code = normalize(lang)
    if not code:
        return []
    out = [code]
    base = code.split("-")[0]
    if base != code:
        out.append(base)
    return out


def _read_json(path: str) -> Dict[str, str]:
    """A {key: text} file, cached by modification time. Bad files read as empty."""
    try:
        st = os.stat(path)
    except OSError:
        return {}
    hit = _cache.get(path)
    if hit and hit[0] == st.st_mtime_ns:
        return hit[1]
    data: Dict[str, str] = {}
    try:
        if st.st_size <= MAX_LOCALE_FILE_BYTES:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                data = {k: v for k, v in raw.items()
                        if isinstance(k, str) and isinstance(v, str) and v and not k.startswith("_")}
    except Exception as e:
        log.warning("Couldn't read translations in %s: %s", path, e)
    _cache[path] = (st.st_mtime_ns, data)
    return data


def _locale_file(plugin_dir: str, lang: str) -> Dict[str, str]:
    """locales/<lang>.json in a plugin, matching the file name case-insensitively."""
    d = os.path.join(plugin_dir or "", "locales")
    if not plugin_dir or not os.path.isdir(d):
        return {}
    want = normalize(lang) + ".json"
    for name in os.listdir(d):
        if name.lower().replace("_", "-") == want:
            return _read_json(os.path.join(d, name))
    return {}


def _manifest_default_locale(plugin_dir: str) -> str:
    try:
        with open(os.path.join(plugin_dir, "manifest.json"), "r", encoding="utf-8") as f:
            return str(json.load(f).get("default_locale") or "en")
    except Exception:
        return "en"


# ── Language-pack tables ──────────────────────────────────────────────────────

_PACKS = {"at": 0.0, "dirs": {}}


def _installed_packs() -> Dict[str, list]:
    """language code -> folders of installed packs (not turned off), from
    their manifests only; refreshed every 30 seconds."""
    import time
    if time.monotonic() - _PACKS["at"] < 30:
        return _PACKS["dirs"]
    try:
        from ..core import i18n
        from . import layout
    except (ImportError, ValueError):
        from core import i18n
        from plugins import layout
    out: Dict[str, list] = {}
    root = os.path.join(layout.plugins_root(), "languages")
    disabled = i18n._disabled_language_plugins()
    if os.path.isdir(root):
        for entry in sorted(os.listdir(root)):
            path = os.path.join(root, entry)
            try:
                with open(os.path.join(path, "manifest.json"), "r", encoding="utf-8") as f:
                    m = json.load(f)
            except Exception:
                continue
            pid = m.get("id", entry)
            code = m.get("language_code") or pid.replace("lang-", "").replace("lang_", "")
            if code and pid not in disabled:
                out.setdefault(normalize(code), []).append(path)
    _PACKS.update(at=time.monotonic(), dirs=out)
    return out


def _pack_dirs(lang: str) -> list[str]:
    """Language-pack folders that may hold plugins/<id>.json for `lang`:
    installed packs first, then the built-in one (unless turned off)."""
    try:
        from ..core import i18n
    except (ImportError, ValueError):
        from core import i18n
    code = normalize(lang)
    out = []
    try:
        out.extend(_installed_packs().get(code, []))
    except Exception as e:
        log.debug("language pack scan failed: %s", e)
    builtin = i18n._builtin_pack(code)
    if builtin and builtin.get("path") and builtin["path"] not in out:
        out.append(builtin["path"])
    return out


def pack_table(lang: str, plugin_id: str) -> Dict[str, str]:
    """Merged plugins/<plugin_id>.json from the language packs for `lang`
    (an installed pack's entries win over the built-in pack's)."""
    if not plugin_id or not re.match(r"^[A-Za-z0-9_-]+$", plugin_id):
        return {}
    merged: Dict[str, str] = {}
    for d in reversed(_pack_dirs(lang)):
        merged.update(_read_json(os.path.join(d, "plugins", plugin_id + ".json")))
    return merged


_OVR = {"at": 0.0, "table": {}}


def _overrides(lang: str) -> Dict[str, str]:
    import time
    if time.monotonic() - _OVR["at"] > 5:
        _OVR.update(at=time.monotonic(), table=_load_overrides())
    table = _OVR["table"]
    for key in (lang, normalize(lang)):
        if isinstance(table.get(key), dict):
            return table[key]
    return {}


def _load_overrides() -> Dict[str, Any]:
    try:
        try:
            from ..core import i18n
        except (ImportError, ValueError):
            from core import i18n
        return i18n.get_i18n_settings().get("custom_translations", {}) or {}
    except Exception:
        return {}


# ── Lookup ────────────────────────────────────────────────────────────────────

def plugin_text(plugin_id: str, key: str, lang: str, default: str = "",
                plugin_dir: str = "", default_locale: str = "") -> str:
    """The text `key` of plugin `plugin_id` in language `lang` (see module docstring)."""
    if not key:
        return default
    chain = lang_chain(lang) or ["en"]
    for code in chain:                                            # 1. admin
        hit = _overrides(code).get(f"{OVERRIDE_PREFIX}{plugin_id}:{key}")
        if isinstance(hit, str) and hit:
            return hit
    for code in chain:                                            # 2. language packs
        hit = pack_table(code, plugin_id).get(key)
        if hit:
            return hit
    if plugin_dir:
        for code in chain:                                        # 3. plugin's locale
            hit = _locale_file(plugin_dir, code).get(key)
            if hit:
                return hit
        dl = default_locale or _manifest_default_locale(plugin_dir)
        for code in lang_chain(dl):                               # 4. plugin's default
            hit = _locale_file(plugin_dir, code).get(key)
            if hit:
                return hit
    return default                                                # 5. as written


def describe(plugin_id: str, description: str, lang: str, plugin_dir: str = "",
             default_locale: str = "") -> str:
    """A plugin's description in `lang`."""
    return plugin_text(plugin_id, "description", lang, description, plugin_dir, default_locale)


def localize_spec(spec, lang: str):
    """
    A copy of a BrokerSpec whose person-facing text (instructions, and the text
    of pause_for_human steps) is in `lang`. Specs that didn't come from a plugin
    (no plugin_id) still get admin overrides and language-pack entries keyed by
    their broker_id. The spec passed in is not changed.
    """
    import copy
    if spec is None or not lang:
        return spec
    pid = getattr(spec, "plugin_id", "") or getattr(spec, "broker_id", "")
    pdir = getattr(spec, "plugin_dir", "")
    keys = getattr(spec, "text_keys", {}) or {}
    out = copy.copy(spec)
    out.steps = [copy.copy(s) for s in spec.steps]
    if spec.instructions:
        out.instructions = plugin_text(pid, keys.get("instructions", "instructions"), lang,
                                       spec.instructions, pdir)
    for i, s in enumerate(out.steps):
        if s.kind == "pause_for_human" and s.text:
            k = f"steps.{i}.text"
            s.text = plugin_text(pid, keys.get(k, k), lang, s.text, pdir)
    return out


def text_entries(spec, description: str = "") -> Dict[str, str]:
    """Every translatable {key: English text} of a broker plugin — what a
    translator needs to write locales/<lang>.json or a pack's plugins/<id>.json."""
    keys = getattr(spec, "text_keys", {}) or {}
    out: Dict[str, str] = {}
    if description:
        out["description"] = description
    if spec is not None:
        if spec.instructions:
            out[keys.get("instructions", "instructions")] = spec.instructions
        for i, s in enumerate(spec.steps):
            if s.kind == "pause_for_human" and s.text:
                k = f"steps.{i}.text"
                out[keys.get(k, k)] = s.text
    return out


def member_language(member) -> str:
    """The language the person running a member's opt-outs reads the app in."""
    user = getattr(member, "user", None)
    lang = getattr(user, "preferred_language", None) if user is not None else None
    if lang:
        return lang
    try:
        try:
            from ..core import i18n
        except (ImportError, ValueError):
            from core import i18n
        return i18n.get_i18n_settings().get("default_language") or "en"
    except Exception:
        return "en"


# ── Validation (install time) ─────────────────────────────────────────────────

def placeholders(text: str) -> set:
    return set(_PLACEHOLDER.findall(text or ""))


def locale_errors(plugin_dir: str, manifest) -> list[str]:
    """
    Problems with a plugin's locales/ folder, given its manifest:
    every declared locale has a file, every file is a flat {key: text} JSON
    object, and each translation uses the same {placeholders} as the text it
    translates (a missing {listing_url} would leave a person without their link).
    """
    errors: list[str] = []
    declared = list(getattr(manifest, "locales", []) or [])
    default_locale = getattr(manifest, "default_locale", "") or "en"
    d = os.path.join(plugin_dir, "locales")
    files, present = {}, set()
    if os.path.isdir(d):
        for name in sorted(os.listdir(d)):
            if not name.endswith(".json"):
                continue
            code = name[:-5]
            present.add(normalize(code))
            path = os.path.join(d, name)
            if not LOCALE_CODE.match(normalize(code)):
                errors.append(f"locales/{name}: the file name isn't a language code")
                continue
            if os.path.getsize(path) > MAX_LOCALE_FILE_BYTES:
                errors.append(f"locales/{name} is larger than {MAX_LOCALE_FILE_BYTES // 1024} KB")
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception as e:
                errors.append(f"locales/{name} isn't valid JSON: {e}")
                continue
            if not isinstance(raw, dict):
                errors.append(f"locales/{name} must be a JSON object of key → text")
                continue
            bad = [k for k, v in raw.items() if not k.startswith("_") and not isinstance(v, str)]
            if bad:
                errors.append(f"locales/{name}: values must be text (check {', '.join(bad[:3])})")
                continue
            files[normalize(code)] = {k: v for k, v in raw.items() if not k.startswith("_")}
    for code in declared:
        if normalize(code) not in present and normalize(code) != "en":
            errors.append(f"manifest lists locale '{code}' but locales/{code}.json is missing")
    base = files.get(normalize(default_locale))
    if base is None and normalize(default_locale) == "en":
        base = _source_texts(plugin_dir, manifest)
    if base:
        for code, table in files.items():
            if code == normalize(default_locale):
                continue
            for k, v in table.items():
                if k in base and placeholders(v) != placeholders(base[k]):
                    errors.append(f"locales/{code}.json '{k}': uses {sorted(placeholders(v))} "
                                  f"but the original uses {sorted(placeholders(base[k]))}")
    return errors


def _source_texts(plugin_dir: str, manifest) -> Dict[str, str]:
    """The plugin's own text, keyed, for placeholder checks."""
    spec = None
    if getattr(manifest, "effective_type", "") == "brokers":
        try:
            from .broker_addon import validate_broker_spec_file
            spec, _ = validate_broker_spec_file(plugin_dir, manifest.spec_file or "spec.json")
        except Exception:
            spec = None
    return text_entries(spec, getattr(manifest, "description", ""))
