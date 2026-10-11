"""
Keeping personal details out of CAPTCHA images and requests.

Anything about a CAPTCHA that's stored or sent anywhere goes through here:

  * Only the CAPTCHA itself is captured: a crop around the widget or puzzle
    image, never the whole page (which shows the person's name and address
    in the form being filled).
  * Inside that crop, every form field and every piece of text that matches
    one of the person's saved details is covered with a solid box.
  * The result is drawn again as a brand-new image (no layers, no metadata,
    no original pixels under the boxes), so the boxes can't be lifted off.
  * The page address loses its query string and fragment, and its path too if
    the path contains any saved detail (people-search sites put names there).

The solving service only ever sees a job number; which request and page the
job belongs to stays in our database.
"""
from __future__ import annotations

import io
import re
from typing import Iterable, Optional
from urllib.parse import urlparse

PAD = 24                 # px of context around the CAPTCHA
MAX_SIDE = 900           # crops larger than this are scaled down


def member_secrets(member) -> list:
    """Every saved detail (and its common spellings) that must never leave in an image or URL."""
    from .combinations import _get_values
    out = set()
    names = _get_values(member, "name", 50) + ([member.full_name] if getattr(member, "full_name", None) else [])
    for n in names:
        for part in re.split(r"\s+", n or ""):
            if len(part) >= 3:
                out.add(part)
        if n:
            out.add(n)
    for kind in ("email", "address"):
        for v in _get_values(member, kind, 50):
            out.add(v)
            if kind == "address":
                street = v.split(",")[0].strip()
                if len(street) >= 5:
                    out.add(street)
    for v in _get_values(member, "phone", 50):
        d = re.sub(r"\D", "", v)
        if len(d) >= 7:
            out.update({d[-10:], d[-7:], d[-4:] if len(d) >= 10 else d})
            if len(d) >= 10:
                d10 = d[-10:]
                out.update({f"{d10[:3]}-{d10[3:6]}-{d10[6:]}", f"({d10[:3]}) {d10[3:6]}-{d10[6:]}",
                            f"{d10[:3]}.{d10[3:6]}.{d10[6:]}"})
    if getattr(member, "formal_name", None):
        out.add(member.formal_name)
    dob = getattr(member, "dob", None)
    if dob:
        out.add(str(dob))
    return sorted((s for s in out if s and len(s) >= 3), key=len, reverse=True)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def contains_secret(text: str, secrets: Iterable[str]) -> bool:
    t = _norm(text)
    return bool(t) and any(_norm(s) and _norm(s) in t for s in secrets)


def safe_page_url(url: str, secrets: Iterable[str] = ()) -> str:
    """scheme://host/path with no query or fragment; just the origin if the path holds a saved detail."""
    try:
        p = urlparse(url or "")
    except Exception:
        return ""
    if p.scheme not in ("http", "https") or not p.hostname:
        return ""
    origin = f"{p.scheme}://{p.hostname}" + (f":{p.port}" if p.port else "")
    path = p.path or "/"
    if contains_secret(path.replace("-", " ").replace("_", " ").replace("/", " "), secrets) \
            or re.search(r"\d{4,}", path):
        return origin + "/"
    return origin + path


def redact_image(png: bytes, boxes: list, crop: Optional[tuple] = None) -> bytes:
    """
    Crop (left, top, right, bottom), black out each box (page coordinates),
    and return a freshly encoded PNG with no metadata.
    """
    from PIL import Image, ImageDraw
    src = Image.open(io.BytesIO(png)).convert("RGB")
    ox = oy = 0
    if crop:
        l, t, r, b = (max(0, int(crop[0])), max(0, int(crop[1])),
                      min(src.width, int(crop[2])), min(src.height, int(crop[3])))
        if r > l and b > t:
            src = src.crop((l, t, r, b))
            ox, oy = l, t
    draw = ImageDraw.Draw(src)
    for (x, y, w, h) in boxes:
        x0, y0 = int(x - ox) - 3, int(y - oy) - 3
        draw.rectangle([x0, y0, x0 + int(w) + 6, y0 + int(h) + 6], fill=(0, 0, 0))
    if max(src.size) > MAX_SIDE:
        f = MAX_SIDE / max(src.size)
        src = src.resize((max(1, int(src.width * f)), max(1, int(src.height * f))))
    # A brand-new image from raw pixels: nothing from the original file
    # (layers, text chunks, EXIF) comes along.
    clean = Image.frombytes("RGB", src.size, src.tobytes())
    out = io.BytesIO()
    clean.save(out, format="PNG", optimize=True)
    return out.getvalue()


# JavaScript run in the page: bounding boxes (page coordinates) of the CAPTCHA
# element, every form control, and every text node, so Python can decide what
# to black out. Nothing leaves the browser except boxes and the visible text.
_COLLECT_JS = """
(sel) => {
  const r = el => { const b = el.getBoundingClientRect();
    return [b.left + window.scrollX, b.top + window.scrollY, b.width, b.height]; };
  let target = null;
  try { target = sel ? document.querySelector(sel) : null; } catch (e) {}
  if (!target) target = document.querySelector("iframe[src*='recaptcha'], iframe[src*='hcaptcha'], .g-recaptcha, .h-captcha, .cf-turnstile, img[src*='captcha' i], img[alt*='captcha' i]");
  const controls = [...document.querySelectorAll('input, textarea, select, [contenteditable=true]')]
    .filter(e => e.offsetParent !== null && (e.type || '') !== 'hidden').map(r);
  const texts = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const n = walker.currentNode; const s = (n.textContent || '').trim();
    if (!s || s.length > 300 || !n.parentElement || n.parentElement.offsetParent === null) continue;
    const range = document.createRange(); range.selectNodeContents(n);
    const b = range.getBoundingClientRect();
    if (b.width && b.height) texts.push({t: s, b: [b.left + window.scrollX, b.top + window.scrollY, b.width, b.height]});
  }
  return {target: target ? r(target) : null, controls, texts,
          viewport: [window.scrollX, window.scrollY, window.innerWidth, window.innerHeight]};
}
"""


async def capture(page, selector: str, secrets: Iterable[str]) -> dict:
    """
    {"image": redacted PNG of just the CAPTCHA (or b"" if it can't be found),
     "boxes": how many areas were blacked out}
    """
    secrets = list(secrets)
    try:
        info = await page.evaluate(_COLLECT_JS, selector or "")
    except Exception:
        return {"image": b"", "boxes": 0}
    t = info.get("target")
    if not t or t[2] < 10 or t[3] < 10:
        return {"image": b"", "boxes": 0}
    crop = (t[0] - PAD, t[1] - PAD, t[0] + t[2] + PAD, t[1] + t[3] + PAD)
    boxes = [tuple(b) for b in info.get("controls", []) if _overlaps(b, crop)]
    boxes += [tuple(x["b"]) for x in info.get("texts", []) if _overlaps(x["b"], crop) and contains_secret(x["t"], secrets)]
    try:
        png = await page.screenshot(full_page=True)
    except Exception:
        return {"image": b"", "boxes": 0}
    return {"image": redact_image(png, boxes, crop), "boxes": len(boxes)}


def _overlaps(b, crop) -> bool:
    x, y, w, h = b
    return x < crop[2] and x + w > crop[0] and y < crop[3] and y + h > crop[1]
