"""
Install-time code inspection for every plugin.

Scans a plugin's files before it's installed (and again whenever it's enabled)
for things a plugin has no business doing, given the host APIs and sandbox it
runs in:

  high    blocks the install
          - running programs (subprocess, os.system, os.exec*, pty, ...)
          - dynamic code: eval / exec / compile / __import__ / importlib /
            marshal / pickle loading / runpy, and reaching into __builtins__
          - native code access (ctypes, cffi)
          - writing, deleting or changing files (open(..., "w"), os.remove,
            shutil.*, pathlib write_text, ...): persistent data goes through
            the storage API, and the plugin's own folder is read-only
          - network libraries in a plugin that wasn't granted "network"
          - files that can't be inspected: compiled or native binaries,
            shell scripts, executables, Python that doesn't parse, and any code
            at all in a data-only (themes, languages) plugin
  medium  shown to the admin in the upload wizard
          - direct network libraries in a plugin that has "network" (allowed,
            but they bypass the host-mediated http.fetch)
          - file modes that aren't literal strings, temp files, long encoded
            string blobs, unexpected file types

This is a static, heuristic check. A determined author can hide intent from
any static scan, so it complements rather than replaces the runtime controls:
the sandbox (read-only plugin folder, no exec, network namespace), the
per-type permission limits, the host-method allowlist, and the launch-time
integrity check that refuses to run a plugin whose files changed.
"""

import ast
import os
import re
from dataclasses import dataclass, asdict

TEXT_EXTENSIONS = {".py", ".json", ".md", ".txt", ".csv", ".yaml", ".yml", ".toml",
                   ".cfg", ".ini", ".html", ".css", ".po", ".pot", ".xml", ".svg"}
ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf"}
BLOCKED_EXTENSIONS = {".so", ".pyd", ".dll", ".dylib", ".exe", ".bin", ".pyc", ".pyo",
                      ".sh", ".bash", ".zsh", ".bat", ".cmd", ".ps1", ".jar", ".class",
                      ".com", ".msi", ".app", ".elf", ".node", ".wasm"}

# module (or dotted prefix) -> reason. Importing any of these is high risk.
DANGEROUS_MODULES = {
    "subprocess": "runs other programs",
    "pty": "runs other programs",
    "multiprocessing": "starts processes",
    "ctypes": "calls native code",
    "cffi": "calls native code",
    "importlib": "loads code dynamically",
    "runpy": "runs code dynamically",
    "code": "runs code dynamically",
    "codeop": "compiles code dynamically",
    "marshal": "loads compiled code",
    "shutil": "copies, moves or deletes files",
}
NETWORK_MODULES = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib",
                   "telnetlib", "smtplib", "imaplib", "poplib", "ssl", "websocket",
                   "websockets", "asyncio.streams", "xmlrpc", "paramiko", "urllib3"}
# An email-provider plugin's job is talking to its mail service (SMTP/IMAP, or a
# mail API over HTTPS, to its declared outbound domains), so these are expected
# there rather than worth a note. Raw sockets still get one.
EMAIL_PROTOCOL_MODULES = {"smtplib", "imaplib", "poplib", "ssl", "email",
                          "requests", "httpx", "urllib", "urllib3", "http"}

DANGEROUS_BUILTINS = {"eval": "runs code built at runtime", "exec": "runs code built at runtime",
                      "compile": "compiles code at runtime", "__import__": "loads code dynamically",
                      "breakpoint": "opens a debugger"}
OS_PROCESS_CALLS = {"system", "popen", "fork", "forkpty", "kill", "killpg", "startfile",
                    "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe",
                    "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp",
                    "spawnvpe", "posix_spawn", "posix_spawnp"}
OS_FILE_CALLS = {"remove", "unlink", "rename", "renames", "replace", "mkdir", "makedirs",
                 "rmdir", "removedirs", "chmod", "chown", "lchown", "symlink", "link",
                 "truncate", "open", "write", "mkfifo", "mknod", "utime"}
# pathlib-style methods that change files. (Not rename/replace: str and many
# other types have methods with those names.)
PATH_WRITE_METHODS = {"write_text", "write_bytes", "touch", "mkdir", "unlink", "rmdir",
                      "chmod", "symlink_to", "hardlink_to", "link_to"}
PICKLE_LOADS = {"load", "loads", "Unpickler"}

_BLOB_RE = re.compile(r"^[A-Za-z0-9+/=_\-]{1500,}$")
_MODE_RE = re.compile(r"^[rwxabtU+]{1,4}$")


@dataclass
class Finding:
    severity: str   # high | medium
    file: str
    line: int
    rule: str
    message: str


def _dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


class _Visitor(ast.NodeVisitor):
    def __init__(self, rel, ptype, has_network, add):
        self.rel, self.ptype, self.has_network, self.add = rel, ptype, has_network, add
        self.aliases = {}   # local name -> module it refers to

    def _module(self, name, line):
        root = name.split(".")[0]
        if root in DANGEROUS_MODULES:
            self.add("high", line, f"import:{root}", f"imports {name}, which {DANGEROUS_MODULES[root]}")
        elif root == "pickle" or root == "dill" or root == "shelve":
            self.add("high", line, f"import:{root}", f"imports {name}, which can run code while loading data")
        elif root in NETWORK_MODULES:
            email_ok = self.ptype == "email" and root in EMAIL_PROTOCOL_MODULES
            if not self.has_network:
                self.add("high", line, f"network:{root}",
                         f"imports {name} but the plugin doesn't request the 'network' permission")
            elif not email_ok:
                self.add("medium", line, f"network:{root}",
                         f"imports {name}: direct network access (allowed with 'network', but "
                         "it bypasses the host-mediated http.fetch)")
        elif root == "tempfile":
            self.add("medium", line, "tempfile", "uses temporary files (only its private /tmp is writable)")

    def visit_Import(self, node):
        for a in node.names:
            self.aliases[a.asname or a.name.split(".")[0]] = a.name
            self._module(a.name, node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        mod = node.module or ""
        if node.level == 0:
            self._module(mod, node.lineno)
        for a in node.names:
            self.aliases[a.asname or a.name] = f"{mod}.{a.name}" if mod else a.name
        self.generic_visit(node)

    def visit_Name(self, node):
        if node.id in ("__builtins__", "builtins"):
            self.add("high", node.lineno, "builtins", "reaches into __builtins__, a way to hide dynamic code")
        self.generic_visit(node)

    def visit_Call(self, node):
        func = node.func
        name = _dotted(func)
        resolved = name
        head = name.split(".")[0]
        if head in self.aliases:
            resolved = self.aliases[head] + name[len(head):]
        leaf = resolved.split(".")[-1]
        line = node.lineno

        if isinstance(func, ast.Name) and func.id in DANGEROUS_BUILTINS:
            self.add("high", line, f"call:{func.id}", f"calls {func.id}(), which {DANGEROUS_BUILTINS[func.id]}")
        elif resolved.startswith("os.") and leaf in OS_PROCESS_CALLS:
            self.add("high", line, "os-process", f"calls {resolved}(), which runs or signals other programs")
        elif resolved.startswith("os.") and leaf in OS_FILE_CALLS:
            self.add("high", line, "os-file", f"calls {resolved}(), which changes files")
        elif head in ("pickle", "dill", "shelve") or resolved.split(".")[0] in ("pickle", "dill", "shelve"):
            if leaf in PICKLE_LOADS:
                self.add("high", line, "pickle-load", f"calls {resolved}(), which can run code while loading")
        elif isinstance(func, ast.Attribute) and func.attr in PATH_WRITE_METHODS \
                and not resolved.startswith(("plugin.", "self.", "storage.")):
            self.add("high", line, "path-write", f"calls .{func.attr}(), which changes files")
        elif isinstance(func, ast.Name) and func.id == "getattr" and node.args and \
                isinstance(node.args[0], ast.Name) and node.args[0].id in ("__builtins__", "builtins"):
            self.add("high", line, "builtins", "looks up builtins by name, a way to hide dynamic code")

        # open(...), io/codecs.open(...), io.FileIO(...), os.fdopen(...), and
        # method-style .open(...) (pathlib.Path.open, zipfile, ...): any of them
        # with a write mode changes files.
        opener = (isinstance(func, ast.Name) and func.id == "open") or \
            resolved in ("io.open", "codecs.open", "io.FileIO", "os.fdopen") or \
            (isinstance(func, ast.Attribute) and func.attr in ("open", "FileIO"))
        if opener:
            # The mode is the 2nd argument for open()/FileIO/fdopen but the 1st
            # for method-style .open() (Path.open("w")), so look at both: a short
            # literal made only of mode letters is the mode.
            candidates = [a for a in node.args[:2]] + [kw.value for kw in node.keywords if kw.arg == "mode"]
            literal_modes = [c.value for c in candidates if isinstance(c, ast.Constant)
                             and isinstance(c.value, str) and _MODE_RE.match(c.value)]
            if any(ch in m for m in literal_modes for ch in "wax+"):
                mode = next(m for m in literal_modes if any(ch in m for ch in "wax+"))
                self.add("high", line, "file-write",
                         f"opens a file for writing (mode {mode!r}); plugins keep data "
                         "through the storage API")
            elif any(kw.arg == "mode" and not isinstance(kw.value, ast.Constant) for kw in node.keywords) \
                    or (len(node.args) >= 2 and not isinstance(node.args[1], ast.Constant)
                        and not literal_modes):
                self.add("medium", line, "file-mode", "opens a file with a mode that isn't a literal string")
        self.generic_visit(node)

    def visit_Constant(self, node):
        if isinstance(node.value, str) and _BLOB_RE.match(node.value):
            self.add("medium", node.lineno, "encoded-blob",
                     f"contains a {len(node.value)}-character encoded string; check what it decodes to")


def inspect_plugin_code(plugin_dir: str, manifest) -> list[dict]:
    """Findings for every file in plugin_dir, as dicts (severity, file, line,
    rule, message). Empty means nothing was flagged."""
    ptype = manifest.effective_type
    has_network = "network" in (manifest.permissions or [])
    data_only = manifest.is_data_only
    findings = []

    for base, dirs, files in os.walk(plugin_dir):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for fname in sorted(files):
            full = os.path.join(base, fname)
            rel = os.path.relpath(full, plugin_dir)
            add = lambda sev, line, rule, msg, rel=rel: findings.append(Finding(sev, rel, line, rule, msg))
            ext = os.path.splitext(fname)[1].lower()
            if os.path.islink(full):
                add("high", 0, "symlink", "is a symbolic link")
                continue
            try:
                with open(full, "rb") as f:
                    head = f.read(4)
            except OSError as e:
                add("high", 0, "unreadable", f"can't be read: {e}")
                continue
            if ext in BLOCKED_EXTENSIONS or head.startswith((b"\x7fELF", b"MZ", b"\xca\xfe\xba\xbe", b"\xcf\xfa\xed\xfe")):
                add("high", 0, "binary", "is a compiled, native or script file that can't be inspected")
                continue
            if head.startswith(b"#!"):
                add("high", 0, "script", "is an executable script")
                continue
            if data_only and ext == ".py":
                add("high", 0, "code-in-data-plugin", f"is code, but '{ptype}' plugins are data only")
                continue
            if ext not in TEXT_EXTENSIONS | ASSET_EXTENSIONS and fname != "LICENSE":
                add("medium", 0, "file-type", f"has an unexpected file type ({ext or 'no extension'})")
            if ext != ".py":
                continue
            try:
                with open(full, encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=rel)
            except (SyntaxError, UnicodeDecodeError, ValueError) as e:
                add("high", 0, "unparseable", f"is Python that can't be parsed, so it can't be inspected ({e})")
                continue
            except (RecursionError, MemoryError):
                # e.g. "x+x+x+…" thousands of terms long. Found by fuzzing: this used
                # to escape as an exception and fail the upload with a server error.
                add("high", 0, "unparseable", "is Python nested too deeply to inspect")
                continue
            try:
                _Visitor(rel, ptype, has_network, lambda sev, line, rule, msg, add=add: add(sev, line, rule, msg)).visit(tree)
            except RecursionError:
                add("high", 0, "unparseable", "is Python nested too deeply to inspect")
    return [asdict(f) for f in findings]


def summarize(findings: list[dict]) -> dict:
    high = [f for f in findings if f["severity"] == "high"]
    medium = [f for f in findings if f["severity"] == "medium"]
    fmt = lambda f: f"{f['file']}" + (f":{f['line']}" if f["line"] else "") + f" {f['message']}"
    return {"clean": not findings, "blocked": bool(high),
            "high": [fmt(f) for f in high], "medium": [fmt(f) for f in medium],
            "findings": findings}
