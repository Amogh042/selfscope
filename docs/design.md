# SelfScope design system

Black + orange pixel/arcade UI, in the spirit of a blocky game menu. Tokens live in
`web/src/index.css` under `@theme` (Tailwind v4), so every value below is a utility class.

## Colour

| Token | Hex | Utility | Use |
|---|---|---|---|
| bg | `#0D0D0D` | `bg-bg` | Page background |
| panel | `#1A1A1A` | `bg-panel` | Panels, cards |
| orange | `#FF7A00` | `text-orange`, `border-orange` | Primary: borders, headings, buttons |
| orange-dark | `#A84E00` | `shadow-block`, `border-orange-dark` | Hard offset block shadow, inner frames |
| orange-light | `#FFB066` | `text-orange-light` | Hover, code, loading state |
| xp | `#5FD35F` | `text-xp`, `bg-xp` | Success, "ready", progress (XP bar) |
| text | `#F2F2F2` | `text-text` | Body text |
| muted | `#9A9A9A` | `text-muted` | Labels, secondary text |
| danger | `#FF4D4D` | `text-danger` | Errors only |

The default Tailwind palette is removed (`--color-*: initial`) so only these colours exist.

## Type

- **Headings** — `Press Start 2P` (`font-pixel`). Use small sizes (9–12px for labels, 24–30px for the title); it is very wide.
- **Body** — `Inter` (`font-sans`, the default).
- **Data, labels, code, numbers** — `JetBrains Mono` (`font-mono`), with `tabular-nums` for figures.

Fonts load from Google Fonts in `web/index.html` (fonts only — no user data is sent).

## Shape

- **Square corners everywhere.** All `rounded-*` utilities are removed and a base rule forces `border-radius: 0`.
- **Borders:** 2px, orange by default (`border` = 2px orange).
- **Shadows:** hard offset blocks, never blurred — `shadow-block-sm` (2px), `shadow-block` (4px), `shadow-block-lg` (6px), all in orange-dark.

## Components (`web/src/components/pixel.tsx`, `index.css`)

- `.pixel-panel` / `<Panel>` — panel bg, 2px orange border, 4px block shadow, header bar with pixel title.
- `.pixel-btn` — orange block button; on press it moves 4px into its shadow (stepped, no easing).
- `<StatusBadge>` — idle (muted) / loading (light orange, blinking) / ready (XP green) / error (danger).
- `<XpBar>` — 20-segment green progress bar.
- `<Terminal>` — monospace output box with orange-dark frame.

## Motion

Stepped only (`steps(1)`): blinking cursors, button presses. No easing curves, no fades.
Respect `prefers-reduced-motion`.

## Data colours (one per source, everywhere)

| Source | Token | Hex | Utility |
|---|---|---|---|
| Music (Spotify) | `music` | `#56B4E9` sky blue | `text-music`, `border-music` |
| YouTube | `youtube` | `#CC79A7` reddish purple | `text-youtube` |
| Chats (WhatsApp) | `chats` | `#009E73` bluish green | `text-chats` |
| Money (bank) | `money` | `#F0E442` yellow | `text-money` |
| Chart grid | `grid` | `#2E2E2E` | `border-grid` |

From the Okabe–Ito palette, which stays distinguishable with the common kinds of colour blindness;
none of them is orange, so **orange stays the accent** (UI chrome, highlights, trend lines, "rise
together" in the matrix). A source is always drawn in its colour: KPI tiles, panel frames, timeline
lines, chips, the pixel source icons. Categories *inside* one chart (moods, topics, spend categories)
use lightness steps of that source's colour (`SHADES` in `src/lib/sourceStyle.ts`, biggest category
brightest) and a dim grey for "other" / "rest", so they never look like another source.
In TypeScript, read colours with `colors()` / `sourceColor()` (they come from these CSS tokens).

## Charts (Apache ECharts, `src/components/charts/Chart.tsx`)

- **Square everything:** bars with no rounding, square markers (`symbol: 'rect'`), no gradients, no
  shadows inside charts, no animation.
- **Thin muted grid lines** (1px `grid`), muted axis labels; **JetBrains Mono** for every number and label
  in a chart; **Press Start 2P only for section headings** (in HTML, never inside a chart).
- **Every chart has:**
  1. a **title that states the takeaway**, computed from the data ("Sad songs peak around 02:00 (55% …)"),
     drawn inside the canvas so it is in the PNG;
  2. **axis units** (₹, min, %, count, "mood −1…1");
  3. a **tooltip with exact values** (square swatch, mono, 2px orange border, hard shadow);
  4. an **empty state** ("No data in this range", dashed frame) and a **loading state** (blinking
     "LOADING…"); a source that was never imported shows "Import <source> to unlock this panel";
  5. a **save-as-PNG** button (toolbox, 2× pixel ratio, panel background).
- Charts are created when scrolled near the viewport and resize with their box. Wide charts (the
  correlation matrix) scroll inside their own box; the page never scrolls sideways.
- Diverging scales (correlations): orange = positive, white = negative, panel colour = 0; non-significant
  cells are flat grey with no label.
- Sequential scales (heatmaps, calendar): panel colour → the source colour.
