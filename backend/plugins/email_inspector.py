"""
Email-provider plugin inspector.

Email-provider plugins are a trusted class (they legitimately send member PII to
a mail API), so they're exempt from the read_pii+network block. That trust comes
with a condition the operator required: the host must actively inspect the plugin
for the abuse this class could hide — exfiltration smuggled into the SEND itself.
A malicious "email provider" could:
  - hardcode a destination address (BCC/CC/to) so a copy of every opt-out goes
    somewhere the operator never intended;
  - hide an encoded/encrypted payload or extra recipient in the message;
  - contact a mail host other than the one it declared.

This inspector performs a STATIC scan of the plugin's source for those patterns.
It is a heuristic safety net, not a proof — it complements (does not replace) the
runtime enforcement, where the host controls the recipient list and verifies what
the plugin reports sending to (see manager.dispatch_email_send). Findings are
surfaced to the admin at install/enable time.

Returns a list of findings; empty = nothing suspicious found. The caller decides
whether findings block enable or just warn (default: warn + require ack).
"""

import ast
import os
import re

# Email address literal (a hardcoded recipient is the primary risk).
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Names/attrs that indicate setting a recipient — a literal near these is worse.
_RECIPIENT_HINTS = ("bcc", "cc", "to", "rcpt", "recipient", "sendmail", "add_bcc")

# Calls/idioms that suggest hiding data (encoding/encryption of content).
# NOTE: base64 specifically is EXPECTED in email-API plugins (Gmail/Graph require
# the raw message to be base64url-encoded), so base64 alone is informational, not
# alarming. Encryption/marshal/pickle are more suspicious.
_OBFUSCATION_HINTS = ("b64encode", "b64decode", "base64", "fernet", "encrypt",
                      "codecs.encode", "bytes.fromhex", "marshal", "pickle.dumps")
_EXPECTED_IN_EMAIL = ("b64encode", "b64decode", "base64")  # normal for mail APIs


def _scan_source(path: str, findings: list):
    try:
        src = open(path, encoding="utf-8", errors="replace").read()
    except Exception as e:
        findings.append(("read_error", path, str(e)))
        return

    # 1) Hardcoded email address literals anywhere in the source.
    for m in _EMAIL_RE.finditer(src):
        addr = m.group(0)
        # Ignore obvious example/placeholder addresses.
        if addr.lower().endswith((".example", "@example.com", "@example.org")):
            continue
        line = src.count("\n", 0, m.start()) + 1
        # Is it near a recipient-setting hint? (higher severity)
        window = src[max(0, m.start() - 60):m.end() + 20].lower()
        near_recipient = any(h in window for h in _RECIPIENT_HINTS)
        findings.append((
            "hardcoded_email" if not near_recipient else "hardcoded_recipient",
            f"{os.path.basename(path)}:{line}", addr,
        ))

    # 2) AST scan for obfuscation idioms and direct bcc/cc assignment to literals.
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        # RecursionError/MemoryError: absurdly deep nesting (found by fuzzing).
        findings.append(("parse_error", os.path.basename(path), "could not parse"))
        return

    for node in ast.walk(tree):
        # base64/encrypt/etc. calls
        if isinstance(node, ast.Call):
            fn = _call_name(node.func)
            if fn and any(h in fn.lower() for h in _OBFUSCATION_HINTS):
                # base64 is normal for mail APIs; mark it informational, not the
                # same as encryption/marshal which are more suspicious.
                kind = ("expected_encoding"
                        if any(h in fn.lower() for h in _EXPECTED_IN_EMAIL)
                        else "obfuscation_call")
                findings.append((kind,
                                 f"{os.path.basename(path)}:{getattr(node,'lineno','?')}", fn))
            # Recipient set as a keyword arg to a call: send(bcc="x@y"), sendmail(to=[...])
            for kw in node.keywords:
                if kw.arg and kw.arg.lower() in _RECIPIENT_FIELDS and _has_email_literal(kw.value):
                    findings.append(("literal_recipient_kwarg",
                                     f"{os.path.basename(path)}:{getattr(node,'lineno','?')}",
                                     kw.arg.lower()))
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                # 1) Variable assignment: to/cc/bcc/recipients = "x@y"
                name = _target_name(tgt)
                if name and name.lower() in _RECIPIENT_FIELDS and _has_email_literal(node.value):
                    findings.append(("literal_recipient_assignment",
                                     f"{os.path.basename(path)}:{node.lineno}", name))
                # 2) Header/subscript assignment: msg['Bcc'] = "x@y", msg["To"] = ...
                if isinstance(tgt, ast.Subscript):
                    key = _subscript_key(tgt)
                    if key and key.lower() in _RECIPIENT_FIELDS and _has_email_literal(node.value):
                        findings.append(("literal_recipient_header",
                                         f"{os.path.basename(path)}:{node.lineno}", key.lower()))


# Recipient field names we care about — To, Cc, AND Bcc (all three lines).
_RECIPIENT_FIELDS = {"to", "cc", "bcc", "recipient", "recipients", "rcpt", "rcpt_to"}


def _has_email_literal(value) -> bool:
    """True if an AST value node contains a hardcoded (non-example) email address,
    directly or inside a list/tuple of literals."""
    def _check_str(s):
        if not isinstance(s, str):
            return False
        if s.lower().endswith((".example", "@example.com", "@example.org")):
            return False
        return bool(_EMAIL_RE.search(s))
    if isinstance(value, ast.Constant):
        return _check_str(value.value)
    if isinstance(value, (ast.List, ast.Tuple)):
        for el in value.elts:
            if isinstance(el, ast.Constant) and _check_str(el.value):
                return True
    return False


def _subscript_key(sub):
    """Get a string subscript key, e.g. msg['Bcc'] -> 'Bcc'."""
    idx = sub.slice
    if isinstance(idx, ast.Constant) and isinstance(idx.value, str):
        return idx.value
    return None


def _call_name(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts = []
        cur = func
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr); cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def _target_name(tgt):
    if isinstance(tgt, ast.Name):
        return tgt.id
    if isinstance(tgt, ast.Attribute):
        return tgt.attr
    return None


def inspect_email_plugin(plugin_dir: str) -> list:
    """
    Statically scan every .py file in an email-provider plugin's directory for
    hidden/hardcoded recipients and obfuscation. Returns a list of
    (kind, location, detail) findings. Empty means nothing flagged.
    """
    findings: list = []
    if not os.path.isdir(plugin_dir):
        return [("no_dir", plugin_dir, "plugin directory not found")]
    for root, _dirs, files in os.walk(plugin_dir):
        for f in files:
            if f.endswith(".py"):
                _scan_source(os.path.join(root, f), findings)
    return findings


def summarize_findings(findings: list) -> dict:
    """Group findings for the admin UI, flagging the high-severity ones."""
    high = [f for f in findings if f[0] in
            ("hardcoded_recipient", "literal_recipient_assignment",
             "literal_recipient_header", "literal_recipient_kwarg")]
    medium = [f for f in findings if f[0] in ("hardcoded_email", "obfuscation_call")]
    info = [f for f in findings if f[0] == "expected_encoding"]
    other = [f for f in findings if f not in high and f not in medium and f not in info]
    return {
        "clean": not high and not medium,   # informational findings don't make it "unclean"
        "high": [{"kind": k, "where": w, "detail": d} for k, w, d in high],
        "medium": [{"kind": k, "where": w, "detail": d} for k, w, d in medium],
        "info": [{"kind": k, "where": w, "detail": d} for k, w, d in info],
        "other": [{"kind": k, "where": w, "detail": d} for k, w, d in other],
        "total": len(findings),
    }
