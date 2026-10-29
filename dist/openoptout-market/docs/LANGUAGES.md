# Authoring Language Packs for OpenOptOut

Language packs provide regional translations and layout adjustments for OpenOptOut. They are data-only plugins containing structured JSON dictionaries without executable code.

---

## 1. Directory Structure

A language pack must follow this directory layout:

```text
lang-<code>/
├── manifest.json
├── texts.json               (every UI phrase, keyed by its English text)
├── messages.json            (categorized navigation and status terms)
├── README.md
└── plugins/                 (optional: translations of specific broker plugin phrases)
    └── fastpeoplesearch.json
```

---

## 2. Manifest Schema (`manifest.json`)

```json
{
  "id": "lang-es",
  "name": "Spanish Language Pack (Español)",
  "version": "1.0.0",
  "author": "OpenOptOut Community",
  "type": "languages",
  "description": "Complete Spanish translation for OpenOptOut interface."
}
```

Key manifest rules:
- `id`: Must begin with `lang-` followed by the ISO 639-1 language code (e.g., `lang-fr`, `lang-de`, `lang-ar`).
- `type`: Must be `"languages"`.

---

## 3. String Translation Files

### `texts.json`
Contains phrase-by-phrase translations for every user interface string, keyed by the original English string:

```json
{
  "Dashboard": "Panel de control",
  "Removal Requests": "Solicitudes de eliminación",
  "Add Family Member": "Agregar miembro de la familia",
  "Save Changes": "Guardar cambios"
}
```

### `messages.json`
Contains categorized regional strings and layout direction:

```json
{
  "locale": "es",
  "locale_name": "Español",
  "direction": "ltr",
  "messages": {
    "nav": {
      "dashboard": "Panel",
      "requests": "Solicitudes",
      "settings": "Configuración"
    }
  }
}
```

---

## 4. Right-to-Left (RTL) Layout Standards

When translating into Right-to-Left languages (Arabic, Hebrew, Persian, Urdu, etc.):
1. Set `"direction": "rtl"` in `messages.json`.
2. The UI automatically activates `html[dir="rtl"]`.
3. Directional navigation icons (arrows, chevrons, undo/redo) automatically mirror using CSS `scale: -1 1`.
4. Technical data (code blocks, email addresses, phone digits, and URLs) retain Left-to-Right orientation (`direction: ltr`).
