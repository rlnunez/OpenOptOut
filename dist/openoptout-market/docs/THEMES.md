# Authoring Accessible Themes for OpenOptOut

OpenOptOut supports custom themes that adjust colors, typography, and contrast across the application. Themes are data-only plugins: they contain design tokens, optional CSS stylesheets, and brand assets without executable code.

---

## 1. Directory Structure

A theme plugin must follow this directory layout:

```text
my-theme/
├── manifest.json
├── theme.json
├── styles.css        (optional: custom component overrides)
├── README.md
└── assets/           (optional: logo, favicon, font assets)
    ├── logo.svg
    └── favicon.ico
```

---

## 2. Manifest Schema (`manifest.json`)

The manifest identifies the theme and declares its accessibility rating:

```json
{
  "id": "civic-high-contrast",
  "name": "Civic High Contrast Theme",
  "version": "1.0.0",
  "author": "Municipal Privacy Consortium",
  "type": "themes",
  "description": "High-contrast theme meeting WCAG 2.2 Level AAA contrast requirements.",
  "wcag_level": "AAA"
}
```

Key manifest fields:
- `id`: Unique slug matching the repository name.
- `type`: Must be `"themes"`.
- `wcag_level`: Set to `"AA"` or `"AAA"` based on verified contrast ratios.

---

## 3. Design Tokens (`theme.json`)

`theme.json` defines color palettes and typography tokens consumed by the frontend engine:

```json
{
  "name": "Civic High Contrast",
  "mode": "dark",
  "colors": {
    "background": "#000000",
    "surface": "#0a0a0a",
    "surface_secondary": "#141414",
    "border": "#ffff00",
    "text_primary": "#ffffff",
    "text_secondary": "#ffff00",
    "text_muted": "#e0e0e0",
    "accent": "#ffff00",
    "accent_hover": "#e6e600",
    "status_success": "#00ff66",
    "status_warning": "#ffcc00",
    "status_danger": "#ff3333"
  },
  "typography": {
    "font_family_sans": "Inter, system-ui, sans-serif",
    "font_family_mono": "JetBrains Mono, monospace",
    "border_radius": "0.25rem"
  },
  "assets": {
    "logo_path": "assets/logo.svg",
    "favicon_path": "assets/favicon.ico"
  }
}
```

---

## 4. CSS Selectors and Component Mapping

When OpenOptOut activates a theme, it injects the theme class onto the root `<html>` element: `html.theme-<id>`.

To target specific components in your `styles.css`, use the following standard UI selectors:

### Base Elements
- `html.theme-<id> body`: Global page background and default font color.
- `html.theme-<id> aside`: Navigation sidebar background and border.
- `html.theme-<id> header`: Top navigation bar.

### Surface and Card Containers
- `html.theme-<id> .bg-slate-950`: Deep base background.
- `html.theme-<id> .bg-slate-900`, `html.theme-<id> .bg-slate-900\/50`: Primary content panels, cards, and modal dialogs.
- `html.theme-<id> .bg-slate-800`, `html.theme-<id> .bg-slate-950\/60`: Table header rows, interactive cards, and nested containers.

### Borders and Dividers
- `html.theme-<id> .border-slate-800`, `html.theme-<id> .border-slate-700`: Structural panel borders and card dividers.

### Typography
- `html.theme-<id> .text-white`, `html.theme-<id> .text-slate-100`: Primary headings and critical data values.
- `html.theme-<id> .text-slate-300`, `html.theme-<id> .text-slate-400`: Body copy and form labels.
- `html.theme-<id> .text-slate-500`, `html.theme-<id> .text-slate-600`: Helper captions, timestamps, and metadata.

### Form Inputs
- `html.theme-<id> input`, `html.theme-<id> select`, `html.theme-<id> textarea`: Form controls.
- `html.theme-<id> input:focus-visible`: Active keyboard focus outline.

### Action Buttons
- `html.theme-<id> .bg-shield-600`, `html.theme-<id> .bg-shield-700`: Primary call-to-action buttons.
- `html.theme-<id> .bg-red-600`, `html.theme-<id> .bg-red-700`: Destructive removal and revocation buttons.

---

## 5. Accessibility Guidelines (WCAG 2.2 AA and AAA)

OpenOptOut enforces rigorous accessibility standards to serve patrons of public libraries, universities, and government agencies. Themes should target WCAG 2.2 Level AA at a minimum, and ideally Level AAA.

### Contrast Requirements

| Content Type | WCAG 2.2 Level AA | WCAG 2.2 Level AAA |
|---|---|---|
| Normal Text (< 18pt or < 14pt bold) | Minimum 4.5:1 ratio | Minimum 7.0:1 ratio |
| Large Text (>= 18pt or >= 14pt bold) | Minimum 3.0:1 ratio | Minimum 4.5:1 ratio |
| User Interface Components & Borders | Minimum 3.0:1 ratio | Minimum 4.5:1 ratio |

### Relative Luminance and Contrast Formula
Luminance is calculated using the standard IEC 61966-2-1 sRGB formula:
- Contrast Ratio = `(L1 + 0.05) / (L2 + 0.05)`
- `L1` is the relative luminance of the lighter color.
- `L2` is the relative luminance of the darker color.

### Critical Accessibility Principles

1. **Do Not Rely on Color Alone (SC 1.4.1):**
   Status indicators (such as removal success or pending states) must pair color changes with text labels, distinct icons, or patterned borders.
2. **Focus Visible and Enhanced (SC 2.4.7, 2.4.11, 2.4.12):**
   Keyboard focus indicators must never be hidden (`outline: none` is prohibited without a replacement). Provide a distinct focus ring with at least 3:1 contrast against both the component and the adjacent background:
   ```css
   html.theme-<id> :focus-visible {
     outline: 2px solid #ffff00 !important;
     outline-offset: 2px !important;
   }
   ```
3. **Respect Reduced Motion (SC 2.3.3):**
   All CSS transitions and animations must be disabled when the user has requested reduced motion:
   ```css
   @media (prefers-reduced-motion: reduce) {
     html.theme-<id> * {
       animation-duration: 0.01ms !important;
       transition-duration: 0.01ms !important;
     }
   }
   ```
4. **Target Size (SC 2.5.8):**
   Interactive touch targets must provide at least 24x24 CSS pixels of clickable area (44x44 CSS pixels for Level AAA).
5. **Right-to-Left (RTL) Layout:**
   Use logical CSS properties (`border-inline-start`, `margin-inline-end`) rather than physical properties (`border-left`, `margin-right`) so the theme renders correctly in Arabic, Hebrew, Urdu, and other RTL languages.
