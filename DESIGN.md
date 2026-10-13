---
name: Popcorn SR
description: A quiet native workspace that makes remote processing feel like a simple local library task.
colors:
  accent: "#3b82f6"
  family-sr: "#14b8a6"
  accent-text-light: "#1d4ed8"
  accent-text-dark: "#93c5fd"
  white-surface: "#ffffff"
  zinc-paper: "#fafafa"
  zinc-subtle: "#f4f4f5"
  zinc-divider: "#e4e4e7"
  zinc-dark-muted: "#a1a1aa"
  zinc-status: "#71717a"
  zinc-muted: "#52525b"
  zinc-dark-subtle: "#27272a"
  zinc-dark-divider: "#3f3f46"
  zinc-ink: "#18181b"
  zinc-black: "#09090b"
  neutral-fill-light: "#1B1B1F1A"
  neutral-fill-dark: "#E1E2E833"
  status-connected: "#22c55e"
  status-warning: "#f59e0b"
typography:
  headline:
    fontFamily: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: 2rem
    fontWeight: 600
    lineHeight: 1.2
  title:
    fontFamily: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: 1.375rem
    fontWeight: 600
    lineHeight: 1.4545
  section:
    fontFamily: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: 1.125rem
    fontWeight: 600
    lineHeight: 1.5556
  body:
    fontFamily: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: 0.9375rem
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: 0.9375rem
    fontWeight: 500
    lineHeight: 1.6
  action:
    fontFamily: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: 0.9375rem
    fontWeight: 500
    lineHeight: 1.6
  navigation:
    fontFamily: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: 0.9375rem
    fontWeight: 400
    lineHeight: 1.6
  supporting:
    fontFamily: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
    fontSize: 0.8125rem
    fontWeight: 400
    lineHeight: 1.5385
  code:
    fontFamily: ui-monospace, "SF Mono", Monaco, Consolas, "Liberation Mono", "Courier New", monospace
    fontSize: 0.9375rem
    fontWeight: 400
    lineHeight: 1.6
rounded:
  inner: 0.375rem
  control: 0.625rem
  panel: 0.75rem
  full: 9999px
spacing:
  field-gap: 8px
  control-inset: 12px
  group-gap: 16px
  row-block: 20px
  section-gap: 24px
  page-head-gap: 28px
  page-gap: 32px
  major-gap: 40px
  welcome-gap: 48px
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.zinc-black}"
    typography: "{typography.action}"
    rounded: "{rounded.control}"
    padding: 8px 12px
    height: 44px
  button-secondary:
    backgroundColor: "{colors.neutral-fill-light}"
    textColor: "{colors.zinc-ink}"
    typography: "{typography.action}"
    rounded: "{rounded.control}"
    padding: 8px 12px
    height: 44px
  button-quiet:
    backgroundColor: transparent
    textColor: "{colors.zinc-ink}"
    typography: "{typography.action}"
    rounded: "{rounded.control}"
    padding: 8px 12px
    height: 44px
  input:
    backgroundColor: "{colors.white-surface}"
    textColor: "{colors.zinc-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: 4px 8px
    height: 44px
    width: 100%
  selector:
    backgroundColor: "{colors.white-surface}"
    textColor: "{colors.zinc-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: 8px 12px
    width: 100%
  navigation:
    backgroundColor: transparent
    textColor: "{colors.zinc-ink}"
    typography: "{typography.navigation}"
    rounded: "{rounded.control}"
    padding: 0 8px
    height: 44px
    width: 100%
  navigation-current:
    backgroundColor: "{colors.neutral-fill-light}"
    textColor: "{colors.zinc-ink}"
  status:
    textColor: "{colors.zinc-muted}"
    typography: "{typography.supporting}"
  panel:
    backgroundColor: "{colors.white-surface}"
    rounded: "{rounded.panel}"
  panel-padded:
    padding: "{spacing.section-gap}"
  disclosure:
    textColor: "{colors.zinc-ink}"
    typography: "{typography.section}"
    padding: "0"
    width: 100%
  progress:
    backgroundColor: "{colors.zinc-subtle}"
    rounded: "{rounded.full}"
    height: 8px
    width: 100%
  preview-continuation:
    textColor: "{colors.zinc-ink}"
    padding: 20px 24px
---

# Design System: Popcorn SR

## Overview

**Creative North Star: "Quiet native workspace"**

Make remote processing feel like a simple local library task. Neutral surfaces, familiar controls and plain language let the library and its next useful action lead. The interface earns trust by distinguishing originals from finished copies and showing actual processing state.

The implemented world uses flat sections, thin dividers and one restrained action color. Recipes, worker pairing and queue actions stay inside the workspace. Motion briefly acknowledges navigation and interaction; system light/dark preference and reduced motion belong to the same world.

This is a source-led refresh of the approved world for the official Astryx migration. Frontmatter records current source values, including inherited Neutral defaults; it does not declare implementation discrepancies approved. Light-theme component defaults are paired with dark assignments in the schema-2 sidecar. Minimum targets, focus, motion and React wiring also live there because frontmatter cannot express them completely.

**Key Characteristics:**

- Quiet zinc surfaces with blue actions and dark action text.
- Restrained system sans with a clear task hierarchy.
- Flat navigation, inline work and thin separators.
- Familiar official controls with a 44px minimum target requirement.
- System themes and reduced-motion-aware feedback.

### Implementation authority

| Source | Responsibility |
| --- | --- |
| `web/themes/popcorn.mjs` | Hand-authored `defineTheme` extension of official `neutralTheme`, using `neutralIconRegistry` from `@astryxdesign/theme-neutral/built`. |
| `web/themes/popcorn.css` / `popcorn.js` | Generated stylesheet and built theme object. Inspect resolved inherited values here; regenerate rather than edit. |
| `web/styles.css` | CSS imports/layers, workspace layout, grids, rows, responsive behavior and custom status dots. |
| `web/main.jsx` / `web/index.html` | React controls, controlled state and entry point. `<Theme theme={popcornTheme} mode="system">` imports the compiled `popcorn.js`. |
| `package.json` / `package-lock.json` | Exact Astryx core, Neutral and CLI pins (0.6.8), React/React DOM (19.3.0), StyleX (0.19.0) and resolved dependency graph. |
| `vite.config.js` / `scripts/build-ui-policy.mjs` | Vite root `web`, base `/assets/`, output `popcorn_sr/static` with `bundles`, then exact selector-sheet CSP policy generation. |

`npm run build` runs `build:theme`, `vite build`, then the policy generator. The theme compiler command is:

```sh
node node_modules/@astryxdesign/cli/clients/cli/bin/astryx.mjs theme build web/themes/popcorn.mjs --icons-specifier @astryxdesign/theme-neutral/built
```

`web/styles.css` imports Tailwind theme/preflight, official Astryx reset/core CSS, compiled Popcorn CSS, Astryx's Tailwind token bridge and source-scanned utilities. Layer order is `reset, theme, base, astryx-base, astryx-theme, components, utilities`. Docker's Node stage runs the same build and copies its output into the Python image. Generated theme JS/CSS and static bundles are ignored; `popcorn_sr/static/.gitkeep` is tracked and recreated by the policy generator after Vite empties its output directory.

`popcorn_sr/server.py` mounts `/assets` only when the static directory exists. A missing built `index.html` returns a root-page 503 with build guidance; a missing directory no longer prevents app construction. This is source wiring, not fresh Docker proof. Removed `ui.css` and static `app.js` are not token/component authorities.

### Evidence boundary

Inspected supplied captures: `evidence/screenshots/overview-desktop.png`, `library-desktop.png`, `library-390-light.png` and `processing-1440-dark.png`. They show the migrated shell, inline recipe and neutral light/dark presentation. Final recaptures at 390/768/1440 light/dark were reviewed. The independent reviewer scored control readability, path wrapping and missing-build startup recovery resolved; the ship verdict covers those scored fixes. The parent verified ten Python tests, two real CPU browser workflows, zero Axe/CSP/JavaScript violations, complete inner-path wrapping and a paired ARM64 Docker roundtrip. These checks do not prove untested GPU hardware or the optional AI image.

The user reports processing/accessibility and local tests passing, plus the earlier Docker smoke passing; final rendered 44px acceptance and rebuilt captures are not independently confirmed by this pass. This documentation pass inspected source/images and recomputed the selector hash. It did not run browser, processing, Ruff, pytest, build or Docker shipping checks. Main-agent fixes, final build and runtime proof remain separate. Screenshots/device labels do not establish GPU/AI readiness.

## Colors

Neutral zinc surfaces and a single blue action/focus accent preserve the approved palette character. Current custom values are literal hex in `web/themes/popcorn.mjs` and `web/styles.css`; they replace legacy OKLCH extraction as frontmatter authority.

### Primary

- **Action Blue** (`accent`): filled primary tasks, visible focus and actual progress. Filled blue buttons retain Zinc Black text in both themes.
- **Readable Action Text** (`accent-text-light`, `accent-text-dark`): stronger light-theme and lighter dark-theme blue for text/icons, separate from filled actions.

### Neutral

White Surface, Zinc Paper, Zinc Ink and Zinc Black define the quiet surface/text hierarchy. Supporting text, divider borders, emphasized field borders and muted fills have distinct roles. Selected navigation and secondary buttons use inherited translucent neutral fill, rather than the muted-fill token.

| Semantic CSS assignment | Light frontmatter token | Dark frontmatter token |
| --- | --- | --- |
| Body background | `zinc-paper` | `zinc-black` |
| Surface / card / popover | `white-surface` | `zinc-ink` |
| Main text | `zinc-ink` | `zinc-paper` |
| Supporting text | `zinc-muted` | `zinc-dark-muted` |
| Disabled text | `zinc-status` | `zinc-dark-muted` |
| Border/divider | `zinc-divider` | `zinc-dark-divider` |
| Emphasized field border | `zinc-dark-muted` | `zinc-status` |
| Muted fill / progress track | `zinc-subtle` | `zinc-dark-subtle` |
| Selected navigation / secondary button | `neutral-fill-light` | `neutral-fill-dark` |
| Action fill / focus | `accent` | `accent` |
| Filled action text | `zinc-black` | `zinc-black` |
| Action text / icon | `accent-text-light` | `accent-text-dark` |

Custom status dots are small semantic markers (8px), always paired with words. Current CSS implements zinc ready, green-500 connected and amber-500 offline/interrupted. PRODUCT.md's approved emerald-500 connected intent differs from the implemented green; no red-500 error-dot variant exists. Official `Banner` feedback inherits Neutral semantic text and muted fills, recorded in the sidecar. These inherited values do not imply the approved semantic-500 palette has been fully applied.

**The One Accent Rule.** Use Action Blue for the next processing action and focus or progress feedback; keep navigation and secondary actions neutral.

## Typography

**Body and heading font:** the platform system sans stack in frontmatter, configured for both official theme axes. No downloaded display font is used. `Text type="code"` uses inherited system monospace for pairing codes and literal commands.

**Character:** restrained, familiar and readable. Sentence-case headings and controls establish hierarchy through size and weight. No uppercase eyebrow style is part of the reusable system.

The theme's base is 15px with ratio 1.2; the compiler quantizes the scale. `Heading` levels 1–3 map to headline, title and section. Body/supporting `Text` handles prose and paths; field/button labels use medium weight, navigation regular weight with medium selected state. The explicitly overridden page heading has no mobile size reduction. Pair-code wrapper sizes are local declarations; nested `Text type="code"` sets its own size, so wrapper values alone do not prove enlarged rendered code.

`Copy` composes `Text as="p" color="secondary" wordBreak="break-word"`. Library mount, worker scratch and job-result text use the `.path` utility: block display, minimum width zero, maximum width 100%, and `overflow-wrap: anywhere`. Astryx applies its `wordBreak` prop only when `maxLines > 0`; unlimited paths therefore need this explicit layout rule. The library path and page-heading stack also use `min-w-0`. Processing guidance is bounded (70ch). iOS coarse-pointer fields/selectors inherit the official 16px text floor.

**The Readable Hierarchy Rule.** Reserve headline and title emphasis for task structure; keep paths, formats and status in the supporting text hierarchy.

## Layout

One workspace replaces the former overview/sidebar/library/queue navigation. The header carries the family mark, truthful processing status and one Devices & storage button. Desktop input and output queue share two equal columns; upscaling settings sit underneath. On screens below 768px, input, queue and settings stack in that order. Content remains centered at 1160px with existing spacing and neutral surfaces.

The default form shows Enhancement, Output size (DLSS mode for that engine) and Video format. Add to queue is the primary action; Preview 5 seconds is secondary. More options contains device selection, destination, frame generation, HDR and engine-specific advanced controls. Verified VSR quality/custom dimensions appear only when relevant. Setup has a direct Back to videos action; the hidden workspace stays mounted so input and settings survive that visit.

Input folders retain paging, refresh, parent navigation, safe relative paths and clear selected state. Queue rows lead with the filename, actual stage/status/progress and download/retry/cancel actions. Detailed method/codec/preset/frame/HDR/output information is under Details. Both lists scroll within bounded regions as content grows. There is no invented activity or diagram. The skip link targets the main landmark, and view changes focus it without scrolling.

The mark uses Popcorn Batch's exact circle geometry from commit `54170f2684f734712b6159ccc7592f3237fa6b71`, with the lower-right circle teal-500 (#14b8a6) instead of Batch's top blue circle. The tile and two neutral circles invert with the theme; favicon uses a fixed zinc-900 tile. Header and login use the same geometry. Teal identifies this family member and does not replace blue action/focus feedback.

## Elevation & Depth

Ordinary panels remain flat, separated by tonal hierarchy, thin borders (1px) and whitespace. No decorative panel shadow is defined in `web/styles.css`. Official inputs use inset hover/focus feedback; selector popovers inherit Neutral elevation. The sidecar retains source-derived shadow/focus snippets without authorizing elevated ordinary panels.

**The Flat By Default Rule.** Use neutral surfaces and thin dividers for structure; do not add decorative elevation to ordinary workspace sections.

## Shapes

Current compiled Neutral values are recorded in frontmatter: inner, control and panel radii. At normal root size, controls resolve to 10px and panels to 12px. PRODUCT.md's approved 8px control / 16px major-panel choices remain the target; the current theme has no radius overrides enforcing them. This is source drift, not a new direction. Progress tracks and dots are circular. No tag/chip control is currently implemented.

Theme tokens set small/medium controls to 44px and large to 48px. Overrides add button minimum height/width and non-shrinking behavior, minimum height to text-input/selector/side-nav-item/checkbox-input, and a **44px `collapsible-trigger` minimum**. The checkbox row also has a 44px minimum. These source declarations do not prove every inner combobox, checkbox label or mobile toggle target measures 44px; final rendered-target acceptance belongs to the main agent.

**The Familiar Controls Rule.** Preserve the approved minimum 44px interactive target for buttons, navigation, text fields, selectors, checkbox labels and disclosure triggers; verify the clickable element rather than its surrounding panel.

## Components

### Official component vocabulary

`web/main.jsx` imports official `VStack`, `HStack`, `Heading`, `Text`, `Button`, `TextInput`, `NumberInput`, `Selector`, `CheckboxInput`, `Collapsible`, `Banner` and `ProgressBar` from `@astryxdesign/core` subpaths. Custom `Copy`, `PageHead`, `Empty`, `Status`, `Feedback`, recipes and rows compose these. Layout CSS does not recreate the control library.

### Buttons

Quiet, direct controls with task names. Primary uses Action Blue/Zinc Black, default secondary uses translucent neutral fill/main text, and ghost removes fill. Official padding and compiled control radius apply. Downloads use `Button href`.

Official hover/press overlays replace the old brightness filter. Enabled press scales to `.98`; disabled buttons use opacity `.5`. Keyboard button/navigation focus uses the inherited accent outline (2px solid, 3px offset). Requests use `isLoading` or `clickAction`; availability uses `isDisabled`. The final theme base prevents shrinking:

```js
components: {
  'collapsible-trigger': {base: {minHeight: '44px'}},
  button: {base: {minHeight: '44px', minWidth: '44px', flexShrink: '0'}},
  'text-input': {base: {minHeight: '44px'}},
  selector: {base: {minHeight: '44px'}},
  'side-nav-item': {base: {minHeight: '44px'}},
  'checkbox-input': {base: {minHeight: '44px'}},
}
```

### Cards / Containers

Custom `.panel` uses surface fill, a thin border, compiled panel radius and clipped overflow. Worker/recipe bodies use 24px official stack padding; empty states use 32px. Library/queue rows have internal separators. No official `Card` import or decorative nested-card system exists.

### Inputs / Fields and Selectors

`TextInput` owns its associated label, description, required marker and native input. `Selector` supplies a controlled combobox, options, disabled choices and layer. Both `onChange` callbacks receive a value, not a native event. Emphasized borders distinguish fields from panel dividers; focus changes the wrapper border to accent and adds an inset accent-muted ring, with keyboard treatment supplied by official field styles.

```jsx
<Selector label="Processing device" value={worker}
  onChange={v => change('worker', v)} width="100%"
  options={[{value: '', label: 'Any compatible worker'},
    ...active.map(w => ({value: w.id, label: w.name + (w.online ? '' : ' (offline)')}))]} />
<TextInput label="Save copies to" value={desired.output_directory}
  onChange={v => change('output_directory', v)} isRequired maxLength={200}
  description="A folder inside your output mount. Example: enhanced/movies" />
```

The recipe stores user intent in `desired` and derives effective worker, engine, codec, encoder and scale from current capability arrays on each render. `change` merges one field; polling does not reinitialize this state. Workspace keeps Recipe mounted, so another input or a visit to setup retains the chosen settings. Compatible capabilities govern options/disabled encoders and conventional-filter checkboxes. The authenticated state poll runs every 3000ms while visible, resumes on visibility changes and guards overlapping refreshes. Connection errors retain workspace state and show reconnecting feedback; 401 clears the session. Submission queues the copy, refreshes the adjacent queue and clears the selected input. Explicitly selected unavailable enhancements remain visible and block submission.

### NVIDIA recipe controls

The current inline recipe separates enhancement from encoding. **VSR quality** offers only verified AI levels plus the adapter default; **Export quality** controls compression. **Output size → Custom dimensions** reveals paired official NumberInput fields with aligned 64–7680 px bounds and a stretching explanation. VSR strength remains under More options, beside the existing optional DLSS/HDR controls. Numeric fields use the 44px theme/style override. Queue summaries retain level, strength and exact dimensions. Missing capability checks keep the choices visible and disable submission rather than silently changing them.

The 2026-10-13 local finish pass reviewed actual 1440 light/390 dark VSR captures in two bounded rounds, with explicitly simulated GPU capabilities. Seven browser workflows passed, including Axe, overflow, numeric target sizes, invalid dimensions, heartbeat retention, capability loss/restoration and submitted combined settings. The mechanical detector found only the pre-existing 28px pairing-code advisory. The review was performed in this thread, without an independent reviewer, honoring the user's preference for direct work. Verdict: ship these controls on development main; genuine NVIDIA execution, representative quality and physical VFX acceptance remain open. Existing palette, typography, theme and composition records were preserved.

### Setup and disclosure

Devices & storage opens secondary setup; Back to videos returns to the same workspace. There is no sidebar or navigation drawer. Collapsible More options and queue Details preserve the official keyboard/disclosure behavior and 44px trigger target. Checkbox labels and their pressable rows have 44px minimum height; the rendered associated label is the clickable target for the smaller checkbox square.

### Messages, Status and Progress

`Feedback` uses non-collapsible success/error `Banner`; interrupted connections use warning, waiting jobs info, and recipe errors remain inline. Banner text/fills inherit Neutral semantic values, rather than the old neutral message box. `Status` is a bare dot plus supporting text, not a chip; dots are `aria-hidden` and words carry meaning. Running jobs use official `ProgressBar` with actual job value, accessible label and `isLabelHidden`; track height is 8px with full rounding.

### Preview Continuation

A completed preview has secondary download and primary **Enhance full video**. Queue's **Choose a video** remains secondary. `clickAction={() => onAction(job.id, 'full')}` posts to `/api/jobs/${id}/full`, refreshes the queue and acknowledges saved preview settings and preserved originals. It does not reopen the recipe. This describes wiring; source preservation and processing readiness require runtime evidence.

**The Continue The Preview Rule.** Let a completed preview continue directly from its job row with saved settings; keep download and choosing another source secondary to that continuation.

### Theme Compilation and Selector CSP

`defineTheme({name: 'popcorn', extends: neutralTheme, icons: neutralIconRegistry, ...})` compiles before Vite. The app imports the built theme object; generated CSS scopes variables/rules under `data-astryx-theme="popcorn"` and uses `light-dark()` with system color scheme. Theme changes require regeneration of both theme output and bundle.

Astryx 0.6.8 installs one static selector-placement sheet of `@position-try` rules at runtime. The policy script imports `slideRulesCss()` from installed core `dist/Layer/layerSlideRules.js`, hashes its exact UTF-8 content with SHA-256/base64, and writes `popcorn_sr/static/ui-policy.json` containing `astryx_version` and `style_hashes`. The recomputed hash matched the existing generated policy:

```text
sha256-6SjltZZHbimwo1Hbgahxv8D9b/3lyMZxSgBbD6dRcUQ=
```

`popcorn_sr/server.py` validates hashes against `sha256-[A-Za-z0-9+/]{43}=`, quotes accepted values and emits `style-src 'self' '<hash>'; script-src 'self'` within the full CSP. It authorizes that exact stylesheet; no `unsafe-inline` allowance is introduced. Dependency updates must regenerate the policy from installed content rather than blindly retaining this hash. Runtime CSP proof remains separate from this source/hash inspection.

Selecting a file leaves the two panes visible; there is no automatic jump to the recipe. View changes focus the main landmark without scrolling. Official controls inherit fast/medium motion (125ms/250ms) and standard easing. Global reduced-motion CSS shortens animations/transitions to `.01ms` and restores automatic scrolling. No former custom 200ms view-entry animation exists in current source.

## Do's and Don'ts

### Do:

- **Do** keep actions and focus blue with dark text on filled blue buttons in both themes.
- **Do** use neutral surfaces, thin dividers and the approved control/panel shape hierarchy; record source drift honestly.
- **Do** preserve official control semantics, visible focus, wrapping paths and the 44px minimum interactive target.
- **Do** pair semantic status indicators with readable words and accessible text.
- **Do** continue a completed preview from its job row using the saved settings.
- **Do** honor system light/dark preference and reduced motion.
- **Do** compile the hand-authored theme and regenerate selector policy with the pinned dependency.

### Don't:

- **Don't** turn status colors into additional action colors.
- **Don't** add decorative charts, fake activity, gradients or glass to this quiet workspace.
- **Don't** make ordinary inline tasks depend on a decorative modal or nested card stack.
- **Don't** imply that processing replaces the library original.
- **Don't** treat screenshots, device names or mocked capabilities as GPU/AI readiness evidence.
- **Don't** promote redundant eyebrows, Unicode icon substitutes or one-off brand measurements into reusable system tokens.
- **Don't** edit generated theme/bundle output or extract active tokens from the removed legacy UI.
- **Don't** declare accessibility, target sizing or release checks passed from this documentation pass.

## Single-workspace review — 2026-10-13

Reviewed the actual generated-media CPU app at 1440 light and 390 dark, with a 768 dark layout check. The final view has input/queue columns, settings below, no sidebar/dashboard, truthful status and the family mark. Originals remain separate. Eight browser workflows passed, including direct Add to queue, a real downloaded CPU copy, saved settings/input across setup, preview-to-full continuation, pairing, keyboard/CSP/44px label target checks and all existing optional GPU-control contracts. An additional explicit-DLSS capability-loss regression verifies that an unavailable selected engine blocks submission instead of becoming conventional resizing. GPU fixtures remain labeled and do not prove GPU execution.

The initial render check found the removed shell no longer supplied an explicit theme background; the new shell now does. The interactive checkbox label now has a real 44px clickable area, exercised at its edge. Axe scans the actual frame-free page directly because its separate analysis page can resolve system-theme colors differently after emulation; no contrast rule is disabled. The review was performed in this thread. Verdict: the simpler UI is ready for development main; 4K delivery/recovery, representative movie quality and external-drive acceptance remain separate. No additional polish loop or release promotion.

2026-10-13 worker update extension: preserves Astryx and the main input/queue/settings workspace. Devices & storage adds current worker version, one Check for updates action, idle/replacement/validation/restored states and an accessible live status. Desktop/light and mobile/dark rendered fixtures were inspected; update/rollback states are explicitly simulated. Eleven browser workflows, Axe and overflow checks pass. Mechanical detector retains only incumbent advisories; no new update token or composition system. This design review does not prove container replacement or a GPU update.
