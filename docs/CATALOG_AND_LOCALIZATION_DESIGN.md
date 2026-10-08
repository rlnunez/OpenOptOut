# Design Document: Core Catalog Marketplace & Plugin Localization Architecture

**Status:** Approved / In Roadmap  
**Target Milestone:** v0.9.0 / v1.0.0  
**Related Roadmap Items:** [Item 8: Add-on Distribution & Marketplace](file:///Users/robertnunez/Documents/GitHub/Privacy%20Shield/docs/ROADMAP.md#L210), [Item 11: First-Run Setup Wizard](file:///Users/robertnunez/Documents/GitHub/Privacy%20Shield/docs/ROADMAP.md#L271), [Item 17: Internationalization & Localization](file:///Users/robertnunez/Documents/GitHub/Privacy%20Shield/docs/ROADMAP.md#L360)

---

## Executive Summary

This design document establishes the architecture for three core capability gaps in OpenOptOut:
1. **Core-Integrated Catalog Marketplace Client:** A remote catalog consumer inside OpenOptOut core that discovers, caches, inspects, and installs official community broker specifications, solver plugins, and language packs without requiring manual zip downloads.
2. **Catalog Tiering & Type Prioritization:** A declarative ranking and tiering schema embedded directly within the catalog's `index.json`, providing curated bundles during onboarding and sorting within the administrative console.
3. **Universal Plugin Localization Standard & Legal Jurisdiction Decoupling:** A standardized multi-tiered translation lookup order for all plugins (`locales/<code>.json`), cross-plugin translation via language packs, and a strict decoupling between **Patron Interface Language** (for UI display) and **Broker Legal Request Language** (for enforceable privacy compliance letters).

---

## Section 1: Catalog Client Inside Core (Marketplace)

### 1.1 Problem Statement
Currently, OpenOptOut only supports installing add-ons via manual local zip upload (`POST /api/plugins/upload`) or scanning unregistered packages already copied onto the server filesystem (`POST /api/plugins/install`). This creates friction for self-hosters and prevents automated updates to broker specs as commercial data broker web layouts drift.

### 1.2 Remote Catalog Architecture
The catalog client runs strictly on the control plane inside OpenOptOut core (`backend/plugins/catalog.py`). It communicates over HTTPS with the official OpenOptOut Add-on Repository index.

```
┌────────────────────────────────────────────────────────┐
│ OpenOptOut Community Catalog (GitHub Releases / CDN)   │
│   ├── index.json (manifest of available add-ons)       │
│   └── packages/<plugin_id>-<version>.zip               │
└──────────────────────────┬─────────────────────────────┘
                           │ HTTPS GET (ETag / TTL Cache)
                           ▼
┌────────────────────────────────────────────────────────┐
│ OpenOptOut Core (backend/plugins/catalog.py)           │
│   ├── CatalogCache (data/catalog_cache.json, TTL 4h)   │
│   ├── Endpoints:                                       │
│   │     GET  /api/plugins/catalog                      │
│   │     POST /api/plugins/catalog/install              │
│   │     POST /api/plugins/catalog/update               │
│   │     POST /api/plugins/catalog/refresh              │
│   └── Existing Safety Pipeline:                        │
│         ├── Safe Zip Boundary Checks (path traversal)  │
│         ├── Static Code Inspector                      │
│         ├── Permission Review & Grants                 │
│         └── SHA-256 Checksum Verification              │
└────────────────────────────────────────────────────────┘
```

### 1.3 Catalog Index Schema (`index.json`)
The catalog repository serves a canonical `index.json` structured as follows:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-10-07T12:00:00Z",
  "catalog_url": "https://catalog.openoptout.org",
  "plugins": [
    {
      "id": "broker-staterecords",
      "type": "brokers",
      "name": "StateRecords Opt-Out",
      "version": "1.2.0",
      "description": "Automated declarative removal for StateRecords.org",
      "author": "OpenOptOut Community",
      "license": "MIT",
      "tier": 1,
      "rank": 10,
      "recommended_bundle": true,
      "archive_url": "https://catalog.openoptout.org/packages/broker-staterecords-1.2.0.zip",
      "sha256": "8f4e2...",
      "min_core_version": "0.8.0",
      "permissions_requested": ["read_pii"],
      "default_locale": "en",
      "supported_locales": ["en", "es", "vi"]
    }
  ]
}
```

### 1.4 Cache & ETag Mechanics
- **Location:** Cached in local database or `/data/catalog_cache.json`.
- **TTL:** 4 hours by default, with `If-None-Match` (ETag) and `If-Modified-Since` headers sent on background refresh queries.
- **Manual Trigger:** Super admins can trigger immediate cache invalidation via `POST /api/plugins/catalog/refresh`.
- **Air-Gapped / Offline Fallback:** If internet egress is disabled or fails, the catalog gracefully serves the last cached index or an embedded fallback bundle.

### 1.5 Secure Catalog Install Pipeline
Catalog installation reuses the existing, battle-tested plugin security pipeline:
1. **Fetch & Verify Checksum:** Download archive to an ephemeral temp directory and verify the SHA-256 digest against `index.json`.
2. **Extraction & Archive Containment:** Run through `_extracted_bundle()` ensuring path containment, no symlinks, and quota ceilings.
3. **Static Inspection:** Pass code files to `code_inspector.py` to identify dangerous constructs.
4. **Registration:** Install into `<plugins_root>/<type>/<id>/` with status `stopped` and `enabled = False`.
5. **Admin Approval Gate:** Like uploaded plugins, catalog plugins remain disabled until an administrator explicitly reviews permissions and enables them. Updates require explicit administrative confirmation until cryptographic binary signing (Roadmap Item 8 Phase 2) is active.

---

## Section 2: Priority & Tiering Within Each Plugin Type

### 2.1 Catalog Priority Model
To avoid hardcoding priority ordering into OpenOptOut releases, priority and recommendations are declared directly in `index.json`:
- **`tier`:**
  - `tier 1` (**Recommended / Essential**): High-reputation, thoroughly tested plugins that form the foundation of consumer data privacy. Installed by default or pre-selected in setup bundles.
  - `tier 2` (**Available / Verified**): Stable plugins for regional brokers, secondary solvers, or supplemental language packs.
  - `tier 3` (**Experimental / Community**): Newly contributed or beta plugins.
- **`rank`:** Integer sorting key within the same plugin `type` (lower number = higher priority).

### 2.2 Language Pack Ranking Strategy
Languages are prioritized according to two criteria:
1. **US Household Primary Languages:** Given that the vast majority of consumer data brokers target US residents, languages spoken by substantial US populations must be readily accessible.
2. **Jurisdictional Privacy Protection Laws:** Regions with established statutory rights to data erasure (EU/UK GDPR, Brazil LGPD, California CCPA).

| Tier | Languages | Primary Justification |
| :--- | :--- | :--- |
| **Tier 1** | **English (`en`)**, **Spanish (`es`)**, **French (`fr`)**, **Arabic (`ar`)** | Built-in out-of-the-box core languages. Covers core US demographics and primary RTL script layout verification. |
| **Tier 2** | **Chinese Simplified (`zh`)**, **Vietnamese (`vi`)**, **Tagalog (`tl`)**, **Korean (`ko`)**, **Portuguese (`pt-BR`)**, **German (`de`)** | Top non-English US home languages + primary legal rights regimes (Brazil LGPD, European GDPR). |
| **Tier 3** | **Hebrew (`he`)**, **Hindi (`hi`)**, **Russian (`ru`)**, **Italian (`it`)**, **Japanese (`ja`)**, **Persian (`fa`)**, **Urdu (`ur`)** | Secondary RTL scripts, international community languages, and niche regional locales. |

---

## Section 3: Universal Plugin Localization Standard

### 3.1 Plugin Localization Packaging
Every plugin can supply its own localized text strings without requiring core modifications.
- **Directory Layout:**
  ```
  plugins/<type>/<plugin_id>/
  ├── manifest.json
  ├── spec.json
  └── locales/
      ├── en.json
      ├── es.json
      └── vi.json
  ```
- **Manifest Declaration:**
  ```json
  {
    "id": "broker-staterecords",
    "default_locale": "en",
    "locales": ["en", "es", "vi"]
  }
  ```

### 3.2 Keyed Text Strings
All user-facing text in plugins (display names, descriptions, checklist instructions, error banners) should be referenced by key or structured dictionary:
```json
{
  "broker.staterecords.name": "StateRecords",
  "broker.staterecords.desc": "Opt-out automated removal from StateRecords database",
  "broker.staterecords.step.search": "Searching records for full name and state",
  "broker.staterecords.step.confirm": "Submitting removal confirmation request"
}
```

### 3.3 Five-Tier Universal Translation Lookup Order
All UI strings across core and plugins resolve using a unified hierarchical fallback chain:

```
┌────────────────────────────────────────────────────────┐
│ 1. Admin Custom Overrides                              │ (Settings store custom string replacements)
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ 2. Language Pack Plugin Messages                       │ (<plugins_root>/languages/<id>/messages.json)
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ 3. Plugin's Own Matching Locale File                   │ (<plugin_dir>/locales/<lang>.json)
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ 4. Plugin's Declared Default Locale                    │ (<plugin_dir>/locales/<default_locale>.json)
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ 5. System Fallback: English Default                    │ (Master dictionary / manifest default)
└────────────────────────────────────────────────────────┘
```

### 3.4 Cross-Plugin Translations via Language Packs
Translators should not be required to fork or modify individual broker or solver plugins to localize them. Language packs can supply cross-plugin string tables:
```
plugins/languages/lang-vi/
├── manifest.json
├── messages.json              # Translates core UI
└── plugins/
    └── broker-staterecords.json # Translates StateRecords checklist & instructions
```
When `get_translations_for_locale("vi")` is invoked, the engine automatically merges strings from `plugins/languages/lang-vi/plugins/<plugin_id>.json` into the plugin's translation dictionary.

---

## Section 4: UI Interface Language vs. Broker Legal Request Language

### 4.1 The Jurisdictional Distinction
A critical architectural boundary exists between **Interface Language** and **Legal Request Language**:
- **Interface Language:** The language selected by the patron or system administrator to navigate the dashboard, complete wizards, and view removal statuses.
- **Legal Request Language:** The legal correspondence dispatched to data broker privacy teams (via email or form submission) demanding compliance with statutory privacy laws (e.g., CCPA, GDPR, LGPD).

> [!IMPORTANT]
> A Vietnamese-speaking or Spanish-speaking user residing in California still requires opt-out emails sent to US brokers to be written in **English**, because US corporate privacy and legal compliance departments require English notices under CCPA/CPRA. Sending a Vietnamese opt-out letter to a US broker invites rejection, confusion, or non-compliance.
> Conversely, an opt-out directed to a French broker under the EU GDPR/CNIL must be formatted in **French**, regardless of whether the user’s UI is set to English.

### 4.2 Data Model & Specification Updates
1. **`BrokerSpec` Schema Update:**
   Add `jurisdiction` and `legal_language` fields to declarative specifications:
   ```json
   {
     "id": "staterecords",
     "jurisdiction": "US",
     "legal_language": "en",
     "email_templates": {
       "en": {
         "subject": "Data removal request — {full_name} [{request_key}]",
         "body": "To the Privacy / Data Protection team at {parent_name}..."
       }
     }
   }
   ```
2. **Decoupling in `compose_optout_email`:**
   In [`backend/core/optout_email_template.py`](file:///Users/robertnunez/Documents/GitHub/Privacy%20Shield/backend/core/optout_email_template.py), `locale` will no longer represent the patron's UI language. It will represent the broker's mandatory `legal_language` (defaulting to `"en"` for US brokers).
   The previous fallback disclaimer `"[Note: a localized (es) template is not yet available; this request is in English.]"` is removed for US brokers, as English is the legally authoritative language for US statutory requests.

---

## Section 5: Setup Wizard Flow Enhancement

### 5.1 Updated 7-Step Setup Wizard
The setup wizard is expanded from 5 steps to 7 sequential steps:

```
[1. Language] ➔ [2. Database] ➔ [3. Email] ➔ [4. Recommended Protections] ➔ [5. Deployment] ➔ [6. Branding] ➔ [7. Summary]
```

1. **Step 1: Language Selection (New):**
   - Auto-detects browser locale (`navigator.language`).
   - Displays a 1-click switcher between Tier 1 languages (English, Spanish, French, Arabic).
   - Instant UI preview with dynamic RTL layout switching if Arabic or Hebrew is selected.
2. **Step 2: Database:**
   - SQLite (default) vs. PostgreSQL (distributed fleet).
3. **Step 3: Email Transport:**
   - OAuth 2.0 (Google/Microsoft), SMTP/IMAP, or local relay.
4. **Step 4: Recommended Protections Bundle (New):**
   - Automatically queries the catalog client for `tier == 1` and `recommended_bundle == true` add-ons.
   - Pre-selects foundational brokers (e.g. StateRecords, CourtRecords, Whitepages, top email-first brokers).
   - "Install Recommended Protections" button allows the operator to provision the protection suite with a single click.
5. **Step 5: Deployment:**
   - HTTPS / Reverse Proxy configuration (Caddy, Certbot, or external).
6. **Step 6: Branding:**
   - Institutional portal name, logo, and theme.
7. **Step 7: Summary & Verification:**
   - Comprehensive checklist of configured components with completion status.

---

## Section 6: Administrative Console "Browse" Catalog Tab

### 6.1 UI Design (`frontend/src/pages/Plugins.jsx`)
The Plugins administrative interface will feature a primary tab switcher:
- **Tab 1: Installed Plugins (Existing):** Manage active plugins, view sandbox status, inspect permissions, review audit logs.
- **Tab 2: Browse Catalog (New):**
  - **Filter by Type:** All, Brokers, Captcha Solvers, Email Transports, Languages, Themes.
  - **Sorting:** Tier 1 (Recommended) pinned to top, followed by catalog rank.
  - **Card Metadata:** Plugin name, author, version, description, requested permissions chip list, and verified badge.
  - **Action Button:** "Install" (fetches package and opens permission grant modal).
  - **Update Badges:** When an installed plugin has a higher version in `index.json`, display an "Update Available" badge with a 1-click update trigger.

---

## Section 7: Implementation Roadmap & Milestones

1. **Phase 1: Catalog Client & Schema (Backend):**
   - Implement `backend/plugins/catalog.py` with caching, SHA-256 checks, and install/update endpoints.
   - Add catalog endpoints to `backend/routers/plugins.py`.
2. **Phase 2: Universal Localization Standard:**
   - Extend `backend/core/i18n.py` to support plugin `locales/` directory scanning and cross-plugin language pack merging.
   - Update `BrokerSpec` and `optout_email_template.py` to decouple legal jurisdiction language from UI language.
3. **Phase 3: Setup Wizard & Admin UI Integration:**
   - Expand `SetupWizard.jsx` and `wizard.py` to incorporate Step 1 (Language) and Step 4 (Recommended Protections).
   - Add the "Browse Catalog" tab to `frontend/src/pages/Plugins.jsx`.
