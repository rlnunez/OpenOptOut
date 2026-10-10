"""
Internationalization (i18n) and Right-to-Left (RTL) Engine (Roadmap Item 17).

Provides:
  - Master English dictionary with categorized keys and screen locations ("where it appears")
  - Out-of-the-box translations for multiple languages (including Arabic for RTL and Spanish/French)
  - In-system translation replacement interface allowing super admins/managers to override wording
  - Discovery of community language pack add-ons (<plugins_root>/languages/<id>/)
  - Dynamic RTL detection and metadata
  - User preferred language persistence
"""

import json
import logging
import os
from typing import Dict, List, Optional, Any

try:
    from . import settings_store
except (ImportError, ValueError):
    from core import settings_store

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
    {"key": "nav.requests", "default_text": "Removal Requests", "location": "Navigation / Sidebar", "description": "Sidebar link to broker removal requests table"},
    {"key": "nav.vault", "default_text": "Identity Vault", "location": "Navigation / Sidebar", "description": "Sidebar link to manage personal data identities"},
    {"key": "nav.family", "default_text": "Family Members", "location": "Navigation / Sidebar", "description": "Sidebar link to manage protected family profiles"},
    {"key": "nav.brokers", "default_text": "Data Brokers", "location": "Navigation / Sidebar", "description": "Sidebar link to broker directory and status"},
    {"key": "nav.settings", "default_text": "Settings", "location": "Navigation / Sidebar", "description": "Sidebar link to platform configuration"},
    {"key": "nav.translations", "default_text": "Translations", "location": "Navigation / Sidebar", "description": "Admin link to in-system translation editor"},
    {"key": "nav.plugins", "default_text": "Plugins", "location": "Navigation / Sidebar", "description": "Sidebar link to plugins and add-on catalog"},
    {"key": "nav.logout", "default_text": "Log Out", "location": "Navigation / User Menu", "description": "Button to log out of current session"},
    {"key": "nav.welcome_tour", "default_text": "Welcome Tour", "location": "Navigation / User Menu", "description": "Button to re-open the guided onboarding walkthrough"},
    {"key": "nav.language", "default_text": "Language", "location": "Header / Language Picker", "description": "Label for active language switcher"},

    # ── Common UI Controls ──────────────────────────────────────────
    {"key": "common.save", "default_text": "Save", "location": "Global / Form Buttons", "description": "Save changes button"},
    {"key": "common.cancel", "default_text": "Cancel", "location": "Global / Form Buttons", "description": "Cancel current dialog or form"},
    {"key": "common.delete", "default_text": "Delete", "location": "Global / Form Buttons", "description": "Delete confirmation button"},
    {"key": "common.edit", "default_text": "Edit", "location": "Global / Table Actions", "description": "Edit row action"},
    {"key": "common.loading", "default_text": "Loading...", "location": "Global / States", "description": "Asynchronous loading indicator"},
    {"key": "common.success", "default_text": "Success", "location": "Global / Notifications", "description": "Success banner title"},
    {"key": "common.error", "default_text": "Error", "location": "Global / Notifications", "description": "Error banner title"},
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
    {"key": "vault.title", "default_text": "Identity Vault", "location": "Identity Vault / Header", "description": "Page heading for personal data management"},
    {"key": "vault.description", "default_text": "The personal identifiers below are used solely to submit opt-out requests and are encrypted at rest.", "location": "Identity Vault / Header", "description": "Privacy assurance subtext"},
    {"key": "vault.add_name", "default_text": "Add Name Variant", "location": "Identity Vault / Names", "description": "Button to add alias or previous name"},
    {"key": "vault.add_address", "default_text": "Add Address", "location": "Identity Vault / Addresses", "description": "Button to add current or historical address"},
    {"key": "vault.add_phone", "default_text": "Add Phone Number", "location": "Identity Vault / Phones", "description": "Button to add phone number"},
    {"key": "vault.add_email", "default_text": "Add Email Address", "location": "Identity Vault / Emails", "description": "Button to add email identity"},

    # ── Onboarding / Welcome Tutorial Modal ────────────────────────
    {"key": "tutorial.welcome_title", "default_text": "Welcome to OpenOptOut", "location": "Welcome Tutorial / Step 1", "description": "Main onboarding modal header"},
    {"key": "tutorial.welcome_desc", "default_text": "Let's take a moment to customize your experience and configure your privacy protections.", "location": "Welcome Tutorial / Step 1", "description": "Introduction to user setup walkthrough"},
    {"key": "tutorial.lang_step_title", "default_text": "Choose Your Preferred Language", "location": "Welcome Tutorial / Step 1", "description": "Step 1 title for language selection"},
    {"key": "tutorial.lang_step_desc", "default_text": "Select your language below. The interface, notifications, and layout will adapt immediately.", "location": "Welcome Tutorial / Step 1", "description": "Explanation of language options"},
    {"key": "tutorial.pii_step_title", "default_text": "Protect Your Identity", "location": "Welcome Tutorial / Step 2", "description": "Step 2 title for profile information"},
    {"key": "tutorial.pii_step_desc", "default_text": "Provide your name and city/state so automated agents can locate and scrub your listings.", "location": "Welcome Tutorial / Step 2", "description": "Why PII is collected"},
    {"key": "tutorial.email_step_title", "default_text": "Opt-Out Communications", "location": "Welcome Tutorial / Step 3", "description": "Step 3 title for email configuration"},
    {"key": "tutorial.email_step_desc", "default_text": "OpenOptOut dispatches removal requests using dedicated inboxes and monitors broker responses.", "location": "Welcome Tutorial / Step 3", "description": "Explanation of email handling"},
    {"key": "tutorial.tour_step_title", "default_text": "Platform Tour & Quick Navigation", "location": "Welcome Tutorial / Step 4", "description": "Step 4 title for UI walkthrough"},
    {"key": "tutorial.tour_step_desc", "default_text": "Explore your dashboard to view verified removals, manage family profiles, and monitor broker health.", "location": "Welcome Tutorial / Step 4", "description": "Tour summary"},
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
    {"key": "ils.import_vault_desc", "default_text": "Your library account has information available ({details}). Would you like to import it into your Identity Vault, or enter your details manually?", "location": "Identity Vault / Banner", "description": "Prompt description in Identity Vault"},
    {"key": "ils.import_action_import", "default_text": "Import my information", "location": "Welcome Tutorial & Identity Vault / Buttons", "description": "Button to import ILS profile info"},
    {"key": "ils.import_action_discard", "default_text": "Let me enter it", "location": "Welcome Tutorial & Identity Vault / Buttons", "description": "Button to enter info manually and keep fields blank"},
    {"key": "ils.import_success", "default_text": "Information imported into Identity Vault.", "location": "Global / Notifications", "description": "Confirmation message after ILS import"},
    {"key": "sip2.field_mapping_title", "default_text": "Patron Field Mapping & Consent", "location": "Settings / SIP2 Provider", "description": "Heading for SIP2 demographic field mapping"},
    {"key": "sip2.field_mapping_desc", "default_text": "Import demographic information from the ILS into patron accounts.", "location": "Settings / SIP2 Provider", "description": "Description for field mapping"},
    {"key": "sip2.patron_choice_title", "default_text": "Patron-Driven Import (Consent Choice)", "location": "Settings / SIP2 Provider", "description": "Heading for patron consent option"},
    {"key": "sip2.patron_choice_desc", "default_text": "When enabled, patrons click 'Import my information' or 'Let me enter it' after logging in. Non-forced fields remain blank until chosen.", "location": "Settings / SIP2 Provider", "description": "Description of patron consent flow"},
    {"key": "sip2.consent_required", "default_text": "Consent Required", "location": "Settings / SIP2 Provider", "description": "Status badge when consent is required"},
    {"key": "sip2.auto_import_all", "default_text": "Auto-Import All", "location": "Settings / SIP2 Provider", "description": "Status badge when all fields are automatically imported"},
    {"key": "sip2.forced_fields_label", "default_text": "Forced Fields (Comma-separated, e.g. library, name)", "location": "Settings / SIP2 Provider", "description": "Label for mandatory fields"},
    {"key": "sip2.forced_fields_desc", "default_text": "Fields listed here are force-imported automatically upon sign-in. Non-listed fields remain patron-driven.", "location": "Settings / SIP2 Provider", "description": "Helper note for forced fields"},

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
    {"key": "tutorial.a11y_section_desc", "default_text": "Customize color theme, high contrast, and text scaling to suit your assistive needs.", "location": "Welcome Tutorial / Step 1", "description": "Subtitle for accessibility options in setup wizard"},
    {"key": "a11y.theme", "default_text": "Color Theme", "location": "Global / Accessibility", "description": "Color theme picker label"},
    {"key": "a11y.theme_light", "default_text": "Light", "location": "Global / Accessibility", "description": "Light theme label"},
    {"key": "a11y.theme_gray", "default_text": "Neutral Gray", "location": "Global / Accessibility", "description": "Neutral gray theme label"},
    {"key": "a11y.theme_dark", "default_text": "Dark", "location": "Global / Accessibility", "description": "Dark theme label"},
    {"key": "a11y.theme_system", "default_text": "System (Auto)", "location": "Global / Accessibility", "description": "Auto OS color scheme theme label"},
    {"key": "a11y.font_size", "default_text": "Font Size & Scaling", "location": "Global / Accessibility", "description": "Font scaling slider label"},
    {"key": "a11y.font_preview_label", "default_text": "Live Preview", "location": "Global / Accessibility", "description": "Live preview label for font slider"},
    {"key": "a11y.font_preview_sample", "default_text": "This text previews your selected font size in real time. All tables, forms, and menus adjust proportionally across OpenOptOut.", "location": "Global / Accessibility", "description": "Sample text inside font size preview box"},
    {"key": "a11y.contrast_checkbox_desc", "default_text": "Enforces maximum contrast (21:1) adapting to your chosen theme. Light theme renders crisp black-on-white; dark theme renders vivid white-on-black with high-visibility borders.", "location": "Global / Accessibility", "description": "Helper note for theme-aware high contrast"},
    {"key": "a11y.dyslexic_font", "default_text": "Dyslexia-Friendly Font (OpenDyslexic)", "location": "Global / Accessibility", "description": "Toggle label for OpenDyslexic font family"},
    {"key": "a11y.dyslexic_font_desc", "default_text": "Switches typography across the platform to OpenDyslexic with weighted bottoms to enhance reading flow.", "location": "Global / Accessibility", "description": "Description of dyslexia-friendly font option"},
    {"key": "a11y.dyslexic_font_short", "default_text": "Dyslexia Font", "location": "Navigation / Sidebar", "description": "Short label for sidebar dyslexia font toggle"},
]

# Built-in Spanish translations
BUILTIN_SPANISH = {
    "nav.dashboard": "Panel de Control",
    "nav.requests": "Solicitudes de Eliminación",
    "nav.vault": "Bóveda de Identidad",
    "nav.family": "Miembros de la Familia",
    "nav.brokers": "Brokers de Datos",
    "nav.settings": "Configuración",
    "nav.translations": "Traducciones",
    "nav.plugins": "Complementos",
    "nav.logout": "Cerrar Sesión",
    "nav.welcome_tour": "Guía de Bienvenida",
    "nav.language": "Idioma",

    "common.save": "Guardar",
    "common.cancel": "Cancelar",
    "common.delete": "Eliminar",
    "common.edit": "Editar",
    "common.loading": "Cargando...",
    "common.success": "Éxito",
    "common.error": "Error",
    "common.next": "Siguiente",
    "common.back": "Atrás",
    "common.finish": "Finalizar",
    "common.search": "Buscar...",
    "common.enabled": "Habilitado",
    "common.disabled": "Deshabilitado",

    "dashboard.title": "Resumen de Protección de Privacidad",
    "dashboard.subtitle": "Monitoreo y eliminación de registros personales en brokers de datos comerciales.",
    "dashboard.total_brokers": "Brokers Rastreados",
    "dashboard.confirmed_removals": "Eliminaciones Confirmadas",
    "dashboard.pending_requests": "En Progreso",
    "dashboard.protection_score": "Cobertura de Protección",
    "dashboard.start_optout_all": "Ejecutar Eliminaciones Automáticas",

    "vault.title": "Bóveda de Identidad",
    "vault.description": "Los identificadores a continuación se utilizan únicamente para enviar solicitudes de exclusión y se cifran en reposo.",
    "vault.add_name": "Agregar Variante de Nombre",
    "vault.add_address": "Agregar Dirección",
    "vault.add_phone": "Agregar Teléfono",
    "vault.add_email": "Agregar Correo Electrónico",

    "tutorial.welcome_title": "Bienvenido a OpenOptOut",
    "tutorial.welcome_desc": "Tomemos un momento para personalizar su experiencia y configurar sus protecciones de privacidad.",
    "tutorial.lang_step_title": "Elija su Idioma Preferido",
    "tutorial.lang_step_desc": "Seleccione su idioma a continuación. La interfaz, las notificaciones y el diseño se adaptarán de inmediato.",
    "tutorial.pii_step_title": "Proteja su Identidad",
    "tutorial.pii_step_desc": "Proporcione su nombre y ciudad/estado para que los agentes automatizados puedan localizar y eliminar sus listados.",
    "tutorial.email_step_title": "Comunicaciones de Exclusión",
    "tutorial.email_step_desc": "OpenOptOut envía solicitudes de eliminación utilizando buzones dedicados y monitorea las respuestas de los brokers.",
    "tutorial.tour_step_title": "Recorrido por la Plataforma",
    "tutorial.tour_step_desc": "Explore su panel para ver eliminaciones verificadas, administrar perfiles familiares y supervisar el estado de los brokers.",
    "tutorial.skip": "Omitir Tutorial",
    "tutorial.start_protecting": "Comenzar a Proteger mis Datos",

    "i18n.manager_title": "Administrador de Idiomas y Traducción",
    "i18n.manager_desc": "Gestione idiomas disponibles, personalice términos e inspeccione dónde aparece cada texto.",
    "i18n.active_languages": "Idiomas Activos",
    "i18n.add_language": "Agregar Idioma",
    "i18n.filter_by_location": "Filtrar por Ubicación de Pantalla",
    "i18n.source_english": "Inglés Original",
    "i18n.translated_text": "Texto Traducido / Reemplazo Personalizado",
    "i18n.where_it_appears": "Dónde Aparece",
    "i18n.save_translations": "Guardar Traducciones Personalizadas",
    "i18n.reset_defaults": "Restablecer a Valores Predeterminados",

    "ils.import_prompt_title": "¿Importar información de su tarjeta de biblioteca?",
    "ils.import_prompt_desc": "Su cuenta de biblioteca tiene información disponible ({details}). ¿Desea importarla para rellenar automáticamente o ingresar sus datos manualmente?",
    "ils.import_vault_desc": "Su cuenta de biblioteca tiene información disponible ({details}). ¿Desea importarla a su Bóveda de Identidad o ingresar sus datos manualmente?",
    "ils.import_action_import": "Importar mi información",
    "ils.import_action_discard": "Permítanme ingresarla",
    "ils.import_success": "Información importada en la Bóveda de Identidad.",
    "sip2.field_mapping_title": "Mapeo de Campos de Usuarios y Consentimiento",
    "sip2.field_mapping_desc": "Importar información demográfica del ILS a las cuentas de usuarios.",
    "sip2.patron_choice_title": "Importación Impulsada por el Usuario (Elección de Consentimiento)",
    "sip2.patron_choice_desc": "Cuando está habilitado, los usuarios eligen 'Importar mi información' o 'Permítanme ingresarla' después de iniciar sesión. Los campos no forzados permanecen vacíos hasta que se elijan.",
    "sip2.consent_required": "Consentimiento Requerido",
    "sip2.auto_import_all": "Importación Automática Total",
    "sip2.forced_fields_label": "Campos Forzados (separados por comas, ej. library, name)",
    "sip2.forced_fields_desc": "Los campos indicados aquí se importan automáticamente al iniciar sesión. Los campos no listados dependen de la elección del usuario.",
    "a11y.title": "Configuración de Accesibilidad",
    "a11y.high_contrast": "Modo de Alto Contraste (WCAG 2.2 AAA)",
    "a11y.high_contrast_desc": "Mejora el contraste de texto y bordes superando una relación de 7:1.",
    "a11y.large_text": "Texto Grande y Tamaño de Objetivos",
    "a11y.large_text_desc": "Aumenta el tamaño de fuente y objetivos táctiles a un mínimo de 44x44px.",
    "a11y.reduced_motion": "Movimiento Reducido",
    "a11y.reduced_motion_desc": "Desactiva animaciones, transiciones y efectos visuales continuos.",
    "a11y.skip_to_content": "Saltar al contenido principal",
    "nav.breadcrumbs": "Migas de pan",
    "tutorial.a11y_section_title": "Opciones de Tema y Accesibilidad",
    "tutorial.a11y_section_desc": "Personalice el tema de color, alto contraste y escala de texto según sus necesidades.",
    "a11y.theme": "Tema de Color",
    "a11y.theme_light": "Claro",
    "a11y.theme_gray": "Gris Neutro",
    "a11y.theme_dark": "Oscuro",
    "a11y.theme_system": "Sistema (Automático)",
    "a11y.font_size": "Tamaño de Fuente y Escala",
    "a11y.font_preview_label": "Vista Previa en Vivo",
    "a11y.font_preview_sample": "Este texto previsualiza el tamaño de fuente seleccionado en tiempo real. Todas las tablas, formularios y menús se ajustan proporcionalmente.",
    "a11y.contrast_checkbox_desc": "Aplica contraste máximo (21:1) adaptado a su tema. El tema claro muestra negro puro sobre blanco; el tema oscuro muestra blanco puro sobre negro con bordes de alta visibilidad.",
    "a11y.dyslexic_font": "Tipografía para Dislexia (OpenDyslexic)",
    "a11y.dyslexic_font_desc": "Cambia la tipografía en toda la plataforma a OpenDyslexic con bases reforzadas para facilitar la lectura.",
    "a11y.dyslexic_font_short": "Fuente Dislexia",
}

# Built-in Arabic translations (RTL Demonstration)
BUILTIN_ARABIC = {
    "nav.dashboard": "لوحة التحكم",
    "nav.requests": "طلبات الحذف",
    "nav.vault": "خزينة الهوية",
    "nav.family": "أفراد العائلة",
    "nav.brokers": "وسطاء البيانات",
    "nav.settings": "الإعدادات",
    "nav.translations": "الترجمات واللغات",
    "nav.plugins": "الإضافات",
    "nav.logout": "تسجيل الخروج",
    "nav.welcome_tour": "جولة ترحيبية",
    "nav.language": "اللغة",

    "common.save": "حفظ",
    "common.cancel": "إلغاء",
    "common.delete": "حذف",
    "common.edit": "تعديل",
    "common.loading": "جار التحميل...",
    "common.success": "نجاح",
    "common.error": "خطأ",
    "common.next": "التالي",
    "common.back": "السابق",
    "common.finish": "إنهاء",
    "common.search": "بحث...",
    "common.enabled": "مفعّل",
    "common.disabled": "معطّل",

    "dashboard.title": "نظرة عامة على حماية الخصوصية",
    "dashboard.subtitle": "مراقبة وإزالة السجلات الشخصية عبر وسطاء البيانات التجارية.",
    "dashboard.total_brokers": "الوسطاء المتبعون",
    "dashboard.confirmed_removals": "عمليات الحذف المؤكدة",
    "dashboard.pending_requests": "قيد التنفيذ",
    "dashboard.protection_score": "تغطية الحماية",
    "dashboard.start_optout_all": "تشغيل الحذف الآلي",

    "vault.title": "خزينة الهوية",
    "vault.description": "المعرّفات أدناه تُستخدم فقط لتقديم طلبات الإزالة ويتم تشفيرها أثناء التخزين.",
    "vault.add_name": "إضافة اسم بديل",
    "vault.add_address": "إضافة عنوان",
    "vault.add_phone": "إضافة رقم هاتف",
    "vault.add_email": "إضافة بريد إلكتروني",

    "tutorial.welcome_title": "مرحبًا بك في OpenOptOut",
    "tutorial.welcome_desc": "لنستغرق لحظة لتخصيص تجربتك وضبط تدابير حماية خصوصيتك.",
    "tutorial.lang_step_title": "اختر لغتك المفضلة",
    "tutorial.lang_step_desc": "حدد لغتك أدناه. ستتكيف الواجهة والإشعارات وتخطيط الاتجاه (يمين إلى يسار) فورًا.",
    "tutorial.pii_step_title": "احمِ هويتك الشخصية",
    "tutorial.pii_step_desc": "أدخل اسمك والمدينة والولاية ليتمكن النظام من البحث عن بياناتك وإزالتها تلقائيًا.",
    "tutorial.email_step_title": "إعدادات البريد لطلبات الإزالة",
    "tutorial.email_step_desc": "يقوم النظام بإرسال مراسلات الحذف ومراقبة تأكيدات الوسطاء عبر صناديق بريد مخصصة.",
    "tutorial.tour_step_title": "جولة تعريفية في النظام",
    "tutorial.tour_step_desc": "استكشف لوحة التحكم لمتابعة عمليات الحذف وإدارة سجلات أفراد العائلة.",
    "tutorial.skip": "تخطي الجولة",
    "tutorial.start_protecting": "ابدأ بحماية بياناتي",

    "i18n.manager_title": "إدارة اللغات والترجمة",
    "i18n.manager_desc": "إدارة اللغات المتاحة وتخصيص النصوص ومعاينة أماكن ظهور الكلمات في الواجهة.",
    "i18n.active_languages": "اللغات المفعّلة",
    "i18n.add_language": "إضافة لغة جديدة",
    "i18n.filter_by_location": "تصفية حسب موقع الشاشة",
    "i18n.source_english": "النص الإنجليزي الأصلي",
    "i18n.translated_text": "النص المترجم / التعديل المخصص",
    "i18n.where_it_appears": "مكان الظهور في الواجهة",
    "i18n.save_translations": "حفظ التعديلات المخصصة",
    "i18n.reset_defaults": "إعادة التعيين إلى الإعدادات الافتراضية",

    "ils.import_prompt_title": "هل تريد استيراد معلوماتك من بطاقة المكتبة؟",
    "ils.import_prompt_desc": "يتوفر في حسابك لدى المكتبة بيانات ({details}). هل ترغب في استيرادها للملء التلقائي أم إدخال بياناتك يدويًا؟",
    "ils.import_vault_desc": "يتوفر في حساب المكتبة بيانات ({details}). هل ترغب في استيرادها إلى خزينة الهوية أم إدخال بياناتك يدويًا؟",
    "ils.import_action_import": "استيراد معلوماتي",
    "ils.import_action_discard": "سأقوم بإدخالها يدويًا",
    "ils.import_success": "تم استيراد المعلومات بنجاح إلى خزينة الهوية.",
    "sip2.field_mapping_title": "مطابقة حقول المشتركين والموافقة",
    "sip2.field_mapping_desc": "استيراد المعلومات الديموغرافية من نظام المكتبة إلى حسابات المشتركين.",
    "sip2.patron_choice_title": "استيراد باختيار المشترك (خيار الموافقة)",
    "sip2.patron_choice_desc": "عند التفعيل، يختار المشتركون 'استيراد معلوماتي' أو 'سأقوم بإدخالها يدويًا' بعد تسجيل الدخول. تظل الحقول غير الإلزامية فارغة حتى يختار المشترك.",
    "sip2.consent_required": "الموافقة مطلوبة",
    "sip2.auto_import_all": "استيراد تلقائي للكل",
    "sip2.forced_fields_label": "الحقول الإلزامية (مفصولة بفواصل، مثل library, name)",
    "sip2.forced_fields_desc": "تُستورد الحقول المذكورة هنا تلقائيًا عند تسجيل الدخول. وتظل بقية الحقول اختيارية للمشترك.",
    "a11y.title": "إعدادات إمكانية الوصول",
    "a11y.high_contrast": "وضع التباين العالي (WCAG 2.2 AAA)",
    "a11y.high_contrast_desc": "تحسين تباين النص والحدود لتجاوز نسبة 7:1 لضعاف البصر.",
    "a11y.large_text": "نص كبير وحجم عناصر موسع",
    "a11y.large_text_desc": "تكبير الخط وعناصر النقر إلى 44×44 بكسل على الأقل لتسهيل الحركة.",
    "a11y.reduced_motion": "تقليل الحركة",
    "a11y.reduced_motion_desc": "تعطيل الرسوم المتحركة والانتقالات والمؤشرات النابضة.",
    "a11y.skip_to_content": "الانتقال إلى المحتوى الرئيسي",
    "nav.breadcrumbs": "مسار التنقل",
    "tutorial.a11y_section_title": "خيارات المظهر وإمكانية الوصول",
    "tutorial.a11y_section_desc": "تخصيص سمة الألوان والتباين العالي وحجم الخط لتناسب احتياجاتك.",
    "a11y.theme": "سمة الألوان",
    "a11y.theme_light": "فاتح",
    "a11y.theme_gray": "رمادي محايد",
    "a11y.theme_dark": "داكن",
    "a11y.theme_system": "النظام (تلقائي)",
    "a11y.font_size": "حجم الخط وتكبير النصوص",
    "a11y.font_preview_label": "معاينة مباشرة",
    "a11y.font_preview_sample": "يعرض هذا النص حجم الخط المحدد في الوقت الفعلي. تتكيف جميع الجداول والنماذج والقوائم بشكل متناسب.",
    "a11y.contrast_checkbox_desc": "يفرض أعلى تباين (21:1) متكيف مع السمة المحددة. تعرض السمة الفاتحة نصوصًا سوداء على خلفية بيضاء، بينما تعرض السمة الداكنة نصوصًا بيضاء ساطعة على خلفية سوداء.",
    "a11y.dyslexic_font": "خط ملائم لعسر القراءة (OpenDyslexic)",
    "a11y.dyslexic_font_desc": "تغيير خط المنصة إلى OpenDyslexic بقواعد ثقيلة لتحسين تدفق القراءة ومنع التشويش.",
    "a11y.dyslexic_font_short": "خط عسر القراءة",
}

# Built-in French translations
BUILTIN_FRENCH = {
    "nav.dashboard": "Tableau de bord",
    "nav.requests": "Demandes de suppression",
    "nav.vault": "Coffre-fort d'identité",
    "nav.family": "Membres de la famille",
    "nav.brokers": "Courtiers de données",
    "nav.settings": "Paramètres",
    "nav.translations": "Traductions",
    "nav.plugins": "Extensions",
    "nav.logout": "Déconnexion",
    "nav.welcome_tour": "Visite guidée",
    "nav.language": "Langue",

    "common.save": "Enregistrer",
    "common.cancel": "Annuler",
    "common.delete": "Supprimer",
    "common.edit": "Modifier",
    "common.loading": "Chargement...",
    "common.success": "Succès",
    "common.error": "Erreur",
    "common.next": "Suivant",
    "common.back": "Retour",
    "common.finish": "Terminer",
    "common.search": "Rechercher...",
    "common.enabled": "Activé",
    "common.disabled": "Désactivé",

    "dashboard.title": "Aperçu de la protection de la vie privée",
    "dashboard.subtitle": "Surveillance et purge des dossiers personnels chez les courtiers de données.",
    "dashboard.total_brokers": "Courtiers surveillés",
    "dashboard.confirmed_removals": "Suppressions confirmées",
    "dashboard.pending_requests": "En cours",
    "dashboard.protection_score": "Couverture de protection",
    "dashboard.start_optout_all": "Lancer les suppressions automatiques",

    "tutorial.welcome_title": "Bienvenue sur OpenOptOut",
    "tutorial.welcome_desc": "Prenons un moment pour personnaliser votre expérience et configurer vos protections de confidentialité.",
    "tutorial.lang_step_title": "Choisissez votre langue préférée",
    "tutorial.lang_step_desc": "Sélectionnez votre langue ci-dessous. L'interface s'adaptera immédiatement.",
    "tutorial.pii_step_title": "Protégez votre identité",
    "tutorial.pii_step_desc": "Indiquez votre nom et votre ville pour que les agents puissent trouver et supprimer vos fiches.",
    "tutorial.skip": "Passer le tutoriel",
    "tutorial.start_protecting": "Commencer à protéger mes données",

    "ils.import_prompt_title": "Importer les détails de votre carte de bibliothèque ?",
    "ils.import_prompt_desc": "Votre compte de bibliothèque contient des informations disponibles ({details}). Souhaitez-vous les importer pour préremplir le formulaire ou saisir vos données manuellement ?",
    "ils.import_vault_desc": "Votre compte de bibliothèque contient des informations disponibles ({details}). Souhaitez-vous les importer dans votre coffre-fort d'identité ou les saisir manuellement ?",
    "ils.import_action_import": "Importer mes informations",
    "ils.import_action_discard": "Je préfère les saisir moi-même",
    "ils.import_success": "Informations importées dans le coffre-fort d'identité.",
    "sip2.field_mapping_title": "Mappage des Champs Usagers et Consentement",
    "sip2.field_mapping_desc": "Importer les données démographiques du SIGB dans les comptes usagers.",
    "sip2.patron_choice_title": "Importation Pilotée par l'Usager (Consentement)",
    "sip2.patron_choice_desc": "Lorsque cette option est activée, les usagers choisissent 'Importer mes informations' ou 'Je préfère les saisir moi-même' après la connexion. Les champs non obligatoires restent vides sans action de leur part.",
    "sip2.consent_required": "Consentement Requis",
    "sip2.auto_import_all": "Importation Automatique Complète",
    "sip2.forced_fields_label": "Champs Obligatoires (séparés par des virgules, ex: library, name)",
    "sip2.forced_fields_desc": "Les champs indiqués ici sont automatiquement importés lors de la connexion. Les autres champs sont soumis au choix de l'usager.",
    "a11y.title": "Paramètres d'accessibilité",
    "a11y.high_contrast": "Mode Contraste Élevé (WCAG 2.2 AAA)",
    "a11y.high_contrast_desc": "Améliore le contraste du texte et des bordures pour dépasser le ratio de 7:1.",
    "a11y.large_text": "Grand Texte et Cibles Élargies",
    "a11y.large_text_desc": "Augmente la taille de police et les zones tactiles à 44x44px minimum.",
    "a11y.reduced_motion": "Mouvement Réduit",
    "a11y.reduced_motion_desc": "Désactive les animations, transitions et clignotements.",
    "a11y.skip_to_content": "Passer au contenu principal",
    "nav.breadcrumbs": "Fil d'Ariane",
    "tutorial.a11y_section_title": "Options de Thème et d'Accessibilité",
    "tutorial.a11y_section_desc": "Personnalisez le thème de couleur, le contraste élevé et la taille du texte selon vos besoins.",
    "a11y.theme": "Thème de Couleur",
    "a11y.theme_light": "Clair",
    "a11y.theme_gray": "Gris Neutre",
    "a11y.theme_dark": "Sombre",
    "a11y.theme_system": "Système (Automatique)",
    "a11y.font_size": "Taille de Police et Mise à l'Échelle",
    "a11y.font_preview_label": "Aperçu en Direct",
    "a11y.font_preview_sample": "Ce texte donne un aperçu en temps réel de votre taille de police. Les tableaux, formulaires et menus s'adaptent proportionnellement.",
    "a11y.contrast_checkbox_desc": "Applique un contraste maximal (21:1) adapté au thème choisi. Le thème clair affiche du noir pur sur fond blanc ; le thème sombre affiche du blanc pur sur fond noir.",
    "a11y.dyslexic_font": "Police adaptée à la dyslexie (OpenDyslexic)",
    "a11y.dyslexic_font_desc": "Remplace la typographie par OpenDyslexic avec une assise renforcée pour améliorer la fluidité de lecture.",
    "a11y.dyslexic_font_short": "Police Dyslexie",
}

# Built-in Pirate translations (Ahoy, matey!)
BUILTIN_PIRATE = {
    # Navigation & Shell
    "nav.dashboard": "Captain's Quarters",
    "nav.requests": "Broadside Demands",
    "nav.vault": "Treasure Chest",
    "nav.family": "Shipmates & Crew",
    "nav.brokers": "Data Scallywags",
    "nav.settings": "Ship's Rigging",
    "nav.translations": "Parley Tongues",
    "nav.plugins": "Cannon Upgrades",
    "nav.logout": "Abandon Ship",
    "nav.welcome_tour": "Maiden Voyage",
    "nav.language": "Pirate Tongue",

    # Common UI Controls
    "common.save": "Stash It!",
    "common.cancel": "Belay That!",
    "common.delete": "Send to Davy Jones",
    "common.edit": "Scrape & Refit",
    "common.loading": "Weighin' Anchor...",
    "common.success": "Shiver Me Timbers!",
    "common.error": "Blimey! Foul Waters!",
    "common.next": "Aye, Onward!",
    "common.back": "Heave Ho, Back!",
    "common.finish": "Drop Anchor!",
    "common.search": "Scour the Horizon...",
    "common.enabled": "Hoist High",
    "common.disabled": "Struck Down",

    # Dashboard Screen
    "dashboard.title": "Pirate Privacy Lookout",
    "dashboard.subtitle": "Trackin' and scuttlin' yer personal charts across greedy data scallywags.",
    "dashboard.total_brokers": "Spotted Scallywags",
    "dashboard.confirmed_removals": "Scuttled Records",
    "dashboard.pending_requests": "Cannons Firin'",
    "dashboard.protection_score": "Hull Armor",
    "dashboard.start_optout_all": "Fire Full Broadside!",

    # Identity Vault Screen
    "vault.title": "Identity Treasure Chest",
    "vault.description": "Yer secret marks and parchment below be guarded under lock and key, only used to scuttle landlubbers' records.",
    "vault.add_name": "Add Pirate Moniker",
    "vault.add_address": "Mark Port of Call",
    "vault.add_phone": "Add Carrier Gull",
    "vault.add_email": "Add Message Bottle",

    # Onboarding / Welcome Tutorial Modal
    "tutorial.welcome_title": "Ahoy! Welcome aboard OpenOptOut",
    "tutorial.welcome_desc": "Avast ye! Let's rig yer ship and batten down the hatches to guard yer booty.",
    "tutorial.lang_step_title": "Pick Yer Ship's Tongue",
    "tutorial.lang_step_desc": "Select how ye parley. The flags and compass will adapt right quick!",
    "tutorial.pii_step_title": "Armour Yer Identity",
    "tutorial.pii_step_desc": "Give us yer pirate name and home port so our deckhands can hunt down yer stolen manifests.",
    "tutorial.email_step_title": "Parley Dispatches",
    "tutorial.email_step_desc": "OpenOptOut fires broadside missives from private bottles and watches the scallywags' surrender notes.",
    "tutorial.tour_step_title": "Rigging Inspection & Ship's Tour",
    "tutorial.tour_step_desc": "Scour the captain's deck to view scuttled charts, rally yer crew, and inspect scallywags.",
    "tutorial.skip": "Set Sail Without Map",
    "tutorial.start_protecting": "Commence Plundering Data!",

    # Translation Manager Screen
    "i18n.manager_title": "Tongues & Sea Lore Quarters",
    "i18n.manager_desc": "Chart available languages, tweak yer pirate slang, and spy where each scroll appears.",
    "i18n.active_languages": "Hoisted Flags",
    "i18n.add_language": "Hail New Language",
    "i18n.filter_by_location": "Spy by Ship Deck",
    "i18n.source_english": "King's English",
    "i18n.translated_text": "Pirate Parchment",
    "i18n.where_it_appears": "Deck Location",
    "i18n.save_translations": "Stash Yer Slang",
    "i18n.reset_defaults": "Return to Navy Charts",

    # Patron Demographics & ILS Import
    "ils.import_prompt_title": "Plunder details from yer Library scroll?",
    "ils.import_prompt_desc": "Yer harbor library holds parchment on ye ({details}). Shall we haul 'em aboard to rig yer profile, or will ye scribe 'em by hand?",
    "ils.import_vault_desc": "Yer harbor library holds parchment on ye ({details}). Shall we haul 'em into yer Treasure Chest, or will ye scribe 'em with yer own quill?",
    "ils.import_action_import": "Aye, Plunder Me Scroll!",
    "ils.import_action_discard": "Nay, I'll Quill It Meself",
    "ils.import_success": "Booty hauled into the Identity Treasure Chest!",
    "sip2.field_mapping_title": "Library Scroll Mapping & Parley Consent",
    "sip2.field_mapping_desc": "Haul patron charts from the harbor ILS into crew accounts.",
    "sip2.patron_choice_title": "Crew-Driven Plunder (Parley Choice)",
    "sip2.patron_choice_desc": "When hoisted, sailors click 'Aye, Plunder Me Scroll!' or 'Nay, I'll Quill It Meself'. Unpressed scrolls remain blank.",
    "sip2.consent_required": "Parley Consent Required",
    "sip2.auto_import_all": "Full Broadside Auto-Plunder",
    "sip2.forced_fields_label": "Ironclad Fields (e.g. library, name)",
    "sip2.forced_fields_desc": "Scrolls listed here are hauled aboard automatically upon boardin'. Others remain crew-driven.",

    # Accessibility & Assistive Navigation (WCAG 2.2 AAA)
    "a11y.title": "Ship's Eyeglass & Helm Rigging",
    "a11y.high_contrast": "High Contrast Beacon (WCAG 2.2 AAA)",
    "a11y.high_contrast_desc": "Strikes blinding lanternlight across charts for sharp sight.",
    "a11y.large_text": "Mighty Runes & Broad Pegs",
    "a11y.large_text_desc": "Heaves up the lettering and expands helm levers to 44px.",
    "a11y.reduced_motion": "Calm Waters",
    "a11y.reduced_motion_desc": "Stills the rolling waves and calms rockin' animations.",
    "a11y.skip_to_content": "Leap straight onto the Main Deck",
    "nav.breadcrumbs": "Sea Trail",
    "tutorial.a11y_section_title": "Ship's Colors & Eyeglass Rigging",
    "tutorial.a11y_section_desc": "Rig yer color flags, high contrast lanterns, and mighty lettering to suit yer voyage.",
    "a11y.theme": "Ship's Colors",
    "a11y.theme_light": "Daylight Sun",
    "a11y.theme_gray": "Foggy Sea",
    "a11y.theme_dark": "Midnight Tide",
    "a11y.theme_system": "Sea Sky (Auto)",
    "a11y.font_size": "Rune Sizing & Lettering",
    "a11y.font_preview_label": "Spyglass Preview",
    "a11y.font_preview_sample": "This parchment previews yer chosen lettering size right quick. All manifests, logs, and sea charts will heave up proportionally.",
    "a11y.contrast_checkbox_desc": "Strikes maximum blinding contrast (21:1) fittin' yer chosen sea flags. Daylight turns parchment stark white with ink-black runes; midnight turns it pitch-black with gold lanternlight.",
    "a11y.dyslexic_font": "OpenDyslexic Sea Runes",
    "a11y.dyslexic_font_desc": "Heaves heavy-keeled anchor runes across all ship manifests so words stop tossin' and turnin' in rough seas.",
    "a11y.dyslexic_font_short": "Anchor Runes",
}

BUILTIN_TRANSLATIONS = {
    "es": BUILTIN_SPANISH,
    "ar": BUILTIN_ARABIC,
    "fr": BUILTIN_FRENCH,
    "pirate": BUILTIN_PIRATE,
}


def is_rtl_language(lang_code: str) -> bool:
    """Returns True if the language code represents a Right-to-Left script."""
    base = (lang_code or "").lower().split("-")[0].strip()
    return base in RTL_LANGUAGES


def get_i18n_settings() -> Dict[str, Any]:
    """Retrieve i18n configuration from settings store."""
    settings = settings_store.load_settings()
    i18n_cfg = settings.get("i18n", {})
    return {
        "enabled_languages": i18n_cfg.get("enabled_languages", ["en", "es", "ar", "fr", "pirate"]),
        "default_language": i18n_cfg.get("default_language", "en"),
        "custom_languages": i18n_cfg.get("custom_languages", {}),
        "custom_translations": i18n_cfg.get("custom_translations", {}),
    }


def save_i18n_settings(cfg: Dict[str, Any]) -> None:
    """Persist i18n configuration to settings store."""
    settings = settings_store.load_settings()
    settings["i18n"] = cfg
    with open(settings_store.SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def scan_language_plugins() -> Dict[str, Dict[str, Any]]:
    """
    Scan <plugins_root>/languages/ for installed language pack plugins.
    Returns { lang_code: { manifest, messages } }.
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
    root = layout.plugins_root()
    lang_dir = os.path.join(root, "languages")
    found_packs = {}
    if not os.path.isdir(lang_dir):
        return found_packs

    for entry in os.listdir(lang_dir):
        pkg_path = os.path.join(lang_dir, entry)
        if not os.path.isdir(pkg_path) or entry.startswith("."):
            continue
        manifest_file = os.path.join(pkg_path, "manifest.json")
        if not os.path.isfile(manifest_file):
            continue
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            code = manifest.get("language_code") or manifest.get("id", "").replace("lang-", "").replace("lang_", "")
            if not code:
                continue

            # Look for messages.json or translations.json
            messages = {}
            for msg_name in ("messages.json", "translations.json"):
                msg_path = os.path.join(pkg_path, msg_name)
                if os.path.isfile(msg_path):
                    with open(msg_path, "r", encoding="utf-8") as mf:
                        messages = json.load(mf)
                    break

            found_packs[code] = {
                "id": manifest.get("id", entry),
                "name": manifest.get("name", code),
                "author": manifest.get("author", ""),
                "version": manifest.get("version", "1.0"),
                "is_rtl": bool(manifest.get("is_rtl", is_rtl_language(code))),
                "messages": messages,
            }
        except Exception as e:
            log.warning("Failed scanning language pack at %s: %s", pkg_path, e)

    return found_packs


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

    # 2. Installed language packs
    for code, pack in plugin_packs.items():
        if code in catalog:
            catalog[code]["source"] = "plugin"
            catalog[code]["name"] = pack["name"]
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
    """Returns the master UI dictionary with locations and descriptions."""
    return MASTER_DICTIONARY


def get_translations_for_locale(locale: str) -> Dict[str, str]:
    """
    Resolve complete translation dictionary for a given language code.
    Resolution order (highest precedence wins):
      1. Default English text from MASTER_DICTIONARY
      2. Built-in translations (e.g. Spanish, Arabic, French)
      3. Installed language pack add-on messages (<plugins_root>/languages/<id>/)
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

    # 2. Built-in translations
    if code in BUILTIN_TRANSLATIONS:
        result.update(BUILTIN_TRANSLATIONS[code])

    # 3. Language pack add-on messages
    plugin_packs = scan_language_plugins()
    if code in plugin_packs and plugin_packs[code]["messages"]:
        result.update(plugin_packs[code]["messages"])

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
