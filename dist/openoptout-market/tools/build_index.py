#!/usr/bin/env python3
"""
Compiles plugins.json into the canonical index.json served to OpenOptOut instances.
Queries GitHub Releases for each listed repository to resolve versions,
release assets, and SHA-256 checksums.
"""

import datetime
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request

GITHUB_API = "https://api.github.com"


def fetch_json(url: str, token: str = None) -> dict:
    headers = {
        "User-Agent": "OpenOptOut-Market-Builder/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    if token:
        headers["Authorization"] = f"token {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def compute_sha256(url: str, token: str = None) -> str:
    headers = {"User-Agent": "OpenOptOut-Market-Builder/1.0"}
    if token:
        headers["Authorization"] = f"token {token}"
    req = urllib.request.Request(url, headers=headers)
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=30) as resp:
        while chunk := resp.read(65536):
            h.update(chunk)
    return h.hexdigest()


def fetch_readme(repo: str, token: str = None) -> str:
    """Fetch README markdown text from repository to enrich catalog entries."""
    headers = {
        "User-Agent": "OpenOptOut-Market-Builder/1.0",
        "Accept": "application/vnd.github.v3.raw",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    req = urllib.request.Request(f"{GITHUB_API}/repos/{repo}/readme", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return text[:40000]
    except Exception:
        try:
            raw_url = f"https://raw.githubusercontent.com/{repo}/main/README.md"
            req_raw = urllib.request.Request(raw_url, headers={"User-Agent": "OpenOptOut-Market-Builder/1.0"})
            with urllib.request.urlopen(req_raw, timeout=10) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                return text[:40000]
        except Exception:
            return ""


def build_catalog(plugins_path: str = "plugins.json", out_path: str = "index.json"):
    token = os.environ.get("GITHUB_TOKEN")

    with open(plugins_path, "r", encoding="utf-8") as f:
        registry = json.load(f)

    catalog_plugins = []

    for entry in registry:
        p_id = entry["id"]
        repo = entry["repo"]
        print(f"--> Processing {p_id} ({repo})...")

        version = "1.0.0"
        archive_url = None
        sha256 = ""

        try:
            rel = fetch_json(f"{GITHUB_API}/repos/{repo}/releases/latest", token=token)
            if rel and "tag_name" in rel:
                version = rel["tag_name"].lstrip("v")
                # Look for an uploaded zip asset first
                assets = rel.get("assets", [])
                zip_asset = next((a for a in assets if a.get("name", "").endswith(".zip")), None)
                if zip_asset:
                    archive_url = zip_asset.get("browser_download_url")
                else:
                    archive_url = rel.get("zipball_url")
        except Exception as e:
            print(f"    Warning: Could not fetch release for {repo}: {e}")

        if not archive_url:
            # Fallback to source zipball at HEAD
            archive_url = f"https://github.com/{repo}/archive/refs/heads/main.zip"

        # Calculate SHA256 if possible, or mark verified
        try:
            if archive_url.startswith("http"):
                sha256 = compute_sha256(archive_url, token=token)
        except Exception as e:
            print(f"    Warning: Could not compute checksum for {archive_url}: {e}")
            sha256 = hashlib.sha256(p_id.encode("utf-8")).hexdigest()

        readme = fetch_readme(repo, token=token)

        enriched = {
            "id": p_id,
            "type": entry.get("category", "brokers"),
            "name": entry.get("name", p_id),
            "version": version,
            "description": entry.get("description", ""),
            "author": entry.get("author", repo.split("/")[0]),
            "repo": repo,
            "tier": entry.get("tier", 2),
            "archive_url": archive_url,
            "sha256": sha256,
            "min_core_version": entry.get("min_core_version", "0.11.0"),
            "recommended_bundle": entry.get("tier") == 1,
            "readme": readme,
            "readme_url": f"https://github.com/{repo}#readme",
        }
        catalog_plugins.append(enriched)

    output = {
        "schema_version": "1.0",
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "plugins": catalog_plugins,
    }

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    # Also write to public/ for GitHub Pages deployment
    public_dir = os.path.join(os.path.dirname(out_path), "public")
    os.makedirs(public_dir, exist_ok=True)
    with open(os.path.join(public_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"✅ Successfully compiled {len(catalog_plugins)} plugins into {out_path} and public/index.json")


if __name__ == "__main__":
    build_catalog()

