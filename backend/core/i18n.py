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
    {"key": "tutorial.welcome_title", "default_text": "Welcome to PrivacyShield", "location": "Welcome Tutorial / Step 1", "description": "Main onboarding modal header"},
    {"key": "tutorial.welcome_desc", "default_text": "Let's take a moment to customize your experience and configure your privacy protections.", "location": "Welcome Tutorial / Step 1", "description": "Introduction to user setup walkthrough"},
    {"key": "tutorial.lang_step_title", "default_text": "Choose Your Preferred Language", "location": "Welcome Tutorial / Step 1", "description": "Step 1 title for language selection"},
    {"key": "tutorial.lang_step_desc", "default_text": "Select your language below. The interface, notifications, and layout will adapt immediately.", "location": "Welcome Tutorial / Step 1", "description": "Explanation of language options"},
    {"key": "tutorial.pii_step_title", "default_text": "Protect Your Identity", "location": "Welcome Tutorial / Step 2", "description": "Step 2 title for profile information"},
    {"key": "tutorial.pii_step_desc", "default_text": "Provide your name and city/state so automated agents can locate and scrub your listings.", "location": "Welcome Tutorial / Step 2", "description": "Why PII is collected"},
    {"key": "tutorial.email_step_title", "default_text": "Opt-Out Communications", "location": "Welcome Tutorial / Step 3", "description": "Step 3 title for email configuration"},
    {"key": "tutorial.email_step_desc", "default_text": "PrivacyShield dispatches removal requests using dedicated inboxes and monitors broker responses.", "location": "Welcome Tutorial / Step 3", "description": "Explanation of email handling"},
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

    "tutorial.welcome_title": "Bienvenido a PrivacyShield",
    "tutorial.welcome_desc": "Tomemos un momento para personalizar su experiencia y configurar sus protecciones de privacidad.",
    "tutorial.lang_step_title": "Elija su Idioma Preferido",
    "tutorial.lang_step_desc": "Seleccione su idioma a continuación. La interfaz, las notificaciones y el diseño se adaptarán de inmediato.",
    "tutorial.pii_step_title": "Proteja su Identidad",
    "tutorial.pii_step_desc": "Proporcione su nombre y ciudad/estado para que los agentes automatizados puedan localizar y eliminar sus listados.",
    "tutorial.email_step_title": "Comunicaciones de Exclusión",
    "tutorial.email_step_desc": "PrivacyShield envía solicitudes de eliminación utilizando buzones dedicados y monitorea las respuestas de los brokers.",
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

    "tutorial.welcome_title": "مرحبًا بك في PrivacyShield",
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

    "tutorial.welcome_title": "Bienvenue sur PrivacyShield",
    "tutorial.welcome_desc": "Prenons un moment pour personnaliser votre expérience et configurer vos protections de confidentialité.",
    "tutorial.lang_step_title": "Choisissez votre langue préférée",
    "tutorial.lang_step_desc": "Sélectionnez votre langue ci-dessous. L'interface s'adaptera immédiatement.",
    "tutorial.pii_step_title": "Protégez votre identité",
    "tutorial.pii_step_desc": "Indiquez votre nom et votre ville pour que les agents puissent trouver et supprimer vos fiches.",
    "tutorial.skip": "Passer le tutoriel",
    "tutorial.start_protecting": "Commencer à protéger mes données",
}

BUILTIN_TRANSLATIONS = {
    "es": BUILTIN_SPANISH,
    "ar": BUILTIN_ARABIC,
    "fr": BUILTIN_FRENCH,
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
        "enabled_languages": i18n_cfg.get("enabled_languages", ["en", "es", "ar", "fr"]),
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
