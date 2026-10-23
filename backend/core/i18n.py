"""
Internationalization (i18n) and Right-to-Left (RTL) Engine (Roadmap Item 17).

Provides:
  - Master English dictionary with categorized keys and screen locations ("where it appears")
  - English in core; every other language as a language-pack plugin (built-in ones in
    plugins/bundled/languages/, community ones in <plugins_root>/languages/)
  - In-system translation replacement interface allowing super admins/managers to override wording
  - Discovery of community language pack add-ons (<plugins_root>/languages/<id>/)
  - Dynamic RTL detection and metadata
  - User preferred language persistence
"""

import json
import logging
import os
import re
from typing import Dict, List, Optional, Any

try:
    from . import settings_store
except (ImportError, ValueError):
    from core import settings_store

try:
    from ..plugins.language_packs import is_safe_translation_string
except (ImportError, ValueError):
    try:
        from plugins.language_packs import is_safe_translation_string
    except (ImportError, ValueError):
        def is_safe_translation_string(k: str, v: str):  # type: ignore
            return True, None

log = logging.getLogger(__name__)

# Standard RTL language codes (ISO 639-1)
RTL_LANGUAGES = {"ar", "he", "fa", "ur", "yi", "ps", "sd", "ckb", "ug"}

# Well-known languages catalog
KNOWN_LANGUAGES = {
    "en": {"name": "English", "native_name": "English", "is_rtl": False},
    "es": {"name": "Spanish", "native_name": "Español", "is_rtl": False},
    "ar": {"name": "Arabic", "native_name": "العربية", "is_rtl": True},
    "fr": {"name": "French", "native_name": "Français", "is_rtl": False},
    "de": {"name": "German", "native_name": "Deutsch", "is_rtl": False},
    "he": {"name": "Hebrew", "native_name": "עברית", "is_rtl": True},
    "zh": {"name": "Chinese (Simplified)", "native_name": "简体中文", "is_rtl": False},
    "vi": {"name": "Vietnamese", "native_name": "Tiếng Việt", "is_rtl": False},
    "fa": {"name": "Persian", "native_name": "فارسی", "is_rtl": True},
    "ur": {"name": "Urdu", "native_name": "اردو", "is_rtl": True},
    "pl": {"name": "Polish", "native_name": "Polski", "is_rtl": False},
    "uk": {"name": "Ukrainian", "native_name": "Українська", "is_rtl": False},
    "sw": {"name": "Swahili", "native_name": "Kiswahili", "is_rtl": False},
    "id": {"name": "Indonesian", "native_name": "Bahasa Indonesia", "is_rtl": False},
    "pt": {"name": "Portuguese", "native_name": "Português", "is_rtl": False},
    "it": {"name": "Italian", "native_name": "Italiano", "is_rtl": False},
    "ja": {"name": "Japanese", "native_name": "日本語", "is_rtl": False},
    "ko": {"name": "Korean", "native_name": "한국어", "is_rtl": False},
    "ru": {"name": "Russian", "native_name": "Русский", "is_rtl": False},
    "tl": {"name": "Tagalog", "native_name": "Filipino", "is_rtl": False},
    "hi": {"name": "Hindi", "native_name": "हिन्दी", "is_rtl": False},
    "pirate": {"name": "Pirate", "native_name": "Pirate (Ahoy!)", "is_rtl": False},
}

# Master English Dictionary with categorized UI screen locations
MASTER_DICTIONARY: List[Dict[str, str]] = [
    # ── Navigation & Shell ──────────────────────────────────────────
    {"key": "nav.dashboard", "default_text": "Dashboard", "location": "Navigation / Sidebar", "description": "Sidebar link to main metrics dashboard"},
    {"key": "nav.requests", "default_text": "Removal requests", "location": "Navigation / Sidebar", "description": "Sidebar link to broker removal requests table"},
    {"key": "nav.vault", "default_text": "Your details", "location": "Navigation / Sidebar", "description": "Sidebar link to manage personal data identities"},
    {"key": "nav.family", "default_text": "Family members", "location": "Navigation / Sidebar", "description": "Sidebar link to manage protected family profiles"},
    {"key": "nav.brokers", "default_text": "Broker sites", "location": "Navigation / Sidebar", "description": "Sidebar link to broker directory and status"},
    {"key": "nav.settings", "default_text": "Settings", "location": "Navigation / Sidebar", "description": "Sidebar link to platform configuration"},
    {"key": "nav.translations", "default_text": "Translations", "location": "Navigation / Sidebar", "description": "Admin link to in-system translation editor"},
    {"key": "nav.plugins", "default_text": "Plugins", "location": "Navigation / Sidebar", "description": "Sidebar link to plugins and add-on catalog"},
    {"key": "nav.logout", "default_text": "Sign out", "location": "Navigation / User Menu", "description": "Button to log out of current session"},
    {"key": "nav.welcome_tour", "default_text": "Welcome Tour", "location": "Navigation / User Menu", "description": "Button to re-open the guided onboarding walkthrough"},
    {"key": "nav.language", "default_text": "Language", "location": "Header / Language Picker", "description": "Label for active language switcher"},

    # ── Common UI Controls ──────────────────────────────────────────
    {"key": "common.save", "default_text": "Save", "location": "Global / Form Buttons", "description": "Save changes button"},
    {"key": "common.cancel", "default_text": "Cancel", "location": "Global / Form Buttons", "description": "Cancel current dialog or form"},
    {"key": "common.delete", "default_text": "Delete", "location": "Global / Form Buttons", "description": "Delete confirmation button"},
    {"key": "common.edit", "default_text": "Edit", "location": "Global / Table Actions", "description": "Edit row action"},
    {"key": "common.loading", "default_text": "Loading...", "location": "Global / States", "description": "Asynchronous loading indicator"},
    {"key": "common.success", "default_text": "Success", "location": "Global / Notifications", "description": "Success banner title"},
    {"key": "common.error", "default_text": "Problem", "location": "Global / Notifications", "description": "Error banner title"},
    {"key": "common.next", "default_text": "Next", "location": "Global / Wizards", "description": "Next step button"},
    {"key": "common.back", "default_text": "Back", "location": "Global / Wizards", "description": "Previous step button"},
    {"key": "common.finish", "default_text": "Finish", "location": "Global / Wizards", "description": "Complete wizard button"},
    {"key": "common.search", "default_text": "Search...", "location": "Global / Search Inputs", "description": "Placeholder for search inputs"},
    {"key": "common.enabled", "default_text": "Enabled", "location": "Global / Badges", "description": "Enabled status badge"},
    {"key": "common.disabled", "default_text": "Disabled", "location": "Global / Badges", "description": "Disabled status badge"},

    # ── Dashboard Screen ───────────────────────────────────────────
    {"key": "dashboard.title", "default_text": "Privacy Protection Overview", "location": "Dashboard / Header", "description": "Main heading on Dashboard"},
    {"key": "dashboard.subtitle", "default_text": "Monitoring and purging personal records across commercial data brokers.", "location": "Dashboard / Header", "description": "Subtitle below Dashboard heading"},
    {"key": "dashboard.total_brokers", "default_text": "Tracked Brokers", "location": "Dashboard / Metrics Cards", "description": "Count of known data brokers"},
    {"key": "dashboard.confirmed_removals", "default_text": "Confirmed Removals", "location": "Dashboard / Metrics Cards", "description": "Number of successfully confirmed opt-outs"},
    {"key": "dashboard.pending_requests", "default_text": "In Progress", "location": "Dashboard / Metrics Cards", "description": "Opt-outs currently submitted or awaiting confirmation"},
    {"key": "dashboard.protection_score", "default_text": "Protection Coverage", "location": "Dashboard / Metrics Cards", "description": "Percentage of clean broker records"},
    {"key": "dashboard.start_optout_all", "default_text": "Run Automated Opt-Outs", "location": "Dashboard / Quick Actions", "description": "Trigger automated batch removal run"},

    # ── Identity Vault Screen ──────────────────────────────────────
    {"key": "vault.title", "default_text": "Your details", "location": "Identity Vault / Header", "description": "Page heading for personal data management"},
    {"key": "vault.description", "default_text": "We use these details only to find and remove your listings. They're stored encrypted.", "location": "Identity Vault / Header", "description": "Privacy assurance subtext"},
    {"key": "vault.add_name", "default_text": "Add a name", "location": "Identity Vault / Names", "description": "Button to add alias or previous name"},
    {"key": "vault.add_address", "default_text": "Add Address", "location": "Identity Vault / Addresses", "description": "Button to add current or historical address"},
    {"key": "vault.add_phone", "default_text": "Add Phone Number", "location": "Identity Vault / Phones", "description": "Button to add phone number"},
    {"key": "vault.add_email", "default_text": "Add Email Address", "location": "Identity Vault / Emails", "description": "Button to add email identity"},

    # ── Onboarding / Welcome Tutorial Modal ────────────────────────
    {"key": "tutorial.welcome_title", "default_text": "Welcome to OpenOptOut", "location": "Welcome Tutorial / Step 1", "description": "Main onboarding modal header"},
    {"key": "tutorial.welcome_desc", "default_text": "Let's take a moment to customize your experience and configure your privacy protections.", "location": "Welcome Tutorial / Step 1", "description": "Introduction to user setup walkthrough"},
    {"key": "tutorial.lang_step_title", "default_text": "Choose Your Preferred Language", "location": "Welcome Tutorial / Step 1", "description": "Step 1 title for language selection"},
    {"key": "tutorial.lang_step_desc", "default_text": "Select your language below. The interface, notifications, and layout will adapt immediately.", "location": "Welcome Tutorial / Step 1", "description": "Explanation of language options"},
    {"key": "tutorial.pii_step_title", "default_text": "Protect Your Identity", "location": "Welcome Tutorial / Step 2", "description": "Step 2 title for profile information"},
    {"key": "tutorial.pii_step_desc", "default_text": "Add your name and city so we can find the sites that list you and ask them to remove it.", "location": "Welcome Tutorial / Step 2", "description": "Why PII is collected"},
    {"key": "tutorial.email_step_title", "default_text": "Your removal email", "location": "Welcome Tutorial / Step 3", "description": "Step 3 title for email configuration"},
    {"key": "tutorial.email_step_desc", "default_text": "We send removal requests from an inbox you connect, and read the replies for you.", "location": "Welcome Tutorial / Step 3", "description": "Explanation of email handling"},
    {"key": "tutorial.tour_step_title", "default_text": "Platform Tour & Quick Navigation", "location": "Welcome Tutorial / Step 4", "description": "Step 4 title for UI walkthrough"},
    {"key": "tutorial.tour_step_desc", "default_text": "See what's been removed, manage your family, and check what needs you.", "location": "Welcome Tutorial / Step 4", "description": "Tour summary"},
    {"key": "tutorial.skip", "default_text": "Skip Tutorial", "location": "Welcome Tutorial / Footer", "description": "Button to dismiss the tutorial"},
    {"key": "tutorial.start_protecting", "default_text": "Start Protecting My Data", "location": "Welcome Tutorial / Step 4", "description": "Completion button"},

    # ── Language & Translation Manager Screen ─────────────────────
    {"key": "i18n.manager_title", "default_text": "Internationalization & Translation Manager", "location": "Translation Manager / Header", "description": "Page heading for translation admin"},
    {"key": "i18n.manager_desc", "default_text": "Manage available interface languages, customize terminology, and inspect where wording appears.", "location": "Translation Manager / Header", "description": "Subtitle for translation admin"},
    {"key": "i18n.active_languages", "default_text": "Active Languages", "location": "Translation Manager / Language List", "description": "Section header for enabled languages"},
    {"key": "i18n.add_language", "default_text": "Add Language", "location": "Translation Manager / Language List", "description": "Button to register a new language"},
    {"key": "i18n.filter_by_location", "default_text": "Filter by Screen Location", "location": "Translation Manager / Filters", "description": "Filter dropdown for UI locations"},
    {"key": "i18n.source_english", "default_text": "Source English", "location": "Translation Manager / Editor Table", "description": "Column header for default text"},
    {"key": "i18n.translated_text", "default_text": "Translated Text / Custom Override", "location": "Translation Manager / Editor Table", "description": "Column header for translation input"},
    {"key": "i18n.where_it_appears", "default_text": "Where it Appears", "location": "Translation Manager / Editor Table", "description": "Column header describing location"},
    {"key": "i18n.save_translations", "default_text": "Save Custom Translations", "location": "Translation Manager / Actions", "description": "Button to save translated strings"},
    {"key": "i18n.reset_defaults", "default_text": "Reset to Default", "location": "Translation Manager / Actions", "description": "Reset translation overrides"},

    # ── Patron Demographics & ILS Import ──────────────────────────
    {"key": "ils.import_prompt_title", "default_text": "Import details from your library card?", "location": "Welcome Tutorial & Identity Vault / Banner", "description": "Prompt asking patron whether to import ILS information"},
    {"key": "ils.import_prompt_desc", "default_text": "Your library account has information available ({details}). Would you like to import it for prefilling, or enter your details manually?", "location": "Welcome Tutorial / Banner", "description": "Prompt description in welcome tour"},
    {"key": "ils.import_vault_desc", "default_text": "Your library account has some of your details ({details}). Would you like to add them to Your details, or type them in yourself?", "location": "Identity Vault / Banner", "description": "Prompt description in Identity Vault"},
    {"key": "ils.import_action_import", "default_text": "Import my information", "location": "Welcome Tutorial & Identity Vault / Buttons", "description": "Button to import ILS profile info"},
    {"key": "ils.import_action_discard", "default_text": "Let me enter it", "location": "Welcome Tutorial & Identity Vault / Buttons", "description": "Button to enter info manually and keep fields blank"},
    {"key": "ils.import_success", "default_text": "Your details were imported.", "location": "Global / Notifications", "description": "Confirmation message after ILS import"},
    {"key": "sip2.field_mapping_title", "default_text": "Patron Field Mapping & Consent", "location": "Settings / SIP2 Provider", "description": "Heading for SIP2 demographic field mapping"},
    {"key": "sip2.field_mapping_desc", "default_text": "Import demographic information from the ILS into patron accounts.", "location": "Settings / SIP2 Provider", "description": "Description for field mapping"},
    {"key": "sip2.patron_choice_title", "default_text": "Patron-Driven Import (Consent Choice)", "location": "Settings / SIP2 Provider", "description": "Heading for patron consent option"},
    {"key": "sip2.patron_choice_desc", "default_text": "When enabled, patrons click 'Import my information' or 'Let me enter it' after logging in. Non-forced fields remain blank until chosen.", "location": "Settings / SIP2 Provider", "description": "Description of patron consent flow"},
    {"key": "sip2.consent_required", "default_text": "Consent Required", "location": "Settings / SIP2 Provider", "description": "Status badge when consent is required"},
    {"key": "sip2.auto_import_all", "default_text": "Auto-Import All", "location": "Settings / SIP2 Provider", "description": "Status badge when all fields are automatically imported"},
    {"key": "sip2.forced_fields_label", "default_text": "Forced Fields (Comma-separated, e.g. library, name)", "location": "Settings / SIP2 Provider", "description": "Label for mandatory fields"},
    {"key": "sip2.forced_fields_desc", "default_text": "Fields listed here are force-imported automatically upon sign-in. Non-listed fields remain patron-driven.", "location": "Settings / SIP2 Provider", "description": "Helper note for forced fields"},
    {"key": "sip2.previous_card_title", "default_text": "Reissued Card Linking", "location": "Settings / SIP2 Provider", "description": "Heading for reissued-card account-linking section"},
    {"key": "sip2.previous_card_desc", "default_text": "If your ILS reports a patron's old card number(s) when it issues a new one, point this at that field so a reissued card links to the patron's existing account instead of creating a duplicate. Leave the field code blank to turn this off.", "location": "Settings / SIP2 Provider", "description": "Description of reissued-card linking"},
    {"key": "sip2.previous_card_field_label", "default_text": "Previous Card Field Code (e.g. XC)", "location": "Settings / SIP2 Provider", "description": "Label for the SIP2 field code carrying old barcodes"},
    {"key": "sip2.previous_card_format_label", "default_text": "Format", "location": "Settings / SIP2 Provider", "description": "Label for the previous-card value format selector"},
    {"key": "sip2.previous_card_format_delimited", "default_text": "Delimited — one field, multiple values separated by a character", "location": "Settings / SIP2 Provider", "description": "Option: delimited previous-card format"},
    {"key": "sip2.previous_card_format_json", "default_text": "JSON array — e.g. [\"OLD123\",\"OLD456\"]", "location": "Settings / SIP2 Provider", "description": "Option: JSON array previous-card format"},
    {"key": "sip2.previous_card_delimiter_label", "default_text": "Delimiter character", "location": "Settings / SIP2 Provider", "description": "Label for the previous-card delimiter picker"},
    {"key": "sip2.delim_comma", "default_text": "Comma (,)", "location": "Settings / SIP2 Provider", "description": "Delimiter option: comma"},
    {"key": "sip2.delim_semicolon", "default_text": "Semicolon (;)", "location": "Settings / SIP2 Provider", "description": "Delimiter option: semicolon"},
    {"key": "sip2.delim_tab", "default_text": "Tab", "location": "Settings / SIP2 Provider", "description": "Delimiter option: tab character"},
    {"key": "sip2.delim_custom", "default_text": "Other…", "location": "Settings / SIP2 Provider", "description": "Delimiter option: admin-supplied custom character"},
    {"key": "sip2.delim_custom_placeholder", "default_text": "One character", "location": "Settings / SIP2 Provider", "description": "Placeholder for the custom delimiter input"},
    {"key": "sip2.delim_pipe_note", "default_text": "Note: \"|\" can't be used — SIP2 itself uses it to separate fields, so a vendor field can never contain one.", "location": "Settings / SIP2 Provider", "description": "Explains why pipe isn't offered as a delimiter"},

    # ── Accessibility & Assistive Navigation (WCAG 2.2 AAA) ─────────
    {"key": "a11y.title", "default_text": "Accessibility Settings", "location": "Global / Accessibility", "description": "Header for accessibility options"},
    {"key": "a11y.high_contrast", "default_text": "High Contrast Mode (WCAG 2.2 AAA)", "location": "Global / Accessibility", "description": "Toggle label for high contrast theme"},
    {"key": "a11y.high_contrast_desc", "default_text": "Enhances text and border contrast to exceed 7:1 ratio for low vision.", "location": "Global / Accessibility", "description": "Description of high contrast mode"},
    {"key": "a11y.large_text", "default_text": "Large Text & Target Size", "location": "Global / Accessibility", "description": "Toggle label for large text and 44px touch targets"},
    {"key": "a11y.large_text_desc", "default_text": "Increases font sizes and button targets to at least 44x44px for motor ease.", "location": "Global / Accessibility", "description": "Description of large text mode"},
    {"key": "a11y.reduced_motion", "default_text": "Reduced Motion", "location": "Global / Accessibility", "description": "Toggle label for reduced motion"},
    {"key": "a11y.reduced_motion_desc", "default_text": "Disables animations, transitions, and pulsing indicators.", "location": "Global / Accessibility", "description": "Description of reduced motion"},
    {"key": "a11y.skip_to_content", "default_text": "Skip to main content", "location": "Global / Header", "description": "Screen reader skip-to-content bypass link"},
    {"key": "nav.breadcrumbs", "default_text": "Breadcrumb", "location": "Navigation / Header", "description": "ARIA landmark label for breadcrumbs trail"},
    {"key": "tutorial.a11y_section_title", "default_text": "Theme & Accessibility Options", "location": "Welcome Tutorial / Step 1", "description": "Heading for accessibility choices in setup wizard"},
    {"key": "tutorial.a11y_section_desc", "default_text": "Customize color theme, high contrast, dyslexia-friendly typography, and text scaling to suit your assistive needs.", "location": "Welcome Tutorial / Step 1", "description": "Subtitle for accessibility options in setup wizard"},
    {"key": "a11y.theme", "default_text": "Color Theme", "location": "Global / Accessibility", "description": "Color theme picker label"},
    {"key": "a11y.theme_light", "default_text": "Light", "location": "Global / Accessibility", "description": "Light theme label"},
    {"key": "a11y.theme_gray", "default_text": "Neutral Gray", "location": "Global / Accessibility", "description": "Neutral gray theme label"},
    {"key": "a11y.theme_dark", "default_text": "Dark", "location": "Global / Accessibility", "description": "Dark theme label"},
    {"key": "a11y.theme_system", "default_text": "System (Auto)", "location": "Global / Accessibility", "description": "Auto OS color scheme theme label"},
    {"key": "a11y.theme_space", "default_text": "Space Explorer", "location": "Global / Accessibility", "description": "Space Explorer high-contrast theme label"},
    {"key": "a11y.font_size", "default_text": "Font Size & Scaling", "location": "Global / Accessibility", "description": "Font scaling slider label"},
    {"key": "a11y.font_preview_label", "default_text": "Live Preview", "location": "Global / Accessibility", "description": "Live preview label for font slider"},
    {"key": "a11y.font_preview_sample", "default_text": "This text previews your selected font size in real time. All tables, forms, and menus adjust proportionally across OpenOptOut.", "location": "Global / Accessibility", "description": "Sample text inside font size preview box"},
    {"key": "a11y.contrast_checkbox_desc", "default_text": "Enforces maximum contrast (21:1) adapting to your chosen theme. Light theme renders crisp black-on-white; dark theme renders vivid white-on-black with high-visibility borders.", "location": "Global / Accessibility", "description": "Helper note for theme-aware high contrast"},
    {"key": "a11y.dyslexic_font", "default_text": "Dyslexia-Friendly Font (OpenDyslexic)", "location": "Global / Accessibility", "description": "Toggle label for OpenDyslexic font family"},
    {"key": "a11y.dyslexic_font_desc", "default_text": "Switches typography across the platform to OpenDyslexic with weighted bottoms to enhance reading flow.", "location": "Global / Accessibility", "description": "Description of dyslexia-friendly font option"},
    {"key": "a11y.dyslexic_font_short", "default_text": "Dyslexia Font", "location": "Navigation / Sidebar", "description": "Short label for sidebar dyslexia font toggle"},
    # ── Added with the plain-language pass ──
    {"key": "nav.checklist", "default_text": "Checklist", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.discovery", "default_text": "Find listings", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.email_monitor", "default_text": "Replies", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.scheduled", "default_text": "Check again", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.captcha", "default_text": "CAPTCHAs", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.inboxes", "default_text": "Email inboxes", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.help", "default_text": "Help", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.credit_freeze", "default_text": "Freeze credit", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.admin", "default_text": "Admin", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.admin_panel", "default_text": "Admin panel", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.broker_updates", "default_text": "Broker updates", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.broker_health", "default_text": "Broker health", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.spec_helpers", "default_text": "Automatic broker steps", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.letters", "default_text": "Opt-out letters", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.monitoring", "default_text": "Monitoring and alerts", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.terms", "default_text": "Terms", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.usage_stats", "default_text": "Usage statistics", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.broker_priority", "default_text": "Broker priority", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.data_sharing", "default_text": "Data sharing", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.parent_companies", "default_text": "Parent companies", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.registries", "default_text": "State registries", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.websearch", "default_text": "Web search", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.branding", "default_text": "Branding", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.reporting", "default_text": "Reporting", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.database", "default_text": "Database", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.worker_fleet", "default_text": "Worker fleet", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.logs", "default_text": "System logs", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.plugin_upload", "default_text": "Add a plugin", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.plugin_docs", "default_text": "Plugin guide", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.add_brokers", "default_text": "Add brokers", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "status.pending", "default_text": "Waiting to send", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.sent", "default_text": "Sent", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.submitted", "default_text": "Sent", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.confirmed", "default_text": "Removed", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.rejected", "default_text": "Refused", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.failed", "default_text": "Didn't work", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.needs_manual", "default_text": "Needs you", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.recheck_due", "default_text": "Check again", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.resistant", "default_text": "Often refuses", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.compliant", "default_text": "Usually removes", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.inconsistent", "default_text": "Mixed results", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.undetermined", "default_text": "Not known yet", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.form", "default_text": "Web form", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.email", "default_text": "Email", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.manual", "default_text": "By hand", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.phone", "default_text": "By phone", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.easy", "default_text": "Easy", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.medium", "default_text": "Medium", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.hard", "default_text": "Hard", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.running", "default_text": "Running", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.done", "default_text": "Done", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.error", "default_text": "Problem", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.success", "default_text": "Worked", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.failure", "default_text": "Didn't work", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.captcha", "default_text": "CAPTCHA", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    {"key": "status.skipped", "default_text": "Skipped", "location": "Status labels / Badges", "description": "Status label shown on badges"},
    # ── Added with the plain-language pass ──
    {"key": "nav.backups", "default_text": "Backups", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    # ── Added with the plain-language pass ──
    {"key": "nav.deadlines", "default_text": "Deadline report", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    # ── Added with the plain-language pass ──
    {"key": "nav.privacy_record", "default_text": "Privacy record", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.calendar", "default_text": "Calendar", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
    {"key": "nav.system_updates", "default_text": "System updates", "location": "Navigation / Sidebar", "description": "Menu and page-path label"},
]

# ── Built-in languages ────────────────────────────────────────────────────────
# English is the only language in core (MASTER_DICTIONARY above). Every other
# language ships as a language-pack plugin in plugins/bundled/languages/
# (lang-<code>/manifest.json + messages.json), the same format a community
# pack uses. At startup they're copied into <plugins_root>/languages/ and
# registered as plugins (plugins/language_packs.py), so an admin can turn one
# off or replace it like any other plugin.

# ── Page text ────────────────────────────────────────────────────────────────
# Phrases on the screens are written in English in the frontend, wrapped in
# tx("..."), and the English text is the key. The list of them is generated
# from the code (scripts/extract_page_texts.mjs) into page_texts.json; each
# language pack translates them in texts.json ({english: translation}).

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _load_page_texts() -> List[Dict[str, Any]]:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "page_texts.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("texts", [])
    except (OSError, ValueError):
        return []


PAGE_TEXTS = _load_page_texts()
PAGE_TEXT_SET = {t["text"] for t in PAGE_TEXTS}


def placeholders(text: str) -> set:
    return set(_PLACEHOLDER.findall(text or ""))


def clean_texts(texts: Dict[str, Any]) -> Dict[str, str]:
    """Only known phrases, translations that keep every {placeholder}, and contain no dangerous tags/URIs."""
    return {k: v for k, v in (texts or {}).items()
            if k in PAGE_TEXT_SET and isinstance(v, str) and v.strip()
            and placeholders(v) == placeholders(k)
            and is_safe_translation_string(k, v)[0]}


def _bundled_languages_dir() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "plugins", "bundled", "languages")


def _read_pack(pkg_path: str) -> Optional[Dict[str, Any]]:
    """manifest + messages of one language pack directory, or None."""
    manifest_file = os.path.join(pkg_path, "manifest.json")
    if not os.path.isfile(manifest_file):
        return None
    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    code = manifest.get("language_code") or manifest.get("id", "").replace("lang-", "").replace("lang_", "")
    if not code:
        return None
    texts = {}
    texts_path = os.path.join(pkg_path, "texts.json")
    if os.path.isfile(texts_path):
        with open(texts_path, "r", encoding="utf-8") as tf:
            texts = json.load(tf)
    messages = {}
    for msg_name in ("messages.json", "translations.json"):
        msg_path = os.path.join(pkg_path, msg_name)
        if os.path.isfile(msg_path):
            with open(msg_path, "r", encoding="utf-8") as mf:
                messages = json.load(mf)
            break
    known = {d["key"] for d in MASTER_DICTIONARY}
    return {
        "code": code,
        "id": manifest.get("id", os.path.basename(pkg_path)),
        # Folder of the pack; plugins/<plugin_id>.json in it translates other
        # plugins' text (see plugins/plugin_i18n.py).
        "path": pkg_path,
        "name": manifest.get("language_name") or manifest.get("name", code),
        "native_name": manifest.get("native_name") or manifest.get("language_name") or manifest.get("name", code),
        "author": manifest.get("author", ""),
        "version": manifest.get("version", "1.0"),
        "is_rtl": bool(manifest.get("is_rtl", code in RTL_LANGUAGES)),
        "messages": {k: v for k, v in messages.items() if k in known and isinstance(v, str) and v and is_safe_translation_string(k, v)[0]},
        "texts": clean_texts(texts),
    }


def _load_bundled_languages() -> Dict[str, Dict[str, Any]]:
    out = {}
    d = _bundled_languages_dir()
    if not os.path.isdir(d):
        return out
    for entry in sorted(os.listdir(d)):
        try:
            pack = _read_pack(os.path.join(d, entry))
            if pack:
                out[pack["code"]] = pack
        except Exception as e:
            log.warning("Built-in language pack %s couldn't be loaded: %s", entry, e)
    return out


BUNDLED_LANGUAGES = _load_bundled_languages()
# code -> messages for every built-in language pack (kept under this name for
# callers and tests that predate the move to plugins).
BUILTIN_TRANSLATIONS = {code: pack["messages"] for code, pack in BUNDLED_LANGUAGES.items()}

# Built-in languages are offered to every install once (see
# offer_new_builtin_languages); an admin who turns one off keeps it off.
DEFAULT_ENABLED = ["en"] + sorted(BUNDLED_LANGUAGES)


def is_rtl_language(lang_code: str) -> bool:
    """Returns True if the language code represents a Right-to-Left script."""
    base = (lang_code or "").lower().split("-")[0].strip()
    return base in RTL_LANGUAGES


def get_i18n_settings() -> Dict[str, Any]:
    """Retrieve i18n configuration from settings store."""
    settings = settings_store.load_settings()
    i18n_cfg = settings.get("i18n", {})
    return {
        "enabled_languages": i18n_cfg.get("enabled_languages", list(DEFAULT_ENABLED)),
        "default_language": i18n_cfg.get("default_language", "en"),
        "custom_languages": i18n_cfg.get("custom_languages", {}),
        "custom_translations": i18n_cfg.get("custom_translations", {}),
    }


def save_i18n_settings(cfg: Dict[str, Any]) -> None:
    """Persist i18n configuration to settings store."""
    settings = settings_store.load_settings()
    settings["i18n"] = cfg
    settings_store.save_settings(settings)


_DISABLED_CACHE = {"at": 0.0, "ids": set()}


def _disabled_language_plugins() -> set:
    """Plugin ids of language packs an admin turned off on the Plugins page
    (cached for 30 seconds; never creates a database just to ask)."""
    import time
    if time.monotonic() - _DISABLED_CACHE["at"] < 30:
        return _DISABLED_CACHE["ids"]
    url = os.getenv("DATABASE_URL", "sqlite:///./privacy_pipeline.db")
    if url.startswith("sqlite:///") and not os.path.exists(url[len("sqlite:///"):]):
        return set()
    ids = _query_disabled()
    _DISABLED_CACHE.update(at=time.monotonic(), ids=ids)
    return ids


def _query_disabled() -> set:
    try:
        try:
            from ..models.database import SessionLocal, InstalledPlugin
        except (ImportError, ValueError):
            from models.database import SessionLocal, InstalledPlugin
        db = SessionLocal()
        try:
            return {r.plugin_id for r in db.query(InstalledPlugin).filter(InstalledPlugin.enabled == False).all()}  # noqa: E712
        finally:
            db.close()
    except Exception:
        return set()


def scan_language_plugins() -> Dict[str, Dict[str, Any]]:
    """
    Language packs installed under <plugins_root>/languages/ (built-in copies
    and community packs), minus any an admin turned off. Returns
    { lang_code: {id, name, native_name, author, version, is_rtl, messages} }.
    """
    try:
        from ..plugins import layout
    except (ImportError, ValueError):
        try:
            from plugins import layout
        except ImportError:
            layout = None
    if not layout:
        return {}
    lang_dir = os.path.join(layout.plugins_root(), "languages")
    found_packs = {}
    if not os.path.isdir(lang_dir):
        return found_packs
    disabled = _disabled_language_plugins()
    for entry in sorted(os.listdir(lang_dir)):
        pkg_path = os.path.join(lang_dir, entry)
        if not os.path.isdir(pkg_path) or entry.startswith("."):
            continue
        try:
            pack = _read_pack(pkg_path)
            if pack and pack["id"] not in disabled:
                found_packs[pack["code"]] = pack
        except Exception as e:
            log.warning("Failed scanning language pack at %s: %s", pkg_path, e)
    return found_packs


def _builtin_pack(code: str, disabled: Optional[set] = None) -> Optional[Dict[str, Any]]:
    pack = BUNDLED_LANGUAGES.get(code)
    if pack is None:
        return None
    if pack["id"] in (disabled if disabled is not None else _disabled_language_plugins()):
        return None
    return pack


def get_available_languages() -> List[Dict[str, Any]]:
    """
    Enumerate all languages available in the system:
    combining well-known catalog, scanned plugin language packs, and custom admin additions.
    """
    cfg = get_i18n_settings()
    enabled_set = set(cfg["enabled_languages"])
    plugin_packs = scan_language_plugins()

    catalog = {}
    # 1. Base known languages
    for code, info in KNOWN_LANGUAGES.items():
        catalog[code] = {
            "code": code,
            "name": info["name"],
            "native_name": info["native_name"],
            "is_rtl": info["is_rtl"],
            "source": "builtin",
            "enabled": code in enabled_set,
        }

    # 2. Language packs: built in (shipped as plugins) and installed
    disabled = _disabled_language_plugins()
    for code, pack in BUNDLED_LANGUAGES.items():
        entry = catalog.setdefault(code, {"code": code, "name": pack["name"], "native_name": pack["native_name"],
                                          "is_rtl": pack["is_rtl"], "enabled": code in enabled_set})
        entry.update(source="plugin", built_in=True, plugin_id=pack["id"], plugin_off=pack["id"] in disabled)
        if entry["plugin_off"]:
            entry["enabled"] = False
    for code, pack in plugin_packs.items():
        if code in catalog:
            catalog[code]["source"] = "plugin"
            catalog[code]["plugin_id"] = pack["id"]
        else:
            catalog[code] = {
                "code": code,
                "name": pack["name"],
                "native_name": pack["name"],
                "is_rtl": pack["is_rtl"],
                "source": "plugin",
                "enabled": code in enabled_set,
            }

    # 3. Custom admin-created languages
    for code, custom in cfg["custom_languages"].items():
        catalog[code] = {
            "code": code,
            "name": custom.get("name", code),
            "native_name": custom.get("native_name", code),
            "is_rtl": custom.get("is_rtl", is_rtl_language(code)),
            "source": "custom",
            "enabled": code in enabled_set,
        }

    return sorted(list(catalog.values()), key=lambda x: (not x["enabled"], x["code"] != "en", x["name"]))


def get_dictionary() -> List[Dict[str, str]]:
    """
    Everything translatable, with where it appears: the keyed dictionary
    (menus, badges, onboarding) and then every phrase on the screens, whose
    key is its English text.
    """
    return MASTER_DICTIONARY + [
        {"key": t["text"], "default_text": t["text"], "location": "Screen: " + ", ".join(t.get("where", [])[:3]),
         "description": t.get("note", "")}
        for t in PAGE_TEXTS
    ]


def get_translations_for_locale(locale: str) -> Dict[str, str]:
    """
    Resolve complete translation dictionary for a given language code.
    Resolution order (highest precedence wins):
      1. Default English text from MASTER_DICTIONARY
      2. The built-in language pack (plugins/bundled/languages/lang-<code>/)
      3. Installed language packs (<plugins_root>/languages/<id>/), e.g. an admin's own
      4. Admin custom replacements / overrides from settings
    """
    code = (locale or "en").lower().strip()

    # 1. Base defaults (English)
    result = {item["key"]: item["default_text"] for item in MASTER_DICTIONARY}

    # If asking for English, apply English custom replacements and return
    cfg = get_i18n_settings()
    custom_overrides = cfg["custom_translations"].get(code, {})

    if code == "en":
        result.update(custom_overrides)
        return result

    # 2. Built-in language pack (unless an admin turned it off)
    disabled = _disabled_language_plugins()
    pack = _builtin_pack(code, disabled)
    if pack is not None:
        result.update(pack["messages"])
        result.update(pack.get("texts", {}))

    # 3. Installed language packs (an admin's own pack for the same code wins)
    plugin_packs = scan_language_plugins()
    if code in plugin_packs:
        result.update(plugin_packs[code]["messages"])
        result.update(plugin_packs[code].get("texts", {}))

    # 4. In-system custom translations / overrides (highest precedence)
    result.update(custom_overrides)

    return result


def set_custom_translation_strings(locale: str, updates: Dict[str, str]) -> Dict[str, str]:
    """
    Save custom translation string replacements for a language.
    Super admins and managers use this to modify wording or translate keys in-system.
    """
    code = (locale or "en").lower().strip()
    cfg = get_i18n_settings()

    if code not in cfg["custom_translations"]:
        cfg["custom_translations"][code] = {}

    for k, v in updates.items():
        if v is None or v == "":
            cfg["custom_translations"][code].pop(k, None)
        else:
            cfg["custom_translations"][code][k] = str(v).strip()

    save_i18n_settings(cfg)
    return get_translations_for_locale(code)


def toggle_language_enabled(code: str, enabled: bool) -> List[Dict[str, Any]]:
    """Enable or disable a language for the platform."""
    code = code.lower().strip()
    cfg = get_i18n_settings()
    current = set(cfg["enabled_languages"])

    if enabled:
        current.add(code)
    else:
        if code == "en":
            raise ValueError("English cannot be disabled as it is the system fallback language.")
        current.discard(code)

    cfg["enabled_languages"] = sorted(list(current))
    save_i18n_settings(cfg)
    return get_available_languages()


def register_custom_language(code: str, name: str, native_name: str, is_rtl: bool) -> Dict[str, Any]:
    """Register a new language code in the system."""
    code = code.lower().strip()
    if not code or not code.replace("-", "").isalnum():
        raise ValueError("Language code must be alphanumeric (e.g. 'es', 'pt-br')")

    cfg = get_i18n_settings()
    cfg["custom_languages"][code] = {
        "name": name.strip(),
        "native_name": native_name.strip() or name.strip(),
        "is_rtl": bool(is_rtl),
    }
    if code not in cfg["enabled_languages"]:
        cfg["enabled_languages"].append(code)

    save_i18n_settings(cfg)
    return {
        "code": code,
        "name": name,
        "native_name": native_name,
        "is_rtl": is_rtl,
        "source": "custom",
        "enabled": True,
    }


def offer_new_builtin_languages() -> List[str]:
    """
    Turn on built-in languages added since this install last looked, once.
    Called at startup. Languages an admin already turned off stay off, because
    each code is only ever offered one time.
    """
    settings = settings_store.load_settings()
    i18n_cfg = settings.get("i18n")
    if not i18n_cfg or "enabled_languages" not in i18n_cfg:
        return []          # never saved: the defaults already include them
    offered = set(i18n_cfg.get("builtins_offered") or ["en", "es", "ar", "fr", "pirate"])
    new = [c for c in DEFAULT_ENABLED if c not in offered]
    if not new:
        return []
    enabled = list(i18n_cfg["enabled_languages"])
    enabled += [c for c in new if c not in enabled]
    i18n_cfg["enabled_languages"] = enabled
    i18n_cfg["builtins_offered"] = sorted(offered | set(new))
    settings["i18n"] = i18n_cfg
    settings_store.save_settings(settings)
    log.info("Turned on newly built-in languages: %s", ", ".join(new))
    return new
