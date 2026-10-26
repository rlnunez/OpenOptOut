# OpenOptOut Accessibility Conformance Report
## VPAT® Version 2.5 (International Edition)
### WCAG 2.2 (Levels A, AA, AAA) • Revised Section 508 • EN 301 549 v3.2.1

**OpenOptOut** is a self-hosted, AGPL-3.0 privacy platform that removes individuals, families, and community members from commercial data broker directories. Digital accessibility is a non-negotiable architectural invariant: privacy protections must be universally usable by everyone, including individuals with visual, auditory, motor, cognitive, or speech disabilities, neurodivergent patrons, and users of assistive technologies.

This document serves as the formal **Accessibility Conformance Report (ACR)** using the Voluntary Product Accessibility Template (VPAT® Version 2.5 INT). It provides institutions—including public and academic libraries, universities, school districts, healthcare networks, municipal entities, and federal agencies—with a rigorous compliance crosswalk verifying where OpenOptOut conforms to and exceeds federal, European, and international procurement standards.

---

## Conformance Report Summary

| Attribute | Specification |
|---|---|
| **Product Name** | OpenOptOut |
| **Product Version** | v0.11.3 |
| **Report Date** | October 2026 |
| **Product Description** | Self-hosted web application and administrative portal for automated personal data removal, family profile management, and privacy rights enforcement. |
| **Contact Information** | Robert Nunez (`nunez.robert@gmail.com`) / GitHub Accessibility Tracker |
| **Applicable Standards** | • **W3C Web Content Accessibility Guidelines (WCAG) 2.2**: Conforming to **Level A** and **Level AA** across 100% of workflows, with extensive **Level AAA** conformance in contrast (21:1), target sizing (44x44px), timing, and typography.<br>• **Revised Section 508 of the U.S. Rehabilitation Act** (36 CFR Part 1194, Appendix A & C).<br>• **EN 301 549 v3.2.1** (European Standard for Public Procurement of ICT Products and Services). |
| **Evaluation Methods** | • **Automated Browser Scans**: axe-core 4.10 dual-round testing (Round 1: Regular Theme functional audit; Round 2: ADA/WCAG High-Contrast Dark Theme audit), Lighthouse accessibility audits, and Playwright automated end-to-end traversal.<br>• **Static AST Analysis**: Dedicated JSX linter (`frontend/scripts/check-a11y.mjs`) scanning 80 component files for ARIA attributes, semantic roles, and button labels.<br>• **Manual Assistive Technology Testing**: Apple VoiceOver (macOS Sonoma / iOS 17), NVDA (Windows 11) across Chromium and Firefox engines.<br>• **Keyboard-Only & Reflow Traversal**: 100% pointerless navigation, focus management verification, and browser zoom testing up to 400% at 1280px resolution. |
| **Hosting & Privacy Guarantee** | **100% Air-Gapped & Self-Hosted**: Zero third-party CDN dependencies, zero external tracking pixels, zero cloud font registries. All typefaces (Inter, JetBrains Mono, OpenDyslexic) and assets are bundled locally, satisfying strict institutional privacy and COPPA requirements. |

---

## Conformance Level Definitions

This report adheres to the standardized VPAT® reporting criteria:

- **Supports**: The functionality of the product has at least one method that meets the criterion without known defects or meets with equivalent facilitation.
- **Partially Supports**: Some functionality of the product does not meet the criterion (remediations documented).
- **Does Not Support**: The majority of product functionality does not meet the criterion.
- **Not Applicable**: The criterion is not relevant to the product (e.g., audio/video guidelines in a text-and-form application).
- **Exceeds**: The product meets the baseline Level A/AA or Section 508 requirement and additionally satisfies the more stringent Level AAA criterion.

---

## Architectural Accessibility Features

OpenOptOut implements a purpose-built, centralized accessibility framework (`frontend/src/context/AccessibilityContext.jsx`):

### 1. Dual Standard & ADA Compliant High-Contrast Themes
- **Paired High-Contrast Themes**: Every aesthetic theme has an accompanying WCAG 2.2 AAA compliant ADA mode:
  - **Dark ADA (`.theme-dark-ada`)**: Pitch-black void (`#000000`) with pure white text (`#ffffff`), 2px solid white element containment borders, and high-luminance amber/cyan accents reaching **21:1 contrast ratios** (far surpassing the 4.5:1 AA and 7:1 AAA thresholds).
  - **Light ADA (`.theme-light-ada`)**: Pure white canvas (`#ffffff`) with absolute black text (`#000000`), 2px black structural borders, and high-visibility `#0000ee` action accents.
  - **Space ADA (`.theme-space-ada`)**: High-luminance amber (`#ffb800`) on deep black with stark white headers and 2px high-visibility amber borders.
- **Color Independence**: Status badges (Pending, Submitted, Confirmed, Failed) utilize unique shapes, distinct icons, and explicit textual descriptions alongside color indicators.

### 2. Fluid Typography Scaling & OpenDyslexic Typeface
- **Scalable Font Slider**: Dynamic font scaling from 100% to 150% without line clipping, text truncation, or viewport breaking (`--a11y-font-size`).
- **OpenDyslexic Typeface (`.a11y-dyslexic-font`)**: Specialized, self-hosted dyslexia-friendly typeface featuring weighted bottoms, unique character silhouettes, and wide apertures.
- **Reflow & 400% Zoom**: Complete responsive reflow supporting up to 400% browser zoom without triggering horizontal scrollbars or losing interactive controls (WCAG 1.4.10).

### 3. Vestibular & Motion Safety
- **Reduced Motion Engine (`.a11y-reduced-motion`)**: Dynamically respects `prefers-reduced-motion: reduce` OS settings, with an independent in-app override. Suppresses non-essential transitions, spinning loaders, and animations to protect users with vestibular conditions.

### 4. Enhanced Target Sizing (WCAG 2.2 AAA)
- **Large Touch Targets (`.a11y-enhanced-targets`)**: Expands buttons, form inputs, checkboxes, table pagination, and toggles to meet or exceed **44x44 CSS pixels** with generous spacing to eliminate accidental clicks.

### 5. Keyboard Navigation & Focus Traps
- **Skip Navigation Link**: High-contrast skip-to-content mechanism (`SkipLink.jsx`) appears on initial keyboard `Tab` press.
- **High-Visibility Focus Rings**: 3px solid, high-contrast outlines with explicit offsets ensuring focus position is immediately visible on any background.
- **Predictable DOM Tab Order & Modal Focus Traps**: Modals (`Modal.jsx`) trap keyboard focus securely, prevent background scrolling, restore focus to triggering elements upon dismissal, and close on `Escape`.

### 6. Bidirectional & Right-to-Left (RTL) Layouts
- **Logical CSS Properties**: Built completely with CSS logical start/end properties (`ms-`, `pe-`, `start-`, `text-start`, `border-s-`), enabling automated, native layout flipping for right-to-left languages (Arabic, Urdu).
- **Directional Icon Mirroring**: Directional arrows and navigation iconography flip automatically in RTL viewports.

### 7. Universal Form Label Association
- **Automated Field Control Labeling (`Field.jsx`)**: Core form field component recursively inspects nested controls, generating and linking programmatic `htmlFor`/`id` bindings and fallback `aria-label`s, preventing unlabelled inputs across the platform.

---

## Detailed Standards Crosswalk

### Table 1: WCAG 2.2 Conformance & Crosswalk to Section 508 & EN 301 549

| Success Criterion | WCAG Level | Section 508 Reference | EN 301 549 Reference | Conformance Level | Remarks and Explanations |
|---|---|---|---|---|---|
| **Principle 1: Perceivable** | | | | | |
| **1.1.1 Non-text Content** | Level A | 501.1 (Web), 504.2 | 9.1.1.1 | **Supports** | All informative SVG icons and imagery include descriptive `aria-label` or `alt` text. Purely decorative elements carry `aria-hidden="true"`. |
| **1.2.1 Audio-only and Video-only** | Level A | 501.1, 504.2 | 9.1.2.1 | **Not Applicable** | The application contains no prerecorded audio or video media. |
| **1.2.2 Captions (Prerecorded)** | Level A | 501.1, 504.2 | 9.1.2.2 | **Not Applicable** | The application contains no video content requiring captions. |
| **1.2.3 Audio Description / Alternative** | Level A | 501.1, 504.2 | 9.1.2.3 | **Not Applicable** | No multimedia video tracks present. |
| **1.2.4 Captions (Live)** | Level AA | 501.1, 504.2 | 9.1.2.4 | **Not Applicable** | No live audio/video streams present. |
| **1.2.5 Audio Description (Prerecorded)** | Level AA | 501.1, 504.2 | 9.1.2.5 | **Not Applicable** | No video tracks present. |
| **1.3.1 Info and Relationships** | Level A | 501.1, 504.2 | 9.1.3.1 | **Supports** | Semantic HTML5 structure (`<main>`, `<nav>`, `<aside>`, `<header>`, `<table>`, `<th>`) throughout. `<Field>` component guarantees programmatic labels for 100% of form inputs. |
| **1.3.2 Meaningful Sequence** | Level A | 501.1, 504.2 | 9.1.3.2 | **Supports** | DOM order matches visual reading sequence; flex and grid layouts do not disrupt logical traversal. |
| **1.3.3 Sensory Characteristics** | Level A | 501.1, 504.2 | 9.1.3.3 | **Supports** | Instructions never rely solely on shape, size, color, or spatial orientation. |
| **1.3.4 Orientation** | Level AA | 501.1, 504.2 | 9.1.3.4 | **Supports** | Display is not locked to portrait or landscape; fully functional across device orientations. |
| **1.3.5 Identify Input Purpose** | Level AA | 501.1, 504.2 | 9.1.3.5 | **Supports** | Member profile and opt-out inputs utilize standard HTML autocomplete tokens (`name`, `given-name`, `family-name`, `email`, `tel`, `address-line1`, etc.). |
| **1.4.1 Use of Color** | Level A | 501.1, 504.2 | 9.1.4.1 | **Supports** | Color is never used as the sole indicator of status. In-line text links feature persistent underlines. Badges include icon indicators and textual labels. |
| **1.4.2 Audio Control** | Level A | 501.1, 504.2 | 9.1.4.2 | **Not Applicable** | No audio plays automatically. |
| **1.4.3 Contrast (Minimum)** | Level AA | 501.1, 504.2 | 9.1.4.3 | **Supports** | Standard themes maintain at least 4.5:1 for normal text and 3:1 for large text. |
| **1.4.4 Resize Text** | Level AA | 501.1, 504.2 | 9.1.4.4 | **Supports** | Text resizes up to 200% via browser zoom without loss of content or functionality; in-app slider supports up to 150% scaling. |
| **1.4.5 Images of Text** | Level AA | 501.1, 504.2 | 9.1.4.5 | **Supports** | Real DOM text is used exclusively; no raster images of text are used in UI controls. |
| **1.4.6 Contrast (Enhanced)** | Level AAA | *(Section 508 Advisory)* | 9.1.4.6 | **Exceeds** | High-contrast ADA themes (`dark-ada`, `light-ada`) achieve **21:1 contrast**, exceeding the 7:1 AAA requirement. |
| **1.4.8 Visual Presentation** | Level AAA | *(Section 508 Advisory)* | 9.1.4.8 | **Exceeds** | Users can customize foreground/background colors, line spacing, font size, and switch to OpenDyslexic typeface. |
| **1.4.9 Images of Text (No Exception)** | Level AAA | *(Section 508 Advisory)* | 9.1.4.9 | **Exceeds** | Zero images of text exist across the platform. |
| **1.4.10 Reflow** | Level AA | 501.1, 504.2 | 9.1.4.10 | **Supports** | Responsive layout reflows down to 320 CSS pixels (400% zoom at 1280px) without horizontal scrolling. |
| **1.4.11 Non-text Contrast** | Level AA | 501.1, 504.2 | 9.1.4.11 | **Supports** | UI boundaries, form control borders, and focus rings meet 3:1 contrast against adjacent colors; 2px high-visibility borders in ADA modes. |
| **1.4.12 Text Spacing** | Level AA | 501.1, 504.2 | 9.1.4.12 | **Supports** | Overriding line height (1.5x), letter spacing (0.12em), and word spacing (0.16em) causes no text clipping or overlap. |
| **1.4.13 Content on Hover or Focus** | Level AA | 501.1, 504.2 | 9.1.4.13 | **Supports** | Tooltips and overlays are dismissible via `Escape`, hoverable without vanishing, and persistent until dismissed. |
| **Principle 2: Operable** | | | | | |
| **2.1.1 Keyboard** | Level A | 501.1, 504.2 | 9.2.1.1 | **Supports** | All functions, forms, modals, tables, and setup steps are 100% operable via keyboard. |
| **2.1.2 No Keyboard Trap** | Level A | 501.1, 504.2 | 9.2.1.2 | **Supports** | Keyboard focus is never trapped; modal dialogs can be closed via `Escape` or Tab-navigation to close controls. |
| **2.1.3 Keyboard (No Exception)** | Level AAA | *(Section 508 Advisory)* | 9.2.1.3 | **Exceeds** | Zero exceptions; 100% of user workflows are keyboard executable. |
| **2.1.4 Character Key Shortcuts** | Level A | 501.1, 504.2 | 9.2.1.4 | **Supports** | No single character key shortcuts are active without explicit modifiers (`Alt`/`Ctrl`). |
| **2.2.1 Timing Adjustable** | Level A | 501.1, 504.2 | 9.2.2.1 | **Supports** | No expiring session timeouts occur without configurable warnings, and idle session limits are administrator-controlled. |
| **2.2.2 Pause, Stop, Hide** | Level A | 501.1, 504.2 | 9.2.2.2 | **Supports** | Looping or animated content can be disabled via the Reduced Motion toggle. |
| **2.2.3 No Timing** | Level AAA | *(Section 508 Advisory)* | 9.2.2.3 | **Exceeds** | Form submissions and opt-out workflows have no time limits. |
| **2.3.1 Three Flashes or Below** | Level A | 501.1, 504.2 | 9.2.3.1 | **Supports** | No components flash more than three times per second. |
| **2.3.2 Three Flashes** | Level AAA | *(Section 508 Advisory)* | 9.2.3.2 | **Exceeds** | Zero strobing or flashing components application-wide. |
| **2.3.3 Animation from Interactions** | Level AAA | *(Section 508 Advisory)* | 9.2.3.3 | **Exceeds** | Interaction-driven animations are suppressed when Reduced Motion is enabled. |
| **2.4.1 Bypass Blocks** | Level A | 501.1, 504.2 | 9.2.4.1 | **Supports** | High-contrast `SkipLink` bypasses repetitive navigation headers directly to `<main>`. |
| **2.4.2 Page Titled** | Level A | 501.1, 504.2 | 9.2.4.2 | **Supports** | Every view dynamically updates `<title>` to describe current location and task. |
| **2.4.3 Focus Order** | Level A | 501.1, 504.2 | 9.2.4.3 | **Supports** | Tab progression follows the visual and logical layout. |
| **2.4.4 Link Purpose (In Context)** | Level A | 501.1, 504.2 | 9.2.4.4 | **Supports** | Hyperlinks convey clear destinations within context. |
| **2.4.5 Multiple Ways** | Level AA | 501.1, 504.2 | 9.2.4.5 | **Supports** | Pages reachable via persistent sidebar navigation, search bar, breadcrumb trail, and direct deep-links. |
| **2.4.6 Headings and Labels** | Level AA | 501.1, 504.2 | 9.2.4.6 | **Supports** | Headings clearly identify sections; form labels describe required input values. |
| **2.4.7 Focus Visible** | Level AA | 501.1, 504.2 | 9.2.4.7 | **Supports** | High-contrast 3px solid focus indicators visible across all elements. |
| **2.4.8 Location** | Level AAA | *(Section 508 Advisory)* | 9.2.4.8 | **Exceeds** | Dynamic breadcrumbs with `aria-current="page"` indicate user position within the app hierarchy. |
| **2.4.9 Link Purpose (Link Only)** | Level AAA | *(Section 508 Advisory)* | 9.2.4.9 | **Exceeds** | Link phrases are explicit and self-describing out of context. |
| **2.4.10 Section Headings** | Level AAA | *(Section 508 Advisory)* | 9.2.4.10 | **Exceeds** | Semantic `<h1>`-`<h4>` headers organize all complex screens and settings tabs. |
| **2.4.11 Focus Not Obscured (Min)** | Level AA | 501.1, 504.2 | 9.2.4.11 | **Supports** | Focused items are never completely obscured by sticky headers or footers. |
| **2.4.12 Focus Not Obscured (Enh)** | Level AAA | *(Section 508 Advisory)* | 9.2.4.12 | **Exceeds** | No author-created overlay obscures any portion of a focused control. |
| **2.4.13 Focus Appearance** | Level AAA | *(Section 508 Advisory)* | 9.2.4.13 | **Exceeds** | Focus indicator perimeter exceeds 2px, contrasting at 3:1+ against both dark and light modes. |
| **2.5.1 Pointer Gestures** | Level A | 501.1, 504.2 | 9.2.5.1 | **Supports** | All interactions operable via single-point clicks; no multi-point or path-based gestures required. |
| **2.5.2 Pointer Cancellation** | Level A | 501.1, 504.2 | 9.2.5.2 | **Supports** | Actions execute on pointer up-event; moving pointer away before release cancels action. |
| **2.5.3 Label in Name** | Level A | 501.1, 504.2 | 9.2.5.3 | **Supports** | Programmatic accessible names match or contain visible text labels. |
| **2.5.4 Motion Actuation** | Level A | 501.1, 504.2 | 9.2.5.4 | **Not Applicable** | No features require device shaking, tilting, or gestures. |
| **2.5.5 Target Size (Enhanced)** | Level AAA | *(Section 508 Advisory)* | 9.2.5.5 | **Exceeds** | Enhanced Target Sizing mode enforces **44x44 CSS pixels** minimum interactive bounding boxes. |
| **2.5.6 Concurrent Inputs** | Level AAA | *(Section 508 Advisory)* | 9.2.5.6 | **Exceeds** | Users can seamlessly switch between mouse, keyboard, touch screen, and stylus input. |
| **2.5.7 Dragging Movements** | Level AA | 501.1, 504.2 | 9.2.5.7 | **Supports** | Priority ordering operations provide simple single-click dropdown and button controls as alternatives to drag-and-drop. |
| **2.5.8 Target Size (Minimum)** | Level AA | 501.1, 504.2 | 9.2.5.8 | **Supports** | All interactive targets meet or exceed 24x24 CSS pixels in default mode, and 44x44 CSS pixels in ADA mode. |
| **Principle 3: Understandable** | | | | | |
| **3.1.1 Language of Page** | Level A | 501.1, 504.2 | 9.3.1.1 | **Supports** | Root `<html lang="...">` dynamically updates upon changing any of the 17 bundled language packs. |
| **3.1.2 Language of Parts** | Level AA | 501.1, 504.2 | 9.3.1.2 | **Supports** | Multi-lingual opt-out previews and statutory citations specify explicit programmatic `lang` and `dir` attributes. |
| **3.2.1 On Focus** | Level A | 501.1, 504.2 | 9.3.2.1 | **Supports** | Receiving focus never triggers context changes, modal launches, or unexpected navigation. |
| **3.2.2 On Input** | Level A | 501.1, 504.2 | 9.3.2.2 | **Supports** | Changing input fields does not automatically submit forms or shift viewport focus. |
| **3.2.3 Consistent Navigation** | Level AA | 501.1, 504.2 | 9.3.2.3 | **Supports** | Navigation sidebars and control headers appear in identical order across all views. |
| **3.2.4 Consistent Identification** | Level AA | 501.1, 504.2 | 9.3.2.4 | **Supports** | Common interface components (search, filter, delete, export) share identical iconography and naming. |
| **3.2.5 Change on Request** | Level AAA | *(Section 508 Advisory)* | 9.3.2.5 | **Exceeds** | Major context shifts occur only upon deliberate user button activation. |
| **3.3.1 Error Identification** | Level A | 501.1, 504.2 | 9.3.3.1 | **Supports** | Form errors are identified in plain text and highlighted visually and programmatically. |
| **3.3.2 Labels or Instructions** | Level A | 501.1, 504.2 | 9.3.3.2 | **Supports** | Clear field labels and explanatory helper text accompany all data entry inputs. |
| **3.3.3 Error Suggestion** | Level AA | 501.1, 504.2 | 9.3.3.3 | **Supports** | Actionable suggestions provided for email formatting, password complexity, and URL validity. |
| **3.3.4 Error Prevention (Data/Legal)** | Level AA | 501.1, 504.2 | 9.3.3.4 | **Supports** | Critical actions (deleting member profiles, purging logs, cryptographic shredding) require explicit secondary modal confirmation. |
| **3.3.7 Redundant Entry** | Level AA | 501.1, 504.2 | 9.3.3.7 | **Supports** | Member identity information auto-populates across data broker workflows without repetitive manual re-entry. |
| **3.3.8 Accessible Authentication** | Level AA | 501.1, 504.2 | 9.3.3.8 | **Supports** | Supports password managers, copy-paste credentials, and WebAuthn hardware passkeys; zero CAPTCHA or cognitive tests for patron sign-in. |
| **3.3.9 Accessible Auth (Enhanced)** | Level AAA | *(Section 508 Advisory)* | 9.3.3.9 | **Exceeds** | Authentication relies on no cognitive puzzles; supports FIDO2 biometric authentication natively. |
| **Principle 4: Robust** | | | | | |
| **4.1.1 Parsing** | Level A | 501.1, 504.2 | 9.4.1.1 | **Supports** | Valid HTML5 DOM syntax verified; elements have complete start and end tags without duplicate attributes. |
| **4.1.2 Name, Role, Value** | Level A | 501.1, 504.2 | 9.4.1.2 | **Supports** | All controls expose standard programmatic name, role, state (`aria-expanded`, `aria-checked`), and values. |
| **4.1.3 Status Messages** | Level AA | 501.1, 504.2 | 9.4.1.3 | **Supports** | Toast alerts and broker status updates announced to screen readers via `aria-live="polite"` without stealing focus. |

---

### Table 2: Revised Section 508 Chapter 5 (Software) & Chapter 6 (Support Documentation)

| Section 508 Clause | Requirement Description | Conformance Level | Remarks and Explanations |
|---|---|---|---|
| **501.1 Scope** | Web and Non-Web Software Conformance | **Supports / Exceeds** | Fully conforms to WCAG 2.2 Level A and Level AA (incorporating and exceeding WCAG 2.0/2.1 standards). |
| **502.2.1** | User-Control of Accessibility Features | **Supports** | OpenOptOut does not override or disable operating system accessibility features. |
| **502.2.2** | No Disruption of Accessibility Features | **Supports** | Does not interfere with screen readers, magnification tools, or system high-contrast settings. |
| **502.3.1 - 502.3.14** | Interoperability with Assistive Technology | **Supports** | Exposes object name, role, state, value, boundary coordinates, and hierarchy to platform accessibility APIs. |
| **503.2** | User Preferences | **Supports** | Automatically syncs with OS preferences (`prefers-color-scheme`, `prefers-reduced-motion`) and provides persistent in-app overrides. |
| **503.3** | Alternative User Interfaces | **Supports** | High-contrast ADA modes, font size scaling, and OpenDyslexic typography offer equivalent functionality. |
| **503.4** | Color and Contrast | **Supports / Exceeds** | High-contrast modes achieve **21:1 contrast**, exceeding federal 4.5:1 / 7:1 thresholds. |
| **504 Authoring Tools** | Authoring Tool Conformance | **Not Applicable** | OpenOptOut is a data protection and opt-out execution application, not an authoring tool. |
| **602.2** | Accessibility Documentation | **Supports** | All accessibility features, keyboard commands, and high-contrast modes are comprehensively documented in this guide. |
| **602.3** | Electronic Support Documentation | **Supports** | Documentation published in accessible Markdown/HTML formats adhering to WCAG 2.2 standards. |
| **602.4** | Alternate Formats | **Supports** | Textual documentation is fully compatible with screen readers, Braille displays, and text-to-speech converters. |
| **603.2** | Information on Accessibility Features | **Supports** | Support channels and documentation provide complete technical details regarding accessibility capabilities. |
| **603.3** | Accommodation of Communication Needs | **Supports** | Issue tracking via GitHub Issues, email support, and screen-reader accessible interaction pathways. |

---

### Table 3: EN 301 549 v3.2.1 Conformance Mapping

| EN 301 549 Clause | Requirement Description | Conformance Level | Remarks and Explanations |
|---|---|---|---|
| **Clause 9 (Web)** | Web Accessibility Requirements (WCAG Mapping) | **Supports / Exceeds** | Meets all mandatory Clause 9 clauses (9.1.1.1 through 9.4.1.3) corresponding to WCAG 2.2 AA and key AAA provisions. |
| **Clause 10 (Documents)** | Non-Web Documents | **Not Applicable** | Web-native application; does not distribute non-web document formats. |
| **Clause 11.1** | Software: Non-Web Software Functionality | **Supports** | User interface exposed via modern web browser engines adhering to standard browser accessibility APIs. |
| **Clause 11.2 - 11.6** | Interoperability, Visual Display, and Contrast | **Supports / Exceeds** | Complies with user preference synchronization, non-interference, and high-contrast display mandates. |
| **Clause 11.7** | User Preferences | **Supports** | Adheres to system and user-defined color scheme, typography, and motion preferences. |
| **Clause 12.1** | Product Documentation | **Supports** | Fully accessible online documentation describing accessibility and operational features. |
| **Clause 12.2** | Support Services | **Supports** | Accessible support mechanisms accommodating diverse user communication needs. |

---

## Institutional Procurement & Evaluation Guidance

For institutions evaluating OpenOptOut for campus, library, municipal, or enterprise procurement:

1. **Higher Education (HECVAT & Section 508)**:
   OpenOptOut satisfies Title II and Title III Americans with Disabilities Act (ADA) requirements, Revised Section 508 Chapter 5, and WCAG 2.2 AA standards. Academic libraries and campus privacy initiatives can deploy the platform with confidence that student and faculty privacy rights are universally exercisable. For student records privacy and campus IdP federation details, see the [FERPA Architecture Alignment Guide](docs/architecture/ferpa-alignment.md).
2. **European Public Procurement (EN 301 549 & European Accessibility Act)**:
   Complies with EU Directive 2016/2102 and the European Accessibility Act (EAA) procurement requirements for public sector software.
3. **Air-Gapped Privacy & Security Isolation**:
   Unlike commercial privacy services that introduce external tracking, third-party analytics, or remote font CDNs, OpenOptOut is 100% self-hosted and air-gapped. Accessible typefaces (including OpenDyslexic) are locally bundled, ensuring zero patron data exposure to font registries.
4. **First-Boot Setup Usability**:
   Accessibility configuration is the first screen presented in the setup wizard, ensuring visually impaired or neurodivergent administrators can configure the system independently from initial deployment.

---

## Reporting Accessibility Issues

We treat accessibility regressions with the same urgency as security vulnerabilities. If you encounter an accessibility barrier or require an accommodation:

- **GitHub Accessibility Tracker**: File an issue at [https://github.com/rlnunez/OpenOptOut/issues](https://github.com/rlnunez/OpenOptOut/issues) with the `accessibility` or `a11y` label.
- **Maintainer Direct Email**: Contact Robert Nunez at [nunez.robert@gmail.com](mailto:nunez.robert@gmail.com) with subject `[A11Y Conformance] OpenOptOut`.
- **Review SLA**: Accessibility reports are acknowledged within 48 hours and triaged directly into active release sprints.
