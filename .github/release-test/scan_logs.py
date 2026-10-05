#!/usr/bin/env python3
"""Find errors in `docker compose logs` output and summarise them in Markdown.

    python3 scan_logs.py "Fresh install" compose.log out.md

Looks for:
  - app log lines at ERROR / CRITICAL level  ("... [ERROR] [module] message")
  - Python tracebacks (with the final exception line)
  - uvicorn / FastAPI "Exception in ASGI application"
  - nginx [error] / [emerg] / [crit] lines
Repeated messages are grouped and counted (numbers and IDs are ignored when
grouping, so "job 17 failed" and "job 18 failed" count as one problem).

Exit code 1 if anything was found, else 0.
"""
import collections
import re
import sys

LEVEL = re.compile(r"\[(ERROR|CRITICAL)\]|\b(ERROR|CRITICAL):\s")
NGINX = re.compile(r"\[(error|emerg|crit|alert)\]")
TB_START = "Traceback (most recent call last)"
PREFIX = re.compile(r"^(?P<svc>[\w.-]+)\s+\|\s?(?P<msg>.*)$")   # "openoptout-api  | message"
NORMALISE = re.compile(r"\b(0x[0-9a-f]+|[0-9a-f]{8,}|\d+(\.\d+)?)\b", re.I)
TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d[,.\d]*\s*")


def main():
    title, log_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(log_path, errors="replace") as f:
        lines = f.read().splitlines()

    problems = collections.OrderedDict()   # key -> {"count", "service", "example", "trace"}

    def add(service, message, trace=None):
        msg = TIMESTAMP.sub("", message).strip()
        key = (service, NORMALISE.sub("#", msg)[:200])
        if key not in problems:
            problems[key] = {"count": 0, "service": service, "example": msg[:400], "trace": trace}
        problems[key]["count"] += 1

    i = 0
    while i < len(lines):
        m = PREFIX.match(lines[i])
        svc, msg = (m.group("svc"), m.group("msg")) if m else ("", lines[i])
        if TB_START in msg:
            trace = [msg]
            j = i + 1
            while j < len(lines):
                m2 = PREFIX.match(lines[j])
                nxt = m2.group("msg") if m2 else lines[j]
                trace.append(nxt)
                j += 1
                # The exception line is the first non-indented line after the frames
                if nxt and not nxt.startswith((" ", "\t", "Traceback")) and len(trace) > 2:
                    break
                if len(trace) > 80:
                    break
            add(svc, f"Traceback → {trace[-1].strip()}", trace="\n".join(trace[-30:]))
            i = j
            continue
        if LEVEL.search(msg) or NGINX.search(msg) or "Exception in ASGI application" in msg:
            add(svc, msg)
        i += 1

    md = [f"### Container logs — {title}", ""]
    if not problems:
        md.append("✅ No errors in the container logs.\n")
    else:
        total = sum(p["count"] for p in problems.values())
        md.append(f"**❌ {len(problems)} distinct error(s), {total} occurrence(s):**\n")
        md.append("| Container | × | Message |\n|---|---|---|")
        for p in list(problems.values())[:40]:
            md.append(f"| {p['service'] or '?'} | {p['count']} | "
                      f"{p['example'][:250].replace('|', '¦')} |")
        traces = [p for p in problems.values() if p["trace"]]
        for p in traces[:5]:
            md += ["", f"<details><summary>Traceback: {p['example'][:120]}</summary>", "",
                   "```", p["trace"], "```", "", "</details>"]
        md.append("")
    md.append("Full logs: download the **release-test-*** artifact → `logs/`.\n")
    with open(out_path, "w") as f:
        f.write("\n".join(md))
    print("\n".join(md))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
