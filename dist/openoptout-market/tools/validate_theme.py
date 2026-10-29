#!/usr/bin/env python3
"""
Validates OpenOptOut theme plugins for manifest correctness, CSS token structure,
and mathematical WCAG 2.2 AA / AAA contrast compliance.
"""

import json
import os
import re
import sys


def srgb_to_linear(channel: float) -> float:
    c = channel / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_code: str) -> float:
    hex_clean = hex_code.strip().lstrip("#")
    if len(hex_clean) == 3:
        hex_clean = "".join(c * 2 for c in hex_clean)
    if len(hex_clean) != 6:
        raise ValueError(f"Invalid hex color: {hex_code}")
    r = int(hex_clean[0:2], 16)
    g = int(hex_clean[2:4], 16)
    b = int(hex_clean[4:6], 16)
    return 0.2126 * srgb_to_linear(r) + 0.7152 * srgb_to_linear(g) + 0.0722 * srgb_to_linear(b)


def contrast_ratio(hex1: str, hex2: str) -> float:
    l1 = relative_luminance(hex1)
    l2 = relative_luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def validate_theme(folder_path: str) -> list[str]:
    errors = []
    manifest_file = os.path.join(folder_path, "manifest.json")
    theme_file = os.path.join(folder_path, "theme.json")
    readme_file = os.path.join(folder_path, "README.md")
    styles_file = os.path.join(folder_path, "styles.css")

    if not os.path.isfile(manifest_file):
        return ["missing manifest.json"]
    if not os.path.isfile(theme_file):
        return ["missing theme.json"]
    if not os.path.isfile(readme_file):
        return ["missing README.md"]

    try:
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:
        return [f"manifest.json parse error: {e}"]

    theme_id = manifest.get("id", "")
    if not theme_id:
        errors.append("manifest.json missing 'id'")
    if manifest.get("type") != "themes":
        errors.append(f"manifest.json type must be 'themes', got '{manifest.get('type')}'")
    if not manifest.get("name"):
        errors.append("manifest.json missing 'name'")

    try:
        with open(theme_file, "r", encoding="utf-8") as f:
            theme_data = json.load(f)
    except Exception as e:
        return [f"theme.json parse error: {e}"]

    colors = theme_data.get("colors", {})
    bg = colors.get("background")
    text = colors.get("text_primary")
    accent = colors.get("accent")

    target_level = manifest.get("wcag_level", "AA").upper()
    req_ratio = 7.0 if target_level == "AAA" else 4.5

    if bg and text:
        try:
            ratio = contrast_ratio(bg, text)
            if ratio < req_ratio:
                errors.append(
                    f"text_primary ({text}) on background ({bg}) contrast is {ratio:.2f}:1 "
                    f"— below WCAG {target_level} minimum ({req_ratio:.1f}:1)"
                )
        except Exception as e:
            errors.append(f"error calculating contrast for background/text: {e}")

    if bg and accent:
        try:
            accent_ratio = contrast_ratio(bg, accent)
            # UI components / accents must meet at least 3.0:1 (AA) or 4.5:1 (AAA)
            min_accent = 4.5 if target_level == "AAA" else 3.0
            if accent_ratio < min_accent:
                errors.append(
                    f"accent ({accent}) on background ({bg}) contrast is {accent_ratio:.2f}:1 "
                    f"— below WCAG {target_level} component minimum ({min_accent:.1f}:1)"
                )
        except Exception as e:
            errors.append(f"error calculating contrast for background/accent: {e}")

    if os.path.isfile(styles_file):
        try:
            with open(styles_file, "r", encoding="utf-8") as f:
                css_content = f.read()
            if "outline: none" in css_content and ":focus" not in css_content:
                errors.append("styles.css uses 'outline: none' without declaring accessible focus indicators")
        except Exception as e:
            errors.append(f"styles.css read error: {e}")

    return errors


def main():
    target_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    errors = validate_theme(target_dir)
    if errors:
        print(f"FAIL  {target_dir}")
        for err in errors:
            print(f"      - {err}")
        sys.exit(1)
    else:
        print(f"PASS  {target_dir} passed theme structure and WCAG accessibility checks.")
        sys.exit(0)


if __name__ == "__main__":
    main()
