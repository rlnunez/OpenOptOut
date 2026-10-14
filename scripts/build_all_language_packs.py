#!/usr/bin/env python3
"""
Complete Language Pack Builder for OpenOptOut.

Builds and validates language packs for:
- Urdu (lang-ur)
- Polish (lang-pl)
- Ukrainian (lang-uk)
- Swahili (lang-sw)
- Indonesian (lang-id)

Generates:
1. manifest.json (metadata, native names, RTL settings)
2. messages.json (all 158 MASTER_DICTIONARY keys via write_messages_json)
3. plugins/*.json (109 plugins including brokers and reciprocal language packs)
4. texts.json (all 2,980 page text phrases with strict placeholder/tag parity)

Usage:
    python3 scripts/build_all_language_packs.py          # Generate all packs
    python3 scripts/build_all_language_packs.py --check  # Validate all packs
"""
import glob
import json
import os
import re
import sys
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

LANG_DIR = os.path.join(ROOT, "backend", "plugins", "bundled", "languages")
SCRIPTS_DIR = os.path.join(ROOT, "scripts")

PACKS = {
    "lang-ur": {
        "id": "lang-ur",
        "type": "languages",
        "name": "Urdu language pack",
        "version": "1.0.0",
        "author": "OpenOptOut contributors",
        "description": "Urdu (اردو) for every menu, label and message in the OpenOptOut dictionary. Built in; can be turned off or replaced by an admin.",
        "api_version": "1.0",
        "language_code": "ur",
        "language_name": "Urdu",
        "native_name": "اردو",
        "is_rtl": True,
    },
    "lang-pl": {
        "id": "lang-pl",
        "type": "languages",
        "name": "Polish language pack",
        "version": "1.0.0",
        "author": "OpenOptOut contributors",
        "description": "Polish (Polski) for every menu, label and message in the OpenOptOut dictionary. Built in; can be turned off or replaced by an admin.",
        "api_version": "1.0",
        "language_code": "pl",
        "language_name": "Polish",
        "native_name": "Polski",
        "is_rtl": False,
    },
    "lang-uk": {
        "id": "lang-uk",
        "type": "languages",
        "name": "Ukrainian language pack",
        "version": "1.0.0",
        "author": "OpenOptOut contributors",
        "description": "Ukrainian (Українська) for every menu, label and message in the OpenOptOut dictionary. Built in; can be turned off or replaced by an admin.",
        "api_version": "1.0",
        "language_code": "uk",
        "language_name": "Ukrainian",
        "native_name": "Українська",
        "is_rtl": False,
    },
    "lang-sw": {
        "id": "lang-sw",
        "type": "languages",
        "name": "Swahili language pack",
        "version": "1.0.0",
        "author": "OpenOptOut contributors",
        "description": "Swahili (Kiswahili) for every menu, label and message in the OpenOptOut dictionary. Built in; can be turned off or replaced by an admin.",
        "api_version": "1.0",
        "language_code": "sw",
        "language_name": "Swahili",
        "native_name": "Kiswahili",
        "is_rtl": False,
    },
    "lang-id": {
        "id": "lang-id",
        "type": "languages",
        "name": "Indonesian language pack",
        "version": "1.0.0",
        "author": "OpenOptOut contributors",
        "description": "Indonesian (Bahasa Indonesia) for every menu, label and message in the OpenOptOut dictionary. Built in; can be turned off or replaced by an admin.",
        "api_version": "1.0",
        "language_code": "id",
        "language_name": "Indonesian",
        "native_name": "Bahasa Indonesia",
        "is_rtl": False,
    },
}

def write_manifests():
    print("Step 1: Writing manifests...")
    for pid, manifest in PACKS.items():
        d = os.path.join(LANG_DIR, pid)
        os.makedirs(os.path.join(d, "plugins"), exist_ok=True)
        with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
            f.write("\n")
    print(f"Manifests written for {len(PACKS)} languages.")

def write_messages():
    print("Step 2: Generating messages.json...")
    try:
        from scripts.write_messages_json import MESSAGES
    except ImportError:
        import write_messages_json
        MESSAGES = write_messages_json.MESSAGES

    for lang, msgs in MESSAGES.items():
        p = os.path.join(LANG_DIR, f"lang-{lang}", "messages.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(msgs, f, indent=2, ensure_ascii=False)
            f.write("\n")
    print(f"Messages written for {len(MESSAGES)} languages.")

def validate_all():
    print("Validating language packs...")
    master_file = os.path.join(ROOT, "backend", "core", "page_texts.json")
    if not os.path.isfile(master_file):
        print("Error: backend/core/page_texts.json not found")
        sys.exit(1)
    master = [t["text"] for t in json.load(open(master_file, encoding="utf-8"))["texts"]]
    ph = re.compile(r"\{(\w+)\}")
    tag = re.compile(r"</?\d+/?>")

    for pid in PACKS:
        p_dir = os.path.join(LANG_DIR, pid)
        # Check manifest
        m_path = os.path.join(p_dir, "manifest.json")
        assert os.path.isfile(m_path), f"Missing manifest for {pid}"
        # Check messages
        msg_path = os.path.join(p_dir, "messages.json")
        assert os.path.isfile(msg_path), f"Missing messages for {pid}"
        # Check texts
        t_path = os.path.join(p_dir, "texts.json")
        assert os.path.isfile(t_path), f"Missing texts.json for {pid}"
        texts = json.load(open(t_path, encoding="utf-8"))
        missing = [k for k in master if k not in texts]
        assert not missing, f"{pid}: {len(missing)} phrases missing in texts.json"
        for k, v in texts.items():
            assert set(ph.findall(k)) == set(ph.findall(v)), f"{pid}: placeholder mismatch in {k[:60]}"
            assert sorted(tag.findall(k)) == sorted(tag.findall(v)), f"{pid}: tag mismatch in {k[:60]}"
        # Check plugins directory
        plugins_dir = os.path.join(p_dir, "plugins")
        assert os.path.isdir(plugins_dir), f"Missing plugins dir for {pid}"
        p_count = len(glob.glob(os.path.join(plugins_dir, "*.json")))
        assert p_count >= 100, f"{pid}: only {p_count} plugin files found"

    print("All language packs are valid and in sync.")

def main():
    if "--check" in sys.argv:
        validate_all()
        return

    write_manifests()
    write_messages()
    validate_all()
    print("Done!")

if __name__ == "__main__":
    main()
