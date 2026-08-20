# Handoff: Rapha portal redesign

## Overview

A visual redesign of the Rapha local portal (`src/rapha/dashboard/portal.py`, served by
`rapha serve` on `127.0.0.1:8766`). Same information architecture, same six tabs, same
briefing keys — new visual system: warm off-white/near-black surfaces, editorial type,
chart-led layout, two accents.

The design was driven by one question the owner wants answered first: **"am I actually
improving?"** Hence the Performance tab leads with a large metric-selectable trend chart
(daily line + 7-day rolling + personal baseline band + previous-window average), and every
delta is stated against the previous equal-length window rather than shown bare.

Nothing was removed from the current portal. Every card in `portal.py` has a counterpart.

## About the design files

`Rapha Portal.dc.html` in this bundle is a **design reference created in HTML** — a
prototype showing intended look and behaviour with synthetic data. It is not production code
to copy.

The target environment already exists and is unusual, so read this carefully:

- The portal is **server-rendered Python**: `portal.py` is a pure function `briefing dict →
  one self-contained HTML string`. No framework, no build step, no npm — stdlib only, per the
  project's constraints (`CLAUDE.md`), and it must work with no network (ADR-009).
- Therefore: **do not introduce React/Vue/Tailwind/a bundler.** Implement the redesign by
  rewriting the `CSS` constant and the card/tab f-strings inside `portal.py`, keeping its
  existing function boundaries (`_today_tab`, `_vitals_card`, `_coach_card`, `_training_tab`,
  `_meals_tab`, `_performance_tab`, `_progress_tab`, `_data_status_tab`, `render`).
- The prototype uses inline styles because of the tool it was authored in. In `portal.py`,
  **use classes and the `CSS` constant** as it does today — that is the better fit and keeps
  diffs readable. Translate, don't transliterate.
- Keep `portal.py` pure and credential-free. It must never import `rapha.garmin` (ADR-001).
- Keep the existing vanilla-JS behaviours in the `JS` constant working: `tab()`,
  `perfRange()`, `_drawLine()`, `_drawIntraday()`, `copyGarmin()`, `uploadPhotos()`,
  `toggleMeasForm()`, `saveMeasurement()`, `togglePhotos()`, `openLightbox()`,
  `refreshStatus()`, `forcePull()`, `launchChrome()`. The redesign changes markup and CSS,
  not the endpoints or the JS contract.

## Fidelity

**High-fidelity.** Final colors, type, spacing and layout. Recreate faithfully. Where the
prototype's synthetic content differs from a real briefing value, the briefing wins — the
prototype's numbers are invented (no real health data may enter the repo; see README's data
boundary and `DECISIONS.md` ADR-002).

## Design tokens

Two themes from one token set. Light is the default; dark follows
`prefers-color-scheme` (the current portal does the reverse — dark-first with a light
override; either direction is fine as long as both themes ship).

All colors are `oklch()`. Keep them as `oklch()` — do not convert to hex; the palette was
built for perceptual consistency (both accents share lightness and chroma, differing only in
hue).

```css
:root {
  color-scheme: light dark;
  /* surfaces */
  --bg: oklch(0.968 0.008 85);          /* page */
  --panel: oklch(0.995 0.004 90);       /* card */
  --inset: oklch(0.975 0.008 85);       /* stat tile / input / code block inside a card */
  --stripe: oklch(0.93 0.008 82);       /* photo-placeholder hatching */
  /* lines */
  --line: oklch(0.88 0.010 80);         /* card border, nav underline track */
  --line2: oklch(0.90 0.010 80);        /* tile border */
  --row: oklch(0.92 0.008 82);          /* table row rule, list divider */
  --line-strong: oklch(0.85 0.010 80);  /* secondary button border, dashed code frame */
  --axis: oklch(0.82 0.010 80);         /* chart baseline */
  --scroll: oklch(0.85 0.010 80);
  /* text */
  --ink: oklch(0.24 0.015 60);          /* headings, numbers */
  --ink2: oklch(0.30 0.014 62);         /* emphasis body */
  --ink3: oklch(0.40 0.014 65);         /* body */
  --ink4: oklch(0.47 0.014 65);         /* secondary body */
  --dim: oklch(0.52 0.012 70);          /* labels, eyebrows */
  --dim2: oklch(0.61 0.012 70);         /* axis ticks, footnotes */
  /* accents — accent = primary/attention, accent2 = good/stable/comparison */
  --accent: oklch(0.60 0.13 45);
  --accent-hover: oklch(0.48 0.13 45);
  --accent2: oklch(0.60 0.13 215);
  --bad: oklch(0.45 0.15 30);
  --on-accent: oklch(0.99 0.004 90);    /* text on an accent fill */
  --on-ink: oklch(0.975 0.008 85);      /* text on an ink fill */
  /* fills */
  --accent-soft: oklch(0.60 0.13 45 / 0.10);   /* pill bg, active tab bg, sparkline area */
  --area: oklch(0.60 0.13 45 / 0.13);          /* hero chart area */
  --band: oklch(0.24 0.015 60 / 0.06);         /* baseline ±1σ band */
  --trend: oklch(0.24 0.015 60 / 0.45);        /* 7-day rolling stroke */
  --stage-rem: oklch(0.60 0.13 215 / 0.55);
  --stage-light: oklch(0.60 0.13 215 / 0.22);
  --bar: oklch(0.60 0.13 215 / 0.75);          /* weekly tonnage bars */
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: oklch(0.185 0.006 70); --panel: oklch(0.225 0.007 70); --inset: oklch(0.265 0.008 70);
    --stripe: oklch(0.31 0.008 70); --line: oklch(0.33 0.008 70); --line2: oklch(0.31 0.008 70);
    --row: oklch(0.29 0.008 70); --line-strong: oklch(0.37 0.009 70); --axis: oklch(0.42 0.010 70);
    --scroll: oklch(0.38 0.008 70);
    --ink: oklch(0.95 0.006 85); --ink2: oklch(0.90 0.006 85); --ink3: oklch(0.82 0.006 82);
    --ink4: oklch(0.75 0.006 80); --dim: oklch(0.69 0.006 78); --dim2: oklch(0.62 0.006 78);
    --accent: oklch(0.74 0.13 48); --accent-hover: oklch(0.82 0.11 48);
    --accent2: oklch(0.74 0.11 215); --bad: oklch(0.70 0.15 30);
    --on-accent: oklch(0.17 0.006 70); --on-ink: oklch(0.17 0.006 70);
    --accent-soft: oklch(0.74 0.13 48 / 0.16); --area: oklch(0.74 0.13 48 / 0.16);
    --band: oklch(0.95 0.006 85 / 0.08); --trend: oklch(0.95 0.006 85 / 0.45);
    --stage-rem: oklch(0.74 0.11 215 / 0.55); --stage-light: oklch(0.74 0.11 215 / 0.28);
    --bar: oklch(0.74 0.11 215 / 0.75);
  }
}
```

**Semantics to preserve.** The current portal maps recovery to green/amber/red. The redesign
deliberately has no green: `--accent2` (blue) = good/stable/fresh, `--accent` (rust) =
attention/caution/primary series, `--bad` (deep rust) = bad/stale. Keep that mapping
consistent — it is what stops the page reading like a generic dashboard.

### Type

Google Fonts, loaded with a `<link>` (offline caveat below):

- **Archivo** 400/500/600/700 — everything structural. Headings 600, letter-spacing
  `-0.02em` to `-0.035em` at large sizes. Numbers 600.
- **IBM Plex Mono** 400/500 — labels, eyebrows, axis ticks, table headers, metadata, code
  block. Always uppercase for labels, `letter-spacing: 0.06em`–`0.2em`, sizes 9–12px.
- `font-feature-settings: 'tnum' 1` on the root so numbers don't jitter between renders.

Scale actually used (px unless noted):

| Role | Size | Family / weight |
|---|---|---|
| Page title ("Day 34 of 60") | `clamp(28, 3.6vw, 44)` | Archivo 600, `-0.025em` |
| Hero metric number | `clamp(48, 6.4vw, 76)` | Archivo 600, `-0.035em`, line-height 0.9 |
| Section h2 (card title, tab head) | 10, uppercase | Plex Mono 500, `0.16em` |
| Big statement (recovery headline, status) | `clamp(26, 3.2vw, 38)` | Archivo 600 |
| Stat tile number | 20–26 | Archivo 600, `-0.02em` |
| Body | 14–16, line-height 1.5–1.6 | Archivo 400 |
| Table cell | 14 | Archivo 400 |
| Table header | 10, uppercase | Plex Mono 500, `0.12em` |
| Axis tick / footnote | 9–10 | Plex Mono 400 |

⚠️ **Offline**: ADR-009 says the page must work with no network. A Google Fonts `<link>`
breaks that promise (it degrades to the fallback stack, which is acceptable but not
intended). Either self-host both families as `woff2` under `%RAPHA_HOME%/dist/fonts/` and
`@font-face` them from the `CSS` constant — preferred, and `build.py` already stages files
into `dist` — or accept the fallback `Helvetica, sans-serif` / `ui-monospace`. Decide
explicitly; don't leave it to chance.

### Geometry

- Page max width **1180px**, gutters `clamp(14px, 3vw, 32px)`.
- Card: `1px solid var(--line)`, radius **4px**, padding `clamp(16px, 1.8vw, 24px)` (hero
  cards `clamp(18px, 2vw, 28px)`). **No shadows** — hairlines only. Tiles inside cards:
  radius 3px.
- Vertical rhythm between cards: `clamp(12px, 1.4vw, 18px)`.
- Pills/buttons: radius 999px, padding `10px 18px`, Plex Mono 11px uppercase `0.06em`.
- Accent left-border for editorial callouts: `3px solid` (coach card `--accent`, programme
  update `--accent2`, session adjustment `--accent`, meals `2px solid var(--accent)`).
- Responsive without media queries: `clamp()` for type/padding and
  `grid-template-columns: repeat(auto-fit, minmax(Npx, 1fr))` for every tile row
  (`minmax` 120px for compact stats, 150px standard, 200–330px for cards). Wide tables sit in
  `overflow-x: auto`. This is why the same markup works on phone and desktop.

## Shell

**Header** (`render`): recovery dot (9px, `--recoveryColor`) + `RAPHA · PROJETO 60 DIAS`
eyebrow; `Day {day_of_60} of 60` as the page title with "of 60" in `--dim2` 400;
metadata line `{athlete} · sheet {sheet_number} · week {week} of 8 · built {generated}`.
Right-aligned: live freshness (`● data is current · 23 min`, colored by `data_status.fresh`)
and `macro-first recomposition`.

**Nav**: underline tabs, not pills. `Plex Mono 11px uppercase 0.1em`, inactive `--dim`,
active `--ink` with a `2px solid var(--accent)` bottom border, on a `1px solid var(--line)`
track. Horizontally scrollable, keeps the current `tab()` JS. **Data Status keeps its health
coloring** (`statusok`/`statusbad` → `--accent2`/`--bad`).

**Footer**: two Plex Mono 10px uppercase lines — the disclaimer
("observations against projeto 60 dias · not medical advice") and
"local-first · 127.0.0.1 · no credential in the portal".

## Screens / views

Each maps 1:1 onto an existing function. Briefing keys named below are the ones already
produced by `dashboard/briefing.py`.

### 1. Today — `_today_tab`, `_vitals_card`, `_coach_card`

1. **Recovery card** (hero). Left: eyebrow `RECOVERY`, then
   `overview.recovery.headline` as a `clamp(28,3.2vw,38)` statement colored by status, plus a
   one-paragraph plain-language read. Right column: the `overview.recovery.signals` list, one
   row per signal — label + `↑ higher is better`/`↓ lower is better` (from
   `higher_is_better`) on the left; `note` in 14/600 colored by `good` (true → `--accent2`,
   false → `--bad`, null → `--accent`) with `recent` beneath in Plex Mono 10 on the right;
   `1px solid var(--row)` divider between rows. Replaces today's `.pill` + `.sig` treatment.
2. **Overnight card** — `vitals`. Three tiles: `sleep_score`, Body Battery `low–high`,
   `hrv_status` title-cased. Then sleep stages as a **single 14px-tall proportional bar**
   (flex-grown by minutes: deep `--accent2`, rem `--stage-rem`, light `--stage-light`, awake
   `--line`) with a **separate wrapping legend** below (10px swatch + `deep 1h04`).
   ⚠️ Do not put the stage labels inside the proportional columns — a short stage clips its
   own label. This was found and fixed in review; keep the split.
3. **Programme update** — `overview.sheet_switch`, only when `days_until <= 10`. Callout with
   `--accent2` left border; same "today/tomorrow/in N days" phrasing.
4. **Coach card** — `coach`. `--accent` left border, paragraphs at 16/1.6, max width `68ch`,
   attribution line in Plex Mono 10. Keep the authored-vs-templated logic and the stale note
   exactly as `_coach_card` has it (including `_md_lite` for authored markdown).
5. **Train / Eat** — two cards in an `auto-fit minmax(300px)` grid. Train: `Day {day} ·
   {focus}`, metadata line, truncated `progression`. Eat: `{target_kcal} kcal · {protein_g} g
   protein`, direction pill (`--accent-soft` fill), first meal line.

### 2. Training — `_training_tab`

- Header row: `focus` as an h2 `clamp(22,2.4vw,28)`, right-aligned `{level} · day {day}`.
- **Adjustment banner** (`training.adjustment`): left border colored by `readiness`
  (green→`--accent2`, amber→`--accent`, red→`--bad`), `--inset` fill, headline 15/600,
  `Leave {reps_in_reserve}` in Plex Mono 11, `detail` below.
- **Exercise rows**, one per `training.exercises[]`, separated by `--row`: name 16/600;
  `{sets} sets · reps {scheme}` Plex Mono 11 `--dim`; the **progression call** in 14/600
  colored by decision (progress→`--accent`, hold→`--accent2`, establish→`--dim2`) using the
  exact strings `_call_line` builds (`↗ Try 32 kg (last 30 kg × 10)`, `→ Hold 22 kg today
  (recovery)`, `↗ Add reps / harder variation`, `○ Find your working load`); `call.reasoning`
  at 13/1.45 `--ink4` max `62ch`; `method` label+cue in Plex Mono 11 `--accent2`; issues in
  `--bad`. Right column: `{rest_s}s rest`, `white-space: nowrap`.
- Progression and Cadence notes as labelled paragraphs (keep the M15/M17 wording).
- **Garmin card**: help paragraph, then the sheet in a `<pre>` — `--inset` fill, `1px dashed
  var(--line-strong)`, Plex Mono 12/1.75, `white-space: pre-wrap`, `overflow-x: auto`. Then
  the primary Copy button (`--accent` fill, label swaps to `Copied ✓` for 1.6s — existing
  `copyGarmin()`), plus secondary outline links to `/workouts.md` and `/workouts.json`.

### 3. Meals — `_meals_tab`

- **Targets card**: four `--inset` tiles (`actual_kcal` with `target {target_kcal}` as the
  label, `actual_protein_g`, `carb_g`, `fat_g`), direction pill + `measured TDEE {tdee_kcal}
  kcal · {deficit_pct}% deficit` in Plex Mono, then `direction_why` and `split`.
- **Meals card**: one block per `meals.meals[]` with a `2px solid var(--accent)` left border —
  head line `{time} · {kcal} kcal · {protein_g} g protein` in Plex Mono 11 `--accent`, label
  16/600, then items as `**{grams} g** {food} · {kcal} kcal` (grams `--ink`, food `--ink3`,
  kcal Plex Mono 11 `--dim2`), and the free additions in 13 `--accent2`.
  Note: this replaces `<ul>` bullets with a flex column + gap.
- **Supplements** and **How to use it** side by side (`auto-fit minmax(320px)`). Supplements:
  `{name} — {dose}` 15/600, `when` 13 `--ink4`, `source` Plex Mono 10 `--dim2`. Principles:
  em-dash bullets in `--accent` + text.

### 4. Performance — `_performance_tab`, `_volume_card`, `_load_card`, `_intraday_card`,
`_progression_card`

**New leading card — the trend hero.** This is the main addition; everything else on the tab
already exists.

- Metric selector: five outline buttons (HRV, Resting HR, Sleep, Energy burned, Weight);
  active = `--accent-soft` fill, `--accent` text and border.
- Big window average + unit; delta vs the previous equal-length window as
  `clamp(22,2.6vw,30)` colored `--accent` when moving the good way (respect
  lower-is-better for RHR and weight), plus a one-sentence verdict naming both averages, the
  day counts and σ.
- Chart, height `clamp(200px,24vw,280px)`: y-axis labels in a 46px Plex Mono column (max /
  mid / min); plot area with `--line2` top rule, `--axis` bottom rule, a dotted mid-line;
  `<svg viewBox="0 0 1000 100" preserveAspectRatio="none">` containing, in paint order —
  area `--area`, baseline ±1σ band `--band`, 7-day rolling line `--trend` `stroke-dasharray
  5 4`, daily line `--accent` `stroke-width 2`. Every stroke needs
  `vector-effect="non-scaling-stroke"` because the viewBox is stretched.
  A `prev avg {value}` chip sits at the previous-window average height: **absolutely
  positioned HTML, emitted after the `<svg>`, `z-index: 2`, `--panel` background** — put it
  before the SVG and the plot paints over the digits (found in review).
  x-ticks: 5 dates below, Plex Mono 10.
- Reuse the existing `window.PERF` payload and `perfRange()`/`_drawLine()` machinery; the
  hero is one more consumer of the same series.

Then, in order: **Snapshot** (vo2max, strength/cardio sessions, typical start),
**Volume & adherence** (four stat tiles; 12-week tonnage bars `--bar`, height ∝ tonnage,
labels Plex Mono 8; note; four adherence tiles — keep labels short, `+5.7 t` / `vs 12 wks
ago`, `today`, or the tiles wrap unevenly), **Load balance** (ACWR as a 44px number colored
by band + band name, `acute` / `4-wk weekly avg` / `sweet spot 0.8–1.3` in Plex Mono, the
existing explanatory note and the `reliable == false` caveat), **Day · heart rate**
(bpm range + intraday sparkline, 00:00–24:00 ticks), **Trends over time** (7D/30D/90D/1Y/All
segmented control, ink fill on active; the note about short lines; then the seven metric
cards — label, direction tag, value, delta, sparkline, `avg over N readings`),
**Load progression** (table: exercise / sess. / top set / trend ▲▼→ / 120×26 sparkline; the
"showing the N most-trained of M" note), **Recent sessions** (date / type / time / avg HR /
kcal, numerics right-aligned).

### 5. Progress — `_progress_tab`, `_measurements_card`

- **Body composition**: four tiles (weight, body fat %, biotype, somatotype) + `bodyfat_source`.
- **Weight trend**: `progress.weight_view` — weigh-ins as a solid `--accent` line over
  `--area` fill, the trend estimate as a `--trend` dashed line, both on one date axis
  (`viewBox="0 0 600 100"`). Legend row: from-date, `weigh-ins` / `– – – trend estimate`,
  to-date. Then the latest/count summary and `trend_note`.
- **Measurements**: latest values as tags (`--inset`, Plex Mono 11), tape/biotype line, then
  `CHANGE SINCE YOU STARTED MEASURING` with per-attr tags colored by direction —
  `_LOWER_IS_BETTER` (waist, hip) inverts, good → `--accent`, wrong-way → `--accent2`.
  Ink-filled toggle button reveals the form: `auto-fill minmax(130px)` grid of ten numeric
  inputs (`--inset` fill, `--line` border, Plex Mono 14) prefilled with the latest values,
  date + notes fields, `--accent` Save button, status text in `--accent2`. Keep
  `saveMeasurement()` POSTing to `/measurement` and the reload-after-save.
- **Progress photos**: `--accent` upload label wrapping a hidden file input
  (`uploadPhotos()`), outline Show/Hide toggle (`togglePhotos()`), then per-date sets — date
  eyebrow, the written analysis in an `--accent`-bordered `--inset` callout (or the "analysis
  pending" note), and a `auto-fill minmax(140px)` grid of 3:4 images, click-to-lightbox.
  In the prototype the images are **hatched placeholders with monospace captions** because
  real photos never leave the machine; wire the real `/photos/<date>/<file>` sources.

### 6. Data Status — `_data_status_tab`

Four cards, all existing content: **status** (dot + `Data is current`/`Data is stale`/`No
pull recorded yet` as a `clamp(26,3vw,34)` statement + sub-line), **last Garmin pull**
(`When` / `Age` tiles in Plex Mono 18, the "last pull brought in" counts, `Pull now` primary
button + status text, the freshness-rule paragraph), **browser session** (`● {state}` colored
by `chrome_up`, outline launch button, the never-sees-your-password explanation), and **how
refresh works** (four em-dash bullets). Keep `refreshStatus()` polling `/pull-status` every
60s and `forcePull()`'s 4s × 30 poll loop unchanged.

## Interactions & behavior

Everything is client-side except the three existing POSTs.

| Interaction | Behavior |
|---|---|
| Tab click | Show one `.tab`, mark nav active, `scrollTo(0,0)` — unchanged |
| Hero metric select | Recompute average, delta, verdict, chart paths from `window.PERF` |
| Range select (7D–All) | Filter every series by cutoff, redraw sparklines + hero; label swap on the active control |
| Copy workout | Clipboard write, button label → `Copied ✓`, revert after 1.6s |
| Measurement save | POST `/measurement`, then reload; blank fields keep last value |
| Photo upload | POST `/upload/photo` per file with `X-Filename`, then reload |
| Pull now | POST `/pull-now`, poll `/pull-status` every 4s up to 30 times, live dot + text |
| Launch Chrome | POST `/launch-chrome`, re-check status after 3s |
| Lightbox | Click photo to open, click/Escape to close |
| Hover | Buttons: border and text to `--accent`. Cards are not hover-lifted |

No entrance animations, no card transitions. The current 0.2s tab fade is fine to keep.

## State

Server-side: none — `portal.py` stays pure, state lives in the briefing.
Client-side, same as today: active tab, active range, upload/save/pull status strings, live
pull status from `/pull-status`, lightbox open. The prototype additionally holds the hero
metric selection — add it as a plain module-level variable in the `JS` constant.

## Empty and error states

Preserve every existing fallback: "Nothing extracted yet — run `rapha extract`",
"No Garmin data yet", "not enough data in this range" for short series, "No intraday data
pulled yet", "No weigh-ins yet", "No measurements yet", "Analysis pending", the
`reliable == false` ACWR caveat, and the unusable-diet-models warning. Style them as
`--dim2` 13px italic-free notes; keep the `<code>` command hints (`--inset` chip, Plex Mono).

## Accessibility

- Nav should be real `<button>`s (it already is); the underline-active state carries a color
  change too, so it isn't color-only.
- The status dot is always paired with text — never the dot alone.
- Body text at 14px minimum against `--panel`; the `--dim`/`--dim2` pair on `--panel` and
  `--inset` clears 4.5:1 in both themes. If you re-tune any token, re-check that pair first.

## Assets

None. No images, no icon font, no SVG illustrations. Arrows and marks are text characters
(`↑ ↓ ↗ → ○ ● ▲ ▼ – –` and `✓`), which is deliberate — keep them as text.

## Files in this bundle

- `Rapha Portal.dc.html` — the design reference. Opens directly in a browser; interactive
  (tabs, metric/range selectors, copy, measurement form, pull-now simulation). Contains
  synthetic data only.
- `README.md` — this document.

Source of truth for the current implementation: `src/rapha/dashboard/portal.py`,
`src/rapha/dashboard/render.py`, `src/rapha/dashboard/build.py`, `src/rapha/server.py`.

## Suggested order of work

1. Replace the `CSS` constant: tokens, both themes, base/type, card/tile/table/pill/button
   primitives. Reload the existing markup — most of it will already look close.
2. Shell: header, underline nav, footer.
3. Tab by tab, top to bottom: Today → Training → Meals → Performance → Progress → Data
   Status. `_stat()` and the other small helpers can keep their signatures.
4. Performance hero last — it is the only genuinely new component.
5. `pytest` (`tests/unit/test_data_status_tab.py`, `test_weight_view.py`, `test_server.py`
   assert on portal output — expect to update assertions where markup changed, not to
   loosen them), then `ruff check .`, then `rapha report && rapha serve` and compare against
   the prototype in both light and dark.
