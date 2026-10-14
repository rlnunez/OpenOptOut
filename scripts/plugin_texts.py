#!/usr/bin/env python3
"""
List the text the built-in plugins show people, and check each built-in
language pack translates it.

    python3 scripts/plugin_texts.py            # every plugin's keys and English text, as JSON
    python3 scripts/plugin_texts.py --check    # report missing or mismatched translations

A pack translates other plugins in <pack>/plugins/<plugin_id>.json, a flat
{key: text} object (see backend/plugins/plugin_i18n.py). Keys: "description",
"instructions", "steps.<i>.text" (pause_for_human steps), or the key a spec
gave with {"$t": key, "default": text}.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
BUNDLED = os.path.join(ROOT, "backend", "plugins", "bundled")


def source_texts() -> dict:
    """{plugin_id: {key: English text}} for every built-in plugin."""
    from backend.plugins.permissions import PluginManifest
    from backend.plugins.broker_addon import validate_broker_spec_file
    from backend.plugins.plugin_i18n import text_entries
    out = {}
    for mp in sorted(glob.glob(os.path.join(BUNDLED, "*", "*", "manifest.json"))):
        d = os.path.dirname(mp)
        with open(mp, encoding="utf-8") as f:
            m = PluginManifest.from_dict(json.load(f))
        spec = None
        if m.effective_type == "brokers":
            spec, _ = validate_broker_spec_file(d, m.spec_file or "spec.json")
        out[m.id] = text_entries(spec, m.description)
    return out


def problems() -> list:
    """Missing translations, placeholder mismatches and stray keys, per pack."""
    ph = lambda t: sorted(set(re.findall(r"\{(\w+)\}", t)))
    src = source_texts()
    errs = []
    for pack in sorted(glob.glob(os.path.join(BUNDLED, "languages", "lang-*"))):
        name = os.path.basename(pack)
        for pid, texts in src.items():
            path = os.path.join(pack, "plugins", pid + ".json")
            table = {}
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    table = json.load(f)
            for key, text in texts.items():
                if not table.get(key):
                    errs.append(f"{name}: {pid} '{key}' is not translated")
                elif ph(table[key]) != ph(text):
                    errs.append(f"{name}: {pid} '{key}' uses {ph(table[key])}, the original {ph(text)}")
            for key in set(table) - set(texts):
                errs.append(f"{name}: {pid} has '{key}', which the plugin doesn't use")
        for path in glob.glob(os.path.join(pack, "plugins", "*.json")):
            pid = os.path.basename(path)[:-5]
            if pid not in src:
                errs.append(f"{name}: plugins/{pid}.json is for a plugin that isn't built in")
    return errs


if __name__ == "__main__":
    if "--check" in sys.argv:
        errs = problems()
        print("\n".join(errs) or "every built-in language pack translates every built-in plugin")
        sys.exit(1 if errs else 0)
    print(json.dumps(source_texts(), indent=1, ensure_ascii=False))
