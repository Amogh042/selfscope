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
