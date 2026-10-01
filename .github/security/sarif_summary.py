#!/usr/bin/env python3
"""Print a short Markdown summary of one or more SARIF files.

Used by .github/workflows/security.yml to write a readable table to each
job's summary page (Actions → run → job), so you can see what a scanner
found without opening the Security tab. Standard library only.

    python3 sarif_summary.py "Bandit" bandit.sarif >> "$GITHUB_STEP_SUMMARY"
"""
import collections
import json
import os
import sys

ICON = {"error": "🔴", "warning": "🟠", "note": "🔵", "none": "⚪"}


def main():
    if len(sys.argv) < 3:
        print("usage: sarif_summary.py TITLE FILE [FILE...]", file=sys.stderr)
        return 2
    title, files = sys.argv[1], sys.argv[2:]

    levels = collections.Counter()
    rules = collections.Counter()
    missing = []
    for path in files:
        if not os.path.exists(path):
            missing.append(path)
            continue
        with open(path) as f:
            sarif = json.load(f)
        for run in sarif.get("runs", []):
            # Rule-level default severity, used when a result has no level of its own
            defaults = {}
            for rule in run.get("tool", {}).get("driver", {}).get("rules", []) or []:
                lvl = (rule.get("defaultConfiguration") or {}).get("level")
                if lvl:
                    defaults[rule.get("id")] = lvl
            for res in run.get("results", []) or []:
                rid = res.get("ruleId", "?")
                levels[res.get("level") or defaults.get(rid, "warning")] += 1
                rules[rid] += 1

    total = sum(levels.values())
    print(f"### {title}\n")
    if missing:
        print(f"⚠️ No report produced ({', '.join(missing)}) — check this step's log.\n")
    if total == 0 and not missing:
        print("✅ No findings.\n")
        return 0
    if total:
        print("| Severity | Count |\n|---|---|")
        for lvl in ("error", "warning", "note", "none"):
            if levels[lvl]:
                print(f"| {ICON[lvl]} {lvl} | {levels[lvl]} |")
        print(f"\n**{total} finding(s).** Most common:\n")
        for rid, n in rules.most_common(8):
            print(f"- `{rid}` × {n}")
        print("\nFull details: **Security → Code scanning** (filter by tool).\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
