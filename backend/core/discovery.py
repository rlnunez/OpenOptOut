"""
Discovery bot — two-pass strategy using the combination matrix.

Pass 1: name × address combinations → find which brokers have listings
Pass 2: triggered by opt-out engine using full matrix on confirmed brokers
"""

import asyncio, logging, re, time, uuid
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus, urlparse

from playwright.async_api import async_playwright, BrowserContext, Page, TimeoutError as PWTimeout

from ..models.database import (
    SessionLocal, FamilyMember, Broker, BrokerScript,
    DiscoveryResult, AutomationLog, RemovalRequest, RequestStatus
)
from .combinations import (
    build_discovery_combos, build_property_discovery_combos, IdentityCombo
)

log = logging.getLogger(__name__)
SCREENSHOTS_DIR = "/data/screenshots"
NAV_TIMEOUT     = 20_000


# ── Browser ───────────────────────────────────────────────────────────────────

async def _launch_browser(playwright):
    """
    Launch Firefox with a randomized user agent + matching viewport.
    UA rotation is one layer of bot-detection evasion — see core/user_agents.py.
    """
    from .user_agents import get_random_agent, get_custom_uas_from_settings, rotation_enabled

    browser = await playwright.firefox.launch(
        headless=True,
        firefox_user_prefs={"dom.webdriver.enabled": False},
    )

    from .proxy import get_proxy_for_context
    proxy = get_proxy_for_context()

    ctx_args = {"locale": "en-US"}
    if proxy:
        ctx_args["proxy"] = proxy

    if rotation_enabled():
        custom = get_custom_uas_from_settings()
        agent  = get_random_agent(custom)
        ctx_args["user_agent"] = agent["ua"]
        ctx_args["viewport"]   = agent["viewport"]
        context = await browser.new_context(**ctx_args)
        log.debug(f"Browser context UA: {agent['platform']} — {agent['ua'][:50]}...")
    else:
        ctx_args["user_agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0"
        ctx_args["viewport"]   = {"width": 1280, "height": 800}
        context = await browser.new_context(**ctx_args)
    return browser, context


async def _screenshot(page: Page, name: str) -> Optional[str]:
    import os; os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    ts   = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = f"{SCREENSHOTS_DIR}/{name}_{ts}.png"
    try:
        await page.screenshot(path=path, full_page=True)
        return path
    except Exception:
        return None


def _get_primary(member: FamilyMember, kind: str) -> Optional[str]:
    primaries = [i for i in member.identities if i.kind == kind and i.is_primary]
    if primaries: return primaries[0].value
    all_k = [i for i in member.identities if i.kind == kind]
    return all_k[0].value if all_k else None


def _city_state(address: Optional[str]) -> tuple[str, str]:
    if not address: return "", ""
    m = re.search(r',\s*([^,]+),?\s+([A-Z]{2})\b', address)
    if m: return m.group(1).strip(), m.group(2).strip()
    parts = [p.strip() for p in address.split(',')]
    if len(parts) >= 2:
        return parts[-2], parts[-1].split()[0] if parts[-1].split() else ""
    return "", ""


# ── Google search ─────────────────────────────────────────────────────────────

async def _google_search(page: Page, combo: IdentityCombo, broker_domain: str) -> list[dict]:
    query = f'site:{broker_domain} "{combo.name}"'
    if combo.city:  query += f' "{combo.city}"'
    if combo.state: query += f' {combo.state}'

    results = []
    try:
        await page.goto(
            f"https://www.google.com/search?q={quote_plus(query)}",
            timeout=NAV_TIMEOUT
        )
        await page.wait_for_timeout(1500)

        links = await page.query_selector_all("a[href]")
        seen  = set()
        for link in links:
            href = await link.get_attribute("href") or ""
            if broker_domain in href and "google.com" not in href and href not in seen:
                seen.add(href)
                try:
                    parent  = await link.evaluate_handle(
                        "el => el.closest('.g, .tF2Cxc, [data-sokoban-container]')"
                    )
                    snippet = await parent.as_element().inner_text() if parent else ""
                except Exception:
                    snippet = ""
                results.append({"url": href, "snippet": snippet[:300]})
        return results[:5]

    except PWTimeout:
        return []
    except Exception as e:
        log.debug(f"Google search error: {e}")
        return []


# ── Direct broker search ──────────────────────────────────────────────────────

async def _direct_search(
    page: Page,
    combo: IdentityCombo,
    broker: Broker,
    script: Optional[BrokerScript],
) -> list[dict]:
    search_url = (script.search_url if script and script.search_url else broker.opt_out_url)
    if not search_url:
        return []

    domain  = urlparse(search_url).netloc
    results = []

    try:
        await page.goto(search_url, timeout=NAV_TIMEOUT)
        await page.wait_for_timeout(1500)

        name_sel = (script.name_selector if script else None) or \
            "input[name='name'], input[placeholder*='name' i], input[id*='name' i]"

        name_input = await page.query_selector(name_sel)
        if not name_input:
            for sel in ["input[type='search']", "input[type='text']"]:
                name_input = await page.query_selector(sel)
                if name_input: break

        if name_input:
            await name_input.fill(combo.name)

            if combo.city:
                for sel in ["input[name='city']", "input[placeholder*='city' i]"]:
                    el = await page.query_selector(sel)
                    if el: await el.fill(combo.city); break

            if combo.state:
                for sel in ["select[name='state']", "input[name='state']"]:
                    el = await page.query_selector(sel)
                    if el:
                        try:    await el.select_option(value=combo.state)
                        except: await el.fill(combo.state)
                        break

            submit_sel = (script.submit_selector if script else None) or \
                "button[type='submit'], input[type='submit'], button:has-text('Search')"
            submit = await page.query_selector(submit_sel)
            if submit:
                await submit.click()
                await page.wait_for_timeout(2500)

            links = await page.query_selector_all("a[href]")
            name_parts = combo.name.lower().split()
            for link in links:
                href = await link.get_attribute("href") or ""
                if domain in href or href.startswith("/"):
                    full = href if href.startswith("http") else f"https://{domain}{href}"
                    text = (await link.inner_text()).lower()
                    if any(p in text for p in name_parts):
                        results.append({"url": full, "snippet": text[:200]})

        return results[:3]

    except PWTimeout:
        return []
    except Exception as e:
        log.debug(f"Direct search error on {broker.name}: {e}")
        return []


# ── One broker × one combo ────────────────────────────────────────────────────

async def _discover_combo(
    combo: IdentityCombo,
    broker: Broker,
    script: Optional[BrokerScript],
    context: BrowserContext,
) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    Run Google + direct search for one (combo, broker) pair.
    Returns (found, listing_url, source, snippet).
    """
    page  = await context.new_page()
    found = False
    url = source = snippet = None

    broker_domain = ""
    if broker.opt_out_url:
        broker_domain = urlparse(broker.opt_out_url).netloc.lstrip("www.")
    if not broker_domain and "." in broker.name:
        broker_domain = broker.name.lstrip("www.")

    try:
        if broker_domain:
            g_results = await _google_search(page, combo, broker_domain)
            if g_results:
                found   = True
                url     = g_results[0]["url"]
                snippet = g_results[0]["snippet"]
                source  = "google"

        if not found:
            d_results = await _direct_search(page, combo, broker, script)
            if d_results:
                found   = True
                url     = d_results[0]["url"]
                snippet = d_results[0]["snippet"]
                source  = "direct"
    finally:
        await page.close()

    return found, url, source, snippet


# ── Full discovery for one member ─────────────────────────────────────────────

async def run_discovery_for_member(member_id: int) -> dict:
    """
    Pass 1: run all discovery combos (name × address) across all brokers.
    Creates a DiscoveryResult per (member, broker, combo).
    Creates a pending RemovalRequest for each broker where any combo finds a listing.
    """
    db = SessionLocal()
    found_brokers = set()
    total_found = total_combos = 0
    errors = []

    try:
        member  = db.query(FamilyMember).filter(FamilyMember.id == member_id).first()
        if not member:
            return {"error": "Member not found"}

        combos  = build_discovery_combos(member)
        # Exclude test brokers — they exist only for the explicit email test send.
        brokers = db.query(Broker).filter(Broker.is_test.isnot(True)).all()
        scripts = {s.broker_id: s for s in db.query(BrokerScript).all()}

        log.info(f"Discovery for {member.full_name}: {len(combos)} combos × {len(brokers)} brokers")

        async with async_playwright() as p:
            browser, context = await _launch_browser(p)
            try:
                for broker in brokers:
                    broker_found = False
                    broker_url   = None

                    # Property brokers use formal name + deed addresses
                    if broker.is_property_broker:
                        broker_combos = build_property_discovery_combos(member)
                    else:
                        broker_combos = combos

                    for combo in broker_combos:
                        total_combos += 1
                        try:
                            found, url, source, snippet = await _discover_combo(
                                combo, broker, scripts.get(broker.id), context
                            )

                            # Store every combo result
                            dr = DiscoveryResult(
                                member_id=member_id,
                                broker_id=broker.id,
                                found=found,
                                listing_url=url,
                                source=source,
                                snippet=snippet,
                                scanned_at=datetime.utcnow(),
                            )
                            # Tag combo details in snippet for traceability
                            if dr.snippet is None:
                                dr.snippet = combo.label()
                            db.add(dr)

                            if found:
                                total_found += 1
                                broker_found = True
                                broker_url   = url
                                # Once we find one combo hit on this broker,
                                # we can stop discovery for it (opt-out will use full matrix)
                                db.commit()
                                break

                        except Exception as e:
                            errors.append(f"{broker.name} / {combo.label()}: {e}")

                    db.commit()

                    if broker_found:
                        found_brokers.add(broker.id)
                        # Create pending RemovalRequest if none exists
                        existing = db.query(RemovalRequest).filter(
                            RemovalRequest.member_id == member_id,
                            RemovalRequest.broker_id == broker.id,
                            RemovalRequest.status == RequestStatus.pending,
                        ).first()
                        if not existing:
                            db.add(RemovalRequest(
                                member_id=member_id,
                                broker_id=broker.id,
                                request_key=str(uuid.uuid4()),
                                listing_url=broker_url,
                                status=RequestStatus.pending,
                            ))
                            db.commit()

                    # Polite inter-broker delay
                    await asyncio.sleep(1.0)

            finally:
                await browser.close()

    except Exception as e:
        errors.append(str(e))
        log.error(f"Discovery run error: {e}")
    finally:
        db.close()

    return {
        "member_id":    member_id,
        "combos_run":   total_combos,
        "combos_found": total_found,
        "brokers_found": len(found_brokers),
        "errors":       errors,
    }
