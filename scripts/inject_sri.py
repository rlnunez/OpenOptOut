#!/usr/bin/env python3
"""
W3C Subresource Integrity (SRI) Injector.

Scans the built frontend distribution (frontend/dist/index.html), computes
SHA-384 cryptographic integrity digests for all bundled script and stylesheet assets,
and injects 'integrity' and 'crossorigin="anonymous"' attributes conforming to
the W3C Subresource Integrity Recommendation.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(REPO_ROOT, "frontend", "dist")
INDEX_PATH = os.path.join(DIST_DIR, "index.html")


def compute_sri_hash(filepath: str) -> str:
    """Compute W3C sha384 SRI integrity string."""
    with open(filepath, "rb") as f:
        digest = hashlib.sha384(f.read()).digest()
    b64 = base64.b64encode(digest).decode("ascii")
    return f"sha384-{b64}"


def inject_sri() -> int:
    if not os.path.isfile(INDEX_PATH):
        print(f"Error: {INDEX_PATH} not found. Run 'npm run build' first.")
        return 1

    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    modified = False

    def replace_script(match: re.Match) -> str:
        nonlocal modified
        tag = match.group(0)
        src = match.group(1)
        # Normalize relative path to dist file
        clean_src = src.lstrip("/")
        asset_path = os.path.join(DIST_DIR, clean_src)
        if os.path.isfile(asset_path):
            sri = compute_sri_hash(asset_path)
            modified = True
            # Replace tag
            new_tag = tag.rstrip(">").rstrip("/")
            return f'{new_tag} integrity="{sri}" crossorigin="anonymous">'
        return tag

    def replace_link(match: re.Match) -> str:
        nonlocal modified
        tag = match.group(0)
        href = match.group(1)
        clean_href = href.lstrip("/")
        asset_path = os.path.join(DIST_DIR, clean_href)
        if os.path.isfile(asset_path):
            sri = compute_sri_hash(asset_path)
            modified = True
            new_tag = tag.rstrip(">").rstrip("/")
            return f'{new_tag} integrity="{sri}" crossorigin="anonymous">'
        return tag

    # Match <script ... src="..." ...>
    html = re.sub(r'<script\b[^>]*\bsrc=["\']([^"\']+)["\'][^>]*>', replace_script, html)
    # Match <link ... rel="stylesheet" ... href="..." ...> or href then rel
    html = re.sub(r'<link\b[^>]*\bhref=["\']([^"\']+\.css)["\'][^>]*>', replace_link, html)

    if modified:
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            f.write(html)
        print("Successfully injected W3C Subresource Integrity (SRI) hashes into dist/index.html")
    else:
        print("No script or stylesheet tags matched for SRI injection.")

    return 0


if __name__ == "__main__":
    sys.exit(inject_sri())
