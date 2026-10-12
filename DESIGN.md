---
name: Popcorn SR
description: A quiet native workspace that makes remote processing feel like a simple local library task.
colors:
  accent: "oklch(62.3% 0.214 259.815)"
  white-surface: "#ffffff"
  zinc-paper: "oklch(98.5% 0 none)"
  zinc-subtle: "oklch(96.7% 0.001 286.375)"
  zinc-divider: "oklch(92% 0.004 286.32)"
  zinc-dark-muted: "oklch(70.5% 0.015 286.067)"
  zinc-status: "oklch(55.2% 0.016 285.938)"
  zinc-muted: "oklch(44.2% 0.017 285.786)"
  zinc-dark-divider: "oklch(27.4% 0.006 286.033)"
  zinc-ink: "oklch(21% 0.006 285.885)"
  zinc-black: "oklch(14.1% 0.005 285.823)"
  status-connected: "oklch(69.6% 0.17 162.48)"
  status-warning: "oklch(76.9% 0.188 70.08)"
  status-error: "oklch(63.7% 0.237 25.331)"
typography:
  headline:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "1.875rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.025em"
  title:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-0.025em"
  section:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.5
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "14px"
    fontWeight: 550
    lineHeight: 1.5
  action:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.4285714286
  navigation:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "0.875rem"
    fontWeight: 500
    lineHeight: 1.4285714286
  metadata:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  tag:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.4
rounded:
  control: "8px"
  panel: "16px"
  tag: "6px"
  progress: "4px"
spacing:
  field-gap: "8px"
  group-gap: "16px"
  form-gap: "20px"
  section-gap: "24px"
  panel-padding: "28px"
  page-gap: "32px"
  major-gap: "40px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.zinc-black}"
    typography: "{typography.action}"
    rounded: "{rounded.control}"
    padding: "11px 17px"
  button-secondary:
    backgroundColor: "{colors.white-surface}"
    textColor: "{colors.zinc-ink}"
    typography: "{typography.action}"
    rounded: "{rounded.control}"
    padding: "11px 17px"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.zinc-muted}"
    typography: "{typography.action}"
    rounded: "{rounded.control}"
    padding: "11px 10px"
  input:
    backgroundColor: "{colors.white-surface}"
    textColor: "{colors.zinc-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
    width: "100%"
  navigation:
    backgroundColor: "transparent"
    textColor: "{colors.zinc-muted}"
    typography: "{typography.navigation}"
    rounded: "{rounded.control}"
    padding: "12px 14px"
  navigation-current:
    backgroundColor: "{colors.zinc-subtle}"
    textColor: "{colors.zinc-ink}"
  tag:
    backgroundColor: "{colors.zinc-subtle}"
    textColor: "{colors.zinc-muted}"
    typography: "{typography.tag}"
    rounded: "{rounded.tag}"
    padding: "5px 9px"
  panel:
    backgroundColor: "{colors.white-surface}"
    rounded: "{rounded.panel}"
  panel-padded:
    padding: "{spacing.panel-padding}"
  message:
    backgroundColor: "{colors.zinc-subtle}"
    rounded: "{rounded.control}"
    padding: "14px 18px"
  progress:
    backgroundColor: "{colors.zinc-subtle}"
    rounded: "{rounded.progress}"
    height: "5px"
    width: "100%"
  preview-continuation:
    textColor: "{colors.zinc-ink}"
    padding: "20px 24px"
---

# Design System: Popcorn SR

## Overview

**Creative North Star: "Quiet native workspace"**

Make remote processing feel like a simple local library task. Neutral surfaces, familiar controls and plain language let the library and its next useful action lead. The interface earns trust by distinguishing originals from finished copies and showing actual processing state.

The implemented world uses flat sections, thin dividers and one restrained action color. Recipes, worker pairing and queue actions stay inside the workspace. Motion briefly acknowledges navigation and interaction; system light/dark preference and reduced motion belong to the same world.

This record extracts reused styles from `ui.css`, `popcorn_sr/static/index.html` and `popcorn_sr/static/app.js`, resolving imported values against the installed Tailwind theme. The frontmatter is normative; component defaults describe the light theme, while the theme assignments below and sidecar snippets retain both themes. Minimum control heights live in the prose and snippets because the frontmatter's fixed-height property cannot represent them. Inspected evidence is in `evidence/screenshots`; it supports visual comparison, not GPU or AI readiness. The supplied workflow evidence covers CPU processing only.

**Key Characteristics:**

- Quiet zinc surfaces with blue actions and dark action text.
- Restrained system sans with a clear task hierarchy.
- Flat navigation, inline work and thin separators.
- Familiar controls with a minimum target height of 44px.
- System themes and reduced-motion-aware feedback.

## Colors

The palette is neutral Tailwind zinc with a single Tailwind blue action/focus accent. Values retain the installed theme's canonical OKLCH format.

### Primary

- **Action Blue** (`accent`): primary task buttons, focus outlines, checkboxes and actual job progress. Its button text remains Zinc Black in both themes.

### Neutral

- **White Surface** (`white-surface`): light-theme panels, inputs and sidebar.
- **Zinc Paper** (`zinc-paper`): light page canvas and dark-theme main text.
- **Zinc Subtle** (`zinc-subtle`): light selected navigation, tags and messages.
- **Zinc Divider** (`zinc-divider`): light borders and separators.
- **Zinc Muted** (`zinc-muted`): light supporting text.
- **Zinc Ink** (`zinc-ink`): light main text and dark panels, inputs and sidebar.
- **Zinc Black** (`zinc-black`): dark page canvas and text on blue actions.
- **Zinc Dark Divider** (`zinc-dark-divider`): dark borders, selected navigation, tags and messages.
- **Zinc Dark Muted** (`zinc-dark-muted`): dark supporting text.
- **Zinc Status** (`zinc-status`): neutral connection dot.

| Semantic assignment in CSS | Light | Dark |
| --- | --- | --- |
| Page | Zinc Paper | Zinc Black |
| Surface | White Surface | Zinc Ink |
| Main text | Zinc Ink | Zinc Paper |
| Supporting text | Zinc Muted | Zinc Dark Muted |
| Border/divider | Zinc Divider | Zinc Dark Divider |
| Subtle fill | Zinc Subtle | Zinc Dark Divider |
| Action fill/focus | Action Blue | Action Blue |
| Action text | Zinc Black | Zinc Black |

Connected emerald, warning amber and error red are semantic indicators, not additional action palettes. They appear in small connection dots or message borders; accompanying text uses the ordinary main/supporting text colors. Status always includes words.

**The One Accent Rule.** Use Action Blue for the next processing action and focus or progress feedback; keep navigation and secondary actions neutral.

## Typography

**Body and heading font:** the platform system sans stack in the frontmatter. No separate display face is part of this Operate interface. Monospace is confined to the selectable pairing code and literal commands.

**Character:** restrained, familiar and readable. Sentence-case headings and controls establish hierarchy through size and weight. No uppercase eyebrow style is part of the reusable system.

### Hierarchy

- **Headline:** page headings; reduce to the implemented compact size (28px) at the narrow breakpoint.
- **Title:** section and panel headings. Settings headings use the smaller section treatment with normal tracking.
- **Section:** step and small section headings.
- **Body:** normal content and native input/select text. Supporting paragraphs use relaxed leading (1.6–1.7); subtitles are limited to the observed measure (58ch), settings prose to (68ch).
- **Label:** field labels; medium emphasis without uppercase styling.
- **Action / Navigation:** compact button text and lighter navigation labels.
- **Metadata / Tag:** file paths, job details and status; metadata wraps long paths, while short tags stay on one line. Hints use metadata size with relaxed leading (1.6).

The overview's enlarged panel heading is a local composition, not a new display token. The brand wordmark and its unique measurements are also outside the reused type ramp.

**The Readable Hierarchy Rule.** Reserve headline and title emphasis for task structure; keep paths, formats and status in the supporting text hierarchy.

## Layout

The desktop shell pairs a sticky sidebar (228px) with flexible main content. The main container is centered within its column, bounded (1320px) and padded responsively (`clamp(24px, 5vw, 64px)`). Navigation is consistent across Overview, Library, Processing, Queue and Settings.

Fields use two equal columns with the form gap; output destination spans both. Workers use two columns with the section gap. Queue and library rows place content beside actions, use thin bottom dividers and allow long names and paths to wrap. The frontmatter records repeated gaps and padding, not a fabricated universal spacing scale.

At the compact-navigation breakpoint (maximum 800px), the sidebar becomes a top bar with five equal navigation columns, main padding becomes (24px 20px 48px), workers stack, and the overview diagram is hidden. At the stacked-controls breakpoint (maximum 520px), page headers, recipe fields and row actions stack; padded panels use (20px), and onboarding becomes a vertical sequence. These are the source's breakpoints, not Tailwind's default breakpoint scale.

The implemented Overview introduces a library-to-worker-to-output diagram beside the choose-video action and an ordered onboarding sequence below it. This is the first-surface expression of the world, not a mandatory template for every screen. The diagram's absence below the compact breakpoint is recorded behavior, not a general ban on diagrams.

**The Inline Work Rule.** Keep recipes, pairing and job actions in their relevant workspace sections, using spacing and dividers to separate steps.

## Elevation & Depth

No box shadows are defined in the implemented system. Tonal differences, thin borders (1px), whitespace and selected navigation establish separation. Panels enclose real library, recipe, worker or queue content. Dividers group rows and secondary options; they do not imply floating cards.

**The Flat By Default Rule.** Use neutral surfaces and thin dividers for structure; do not add decorative elevation to ordinary workspace sections.

## Shapes

Controls and messages use the control radius; major panels use the panel radius; small descriptive tags use the tag radius. Progress tracks use the smaller progress radius. Circular connection dots and numbered onboarding markers communicate state or sequence rather than creating a pill-shaped control system.

**The Familiar Controls Rule.** Maintain the implemented 44px minimum height for buttons, navigation, text inputs and selects; checkbox labels and disclosure summaries provide the same minimum vertical target.

## Components

### Buttons

Quiet, direct controls with task names. Primary buttons pair Action Blue with Zinc Black; secondary buttons use the theme surface and a thin divider border; quiet buttons remove the visible fill and border. Padding and typography are defined in frontmatter.

Hover uses the observed brightness filter (`brightness(.94)`); press uses the observed scale (`scale(.98)`). Visible focus uses an accent outline (2px) with an offset (4px). Disabled buttons halve opacity and use the default cursor. Background/transform transitions run only when reduced motion is not requested (160ms, `ease-out`). The brightness filter has no separately invented hover-color token.

### Chips

Tags describe connection state, preview identity and available encoders. They use subtle fill and supporting text, with no decorative shadow or border. Connection tags combine a small circular dot (7px) with a word such as Connected or Offline. They are descriptive, not clickable filters.

### Cards / Containers

Flat panels have a theme surface, thin divider border, panel radius and clipped overflow. Standard padded panels use the panel padding; narrow screens use the observed compact padding. Library and queue rows provide internal separators instead of nested cards. The overview's larger padding is local to that composition.

### Inputs / Fields

Native inputs and selects share the control radius, surface fill and thin divider border. They span the available width and use body text. Labels sit above fields with the field gap; helper text follows in the supporting hierarchy. Text inputs, selects and checkbox labels retain visible focus. Recipe/login errors stay inline in message containers; submit controls expose busy copy and disabled state.

### Navigation

Desktop navigation is a vertical list of rounded, neutral buttons. Hover and the current page share subtle fill and main text; inactive items use supporting text. The current page is exposed through `aria-current`. Compact navigation uses five equal columns, smaller text (12px) and observed compact padding (10px 2px), retaining the minimum target height. View changes focus the main region, and a keyboard skip link reaches it.

### Messages and Progress

Messages use subtle fill, the control radius and wrapping text. Success and error states add the corresponding thin semantic border; their text remains neutral. Global notices use a polite live region, while form errors use alerts. Job progress is a thin actual progress track (5px) with the action accent; it is not a decorative metric.

### Preview Continuation

A completed preview row offers a secondary download and a primary **Enhance full video** action. The Queue header's **Choose a video** action is secondary, so continuation leads. The action posts directly to the saved job's full-video endpoint, refreshes the queue and acknowledges use of the preview settings and preservation of the original. It does not reopen the recipe form.

The source-hash check and reuse of saved settings are supplied CPU workflow evidence for this handoff; this document pass inspected the UI and its action wiring, not the server verification path. Neither the display of a device name nor a capability label establishes GPU/AI readiness.

**The Continue The Preview Rule.** Let a completed preview continue directly from its job row with saved settings; keep download and choosing another source secondary to that continuation.

When motion is allowed, views enter briefly (200ms, `ease-out`, opacity and a 4px vertical shift). Selecting a video scrolls to its inline recipe smoothly; reduced-motion preference uses an instant scroll. The sidecar records those existing behaviors without adding new animation.

## Do's and Don'ts

### Do:

- **Do** keep actions and focus blue with dark text on filled blue buttons in both themes.
- **Do** use neutral surfaces, thin dividers and the existing control/panel shape hierarchy.
- **Do** preserve visible focus, native controls, wrapping paths and the 44px minimum control height.
- **Do** pair semantic status indicators with readable words and neutral text.
- **Do** continue a completed preview from its job row using the saved settings.
- **Do** honor system light/dark preference and reduced motion.

### Don't:

- **Don't** turn status colors into additional action colors.
- **Don't** add decorative charts, fake activity, gradients or glass to this quiet workspace.
- **Don't** make ordinary inline tasks depend on a decorative modal or nested card stack.
- **Don't** imply that processing replaces the library original.
- **Don't** treat screenshots, device names or mocked capabilities as GPU/AI readiness evidence.
- **Don't** promote redundant eyebrows, Unicode icon substitutes or one-off brand measurements into reusable system tokens.
