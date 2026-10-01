#!/usr/bin/env python3
"""Convert ShellCheck `-f json1` output (stdin) into SARIF 2.1.0 (stdout).

ShellCheck has no native SARIF output; this lets its findings appear in the
repository's Security → Code scanning tab next to every other scanner.
Standard library only.
"""
import json
import sys

LEVELS = {"error": "error", "warning": "warning", "info": "note", "style": "note"}

data = json.load(sys.stdin)
comments = data.get("comments", data) if isinstance(data, dict) else data

rules, results = {}, []
for c in comments:
    rule_id = f"SC{c['code']}"
    rules.setdefault(rule_id, {
        "id": rule_id,
        "name": rule_id,
        "shortDescription": {"text": c["message"][:200]},
        "helpUri": f"https://www.shellcheck.net/wiki/{rule_id}",
    })
    results.append({
        "ruleId": rule_id,
        "level": LEVELS.get(c.get("level"), "warning"),
        "message": {"text": c["message"]},
        "locations": [{
            "physicalLocation": {
                "artifactLocation": {"uri": c["file"].lstrip("./")},
                "region": {
                    "startLine": c["line"],
                    "startColumn": c["column"],
                    "endLine": c.get("endLine", c["line"]),
                    "endColumn": max(c.get("endColumn", c["column"] + 1), c["column"] + 1),
                },
            }
        }],
    })

json.dump({
    "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
    "version": "2.1.0",
    "runs": [{
        "tool": {"driver": {
            "name": "ShellCheck",
            "informationUri": "https://www.shellcheck.net",
            "rules": list(rules.values()),
        }},
        "results": results,
    }],
}, sys.stdout, indent=2)
