# Accessibility Statement and Conformance Guide

OpenOptOut is dedicated to ensuring digital privacy tools are universally accessible to everyone, including individuals with disabilities, neurodivergent users, and patrons using assistive technologies. As an open-source platform purpose-built for families and public institutions (such as libraries, credit unions, and educational organizations), digital accessibility is a core architectural requirement.

---

## Conformance Standards

OpenOptOut's user interface is designed and evaluated against the following standards:

- **Web Content Accessibility Guidelines (WCAG) 2.2**: Conforming to **Level AA** across all primary workflows, with targeted **Level AAA** enhancements implemented in contrast, target sizing, and motion safety.
- **Section 508 of the U.S. Rehabilitation Act**: Aligned with federal accessibility requirements for public sector and federally funded deployments.
- **EN 301 549**: Conforming to European accessibility standards for public procurement of ICT products and services.

---

## Core Accessibility Features

Starting in release `v0.10.0`, OpenOptOut includes a comprehensive accessibility architecture managed through the central Accessibility Provider (`frontend/src/context/AccessibilityContext.jsx`):

### 1. High-Contrast & Theme Controls
- **Standard Themes**: Support for Light, Gray (reduced glare), Dark, and automatic System OS sync (`prefers-color-scheme`).
- **High-Contrast Modes (WCAG 2.2 AAA)**: Dedicated high-contrast options (`.a11y-high-contrast-light` and `.a11y-high-contrast-dark`) enforcing text contrast ratios exceeding 7:1 for body copy and 4.5:1 for large text and interactive components.
- **Color Independence**: Status indicators (such as broker removal pending, submitted, confirmed, or failed) use distinct icons, patterns, and descriptive text badges in addition to color.

### 2. Typography and Scalable Text
- **Fluid Font Scaling**: Built-in text resizing controls scaling UI typography from 100% to 150% without clipping or overflowing layout containers (`--a11y-font-size`).
- **Reflow & Zoom**: Full support for browser zoom up to 200% and 400% without horizontal scrolling or loss of functionality (WCAG 1.4.4 and 1.4.10).
- **Legible Font Stacks**: System-native UI typography engineered for readability, clear letterform distinction, and adequate character spacing.
- **Dyslexia-Friendly Typography (OpenDyslexic)**: Users can switch to OpenDyslexic (`.a11y-dyslexic-font`), a specialized typeface designed to mitigate reading errors with heavy weighted bottoms, unique letter shaping, and wide apertures. Packaged locally via self-hosted assets to preserve strict air-gapped privacy.

### 3. Motion & Vestibular Safety
- **Reduced Motion Support**: Immediate respect for OS-level `prefers-reduced-motion` settings, plus an in-app toggle (`.a11y-reduced-motion`).
- **Disabling Non-Essential Animations**: Eliminates vestibular triggers, animated transitions, layout shifts, and looping spinners, replacing them with static state indicators.

### 4. Touch & Click Target Sizing (WCAG 2.2 AAA)
- **Enhanced Targets**: Enabling Enhanced Target Sizing (`.a11y-enhanced-targets`) expands interactive elements (buttons, inputs, checkboxes, table actions) to meet or exceed 44x44 CSS pixels.
- **Adequate Spacing**: Sufficient separation between adjacent interactive elements prevents accidental activation for users with motor tremors or limited precision.

### 5. Keyboard Navigation & Focus Management
- **Skip Link Navigation**: An accessible skip link (`SkipLink.jsx`) appears on initial keyboard focus (`Tab`), allowing users to bypass navigation sidebars and jump straight to main content.
- **Prominent Focus Indicators**: High-contrast, custom focus outlines (minimum 3px solid rings with high visual separation) guarantee keyboard position is always clear.
- **Logical Tab Order**: All interactive controls, forms, modal dialogs, and setup wizard steps follow an intuitive, predictable DOM reading order.
- **Modal Focus Traps**: Dialogs and popups trap focus appropriately while open, restore focus to the triggering element upon close, and dismiss cleanly with the `Escape` key.

### 6. Screen Readers & Assistive Technologies
- **Semantic Structure**: Proper HTML5 landmarks (`<nav>`, `<header>`, `<main>`, `<aside>`, `<footer>`) and strict heading hierarchies (`h1` through `h4`) allow efficient screen reader navigation.
- **Live Announcements**: Critical notifications, broker submission progress, and error alerts are announced to assistive technology using `aria-live="polite"` regions.
- **Descriptive ARIA Attributes**: All icon-only buttons, disclosure widgets, form controls, and multi-step progress indicators include descriptive `aria-label`, `aria-describedby`, and `aria-expanded` attributes.
- **Accessible Breadcrumbs**: Dynamic breadcrumb trails (`Breadcrumbs.jsx`) provide contextual location awareness with structured navigation landmarks and `aria-current="page"` markup.

### 7. Persistent User Preferences
- **Cross-Device Persistence**: Accessibility settings are stored locally in `localStorage` for instant client-side rendering and synced to the authenticated user account profile via `/i18n/user/preference`.

---

## WCAG 2.2 Conformance Matrix

| Principle | Guideline | Status | Notes |
|---|---|---|---|
| **Perceivable** | 1.1 Text Alternatives | Conforms (AA) | All informative imagery and SVG icons provide descriptive alt text or ARIA labels; decorative elements use `aria-hidden="true"`. |
| | 1.3 Adaptable | Conforms (AA) | Meaningful sequence, semantic landmarks, and form field autocomplete attributes are maintained throughout. |
| | 1.4 Distinguishable | Conforms (AAA) | High-contrast modes exceed 7:1 contrast; font scaling up to 150% is supported; text spacing and reflow up to 400% zoom are verified. |
| **Operable** | 2.1 Keyboard Accessible | Conforms (AA) | All actions are fully executable via keyboard alone; no keyboard traps exist. |
| | 2.4 Navigable | Conforms (AAA) | Skip-to-content links provided; visible focus rings; hierarchical page titles and breadcrumbs. |
| | 2.5 Input Modalities | Conforms (AAA) | Enhanced target sizing option enforces 44x44px minimum touch targets. |
| **Understandable**| 3.1 Readable | Conforms (AA) | Programmatic language tags (`lang` attribute) are updated dynamically with internationalization changes. |
| | 3.2 Predictable | Conforms (AA) | UI components behave consistently; theme and setting changes apply predictably without unexpected context switches. |
| | 3.3 Input Assistance | Conforms (AA) | Accessible error identification, inline validation cues, and descriptive input error messages. |
| **Robust** | 4.1 Compatible | Conforms (AA) | Valid HTML markup, standard ARIA roles, and verified compatibility with modern assistive technologies. |

---

## Assistive Technology Testing

OpenOptOut is evaluated using a combination of automated scans and manual testing:

- **Automated Scanning**: Continuous audits via `axe-core`, Lighthouse, and Playwright automated accessibility probes.
- **Screen Readers**: Tested with Apple VoiceOver (macOS / iOS) and NVDA (Windows) across Chromium and Firefox browsers.
- **Keyboard-Only**: Rigorous manual verification of all workflows (registration, onboarding wizard, vault management, broker opt-out triggering, and settings configuration) without a pointer device.

---

## Feedback and Reporting

We actively welcome feedback on the accessibility of OpenOptOut. If you encounter an accessibility barrier or have a suggestion to improve assistive technology support:

- **GitHub Issues**: Open an issue on our [GitHub repository](https://github.com/rlnunez/OpenOptOut/issues) with the `a11y` or `accessibility` label.
- **Maintainer Contact**: Email Robert Nunez at [nunez.robert@gmail.com](mailto:nunez.robert@gmail.com) with the subject line `Accessibility Feedback: OpenOptOut`.

Please include the page or component where the issue occurred, the assistive technology or browser used, and a brief description of the encountered barrier. We treat accessibility bugs with high priority and commit to prompt review and resolution.
