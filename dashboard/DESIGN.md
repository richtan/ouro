# Ouro Dashboard Design System

This is the single source of truth for all UI decisions in the Ouro dashboard. Any new feature, page, or component must follow this document exactly.

## Philosophy

**Base-inspired. Clean. Confident. Professional.**

- Grayscale-dominant with blue used sparingly for maximum impact
- Strong typographic hierarchy — you know what's important at a glance
- Generous whitespace — every element earns its place
- No visual noise — no glow effects, no gradients, no animated textures
- Data-first — the UI serves the data, not the other way around

The dashboard should feel like it belongs in the Base ecosystem: premium, trustworthy, and intentional.

---

## Color Palette

All colors are defined as Tailwind tokens under the `o` namespace in `tailwind.config.ts`.

### Backgrounds

| Token | Hex | Usage |
|---|---|---|
| `bg-o-bg` | `#0a0b0d` | Page background (Base Gray 100) |
| `bg-o-surface` | `#111316` | Card and panel surfaces |
| `bg-o-surfaceHover` | `#191b1f` | Hover state for interactive surfaces |

### Borders

| Token | Hex | Usage |
|---|---|---|
| `border-o-border` | `#1e2025` | Default borders on cards, inputs, dividers |
| `border-o-borderHover` | `#32353d` | Focus/hover borders (Base Gray 80) |

### Blues (Primary Accent)

| Token | Hex | Usage |
|---|---|---|
| `bg-o-blue` | `#0052ff` | Primary button fills, key indicators |
| `bg-o-blueHover` | `#0045d6` | Button hover/press state |
| `text-o-blueText` | `#4C8FFF` | Links, highlighted text, active nav items. Passes AA contrast on `#0a0b0d` (~6:1) |

For muted blue backgrounds, use opacity modifiers: `bg-o-blue/10`, `bg-o-blue/20`, etc. Do NOT create separate muted tokens.

### Text

| Token | Hex | Usage |
|---|---|---|
| `text-o-text` | `#f5f5f5` | Primary text (headings, values, body) |
| `text-o-textSecondary` | `#8a919e` | Labels, descriptions, secondary info |
| `text-o-muted` | `#5b616e` | Timestamps, disabled text, scale markers (Base Gray 60) |

### Semantic Colors

| Token | Hex | Usage |
|---|---|---|
| `text-o-green` / `bg-o-green` | `#22c55e` | Success, completed, positive values |
| `text-o-red` / `bg-o-red` | `#ef4444` | Error, failed, negative values |
| `text-o-amber` / `bg-o-amber` | `#eab308` | Warning, pending, caution |

Muted semantic backgrounds use opacity: `bg-o-green/10`, `bg-o-red/10`, `bg-o-amber/10`.

---

## Typography

### Font Stack

Fonts are loaded via the `geist` npm package in `layout.tsx` and exposed as CSS variables.

| CSS Variable | Font | Tailwind Class | Purpose |
|---|---|---|---|
| `--font-geist-sans` | Geist Sans | `font-sans`, `font-display`, `font-body` | All text: headings, body, labels, nav links |
| `--font-geist-mono` | Geist Mono | `font-mono` | Job IDs, wallet addresses, prices, terminal output, code |

Geist is Vercel's modern sans-serif typeface. It provides a clean, geometric feel with excellent readability at all sizes. `font-display` and `font-body` are aliases for `font-sans` (all resolve to Geist Sans).

### When to Use `font-mono`

`font-mono` (Geist Mono) is strictly reserved for **data that benefits from monospaced rendering**:

- **Use mono**: Job IDs, Slurm IDs, wallet addresses, tx hashes, SHA-256 hashes, dollar amounts/prices, builder codes, `<pre>` code/script blocks, terminal/log output, decoded data values, table data cells in structured logs
- **Never use mono**: Buttons ("Upload File", "Decode", "Sign out", "Copy"), status badges ("completed", "running"), UI labels ("Self-Sustaining", "Three Revenue Streams", "DUAL"), error messages, navigation links, summary text ("42 total", "3 jobs for..."), any human-readable label or CTA

Buttons and badges should use `font-sans` (inherited by default) with `font-medium` or `font-semibold` for visual weight instead.

### Sizing Hierarchy

| Element | Size | Class | Font | Additional |
|---|---|---|---|---|
| Page heading | 24px mobile / 30px desktop | `text-2xl md:text-3xl` | `font-display font-bold` | `tracking-tight` |
| Section heading | 18px | `text-lg` | `font-display font-bold` | — |
| Stat value | 24px | `text-2xl` | `font-display font-semibold` | `tracking-tight` |
| Stat label | 12px | `text-xs` | `font-body` | `uppercase tracking-wider text-o-textSecondary` |
| Body text | 14px | `text-sm` | `font-body` | — |
| Code / data | 12px | `text-xs` | `font-mono` | — |
| **Minimum text** | **12px** | **`text-xs`** | — | NEVER use `text-[10px]` or smaller |

### Letter Spacing

- Display headings at `text-xl` and above: `tracking-tight` (-0.02em)
- Stat labels and status badges: `tracking-wider` (0.05em) + `uppercase`
- Body text: default tracking

---

## Component Patterns

### Card

The base building block. Defined in `globals.css`:

```css
.card {
  @apply bg-o-surface border border-o-border rounded-xl p-5 transition-colors duration-150;
}
.card:hover {
  @apply border-o-borderHover;
}
@media (max-width: 640px) {
  .card { @apply p-4 rounded-lg; }
}
```

Rules:
- NO `::before` pseudo-elements
- NO gradients
- NO glow effects
- NO noise textures

### Stat Sub-Cards

Metric boxes inside cards (e.g., per-job economics, grid stats):

```html
<div class="bg-o-bg rounded-lg p-3 border border-o-border">
  <div class="text-xs text-o-textSecondary uppercase tracking-wider">Label</div>
  <div class="font-display text-xl font-semibold text-o-text mt-1">Value</div>
</div>
```

Use `bg-o-bg` (page background) for the inset effect. NEVER use `bg-black/30`.

### Buttons

**Primary (CTA):**
```html
<button class="px-6 py-3 bg-o-blue text-white font-display font-semibold text-sm rounded-lg hover:bg-o-blueHover transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
  Submit & Pay
</button>
```
On mobile: add `w-full sm:w-auto`.

**Secondary:**
```html
<button class="px-4 py-2.5 bg-o-blue/10 text-o-blueText border border-o-blue/20 rounded-lg text-xs font-mono hover:bg-o-blue/20 transition-colors">
  Action
</button>
```

**Ghost:**
```html
<button class="px-3 py-2 text-xs font-mono text-o-textSecondary hover:text-o-text border border-o-border rounded-lg hover:border-o-borderHover transition-colors">
  Cancel
</button>
```

### Inputs

```html
<input class="w-full bg-o-bg border border-o-border rounded-lg px-3 py-2.5 font-mono text-xs text-o-text placeholder-o-muted focus:outline-none focus:border-o-blueText" />
```

Range sliders: `accent-o-blue`.

### Status Badges

Pill-shaped with semantic colors:

```html
<span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs uppercase tracking-wider font-mono bg-o-green/10 text-o-green">
  <span class="w-1.5 h-1.5 rounded-full bg-o-green"></span>
  completed
</span>
```

Status color mapping:
- `pending` → amber
- `processing` / `running` → blue (with `animate-pulse` on dot)
- `completed` → green
- `failed` → red

### Empty States

Centered in card with descriptive text and a CTA button:

```html
<div class="card text-center py-16">
  <p class="text-o-textSecondary text-sm mb-4">No data yet</p>
  <a href="/submit" class="inline-block px-5 py-3 bg-o-blue text-white rounded-lg text-xs font-mono hover:bg-o-blueHover transition-colors">
    Take action →
  </a>
</div>
```

### Loading States

Use `animate-pulse` on a gray placeholder block:

```html
<div class="card animate-pulse">
  <div class="h-32 bg-o-border/30 rounded"></div>
</div>
```

For spinners: `w-6 h-6 border-2 border-o-border border-t-o-blueText rounded-full animate-spin`.

---

## Layout

### Page Structure

```html
<main class="min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-7xl mx-auto">
  <!-- heading -->
  <!-- content -->
</main>
```

Narrower pages (submit, history, pay): use `max-w-4xl` or `max-w-2xl`.

### Spacing

- Between sections: `mb-6`
- Between heading and content: `mb-6` or `mb-8`
- Inside cards between sections: `mt-5 pt-4 border-t border-o-border`
- Grid gaps: `gap-4` (tight) to `gap-6` (standard)

### Grid Patterns

- 2-column: `grid grid-cols-1 md:grid-cols-2 gap-6`
- 4-stat: `grid grid-cols-2 md:grid-cols-4 gap-4`
- 3-stat: `grid grid-cols-3 gap-4`

### Landing Page (`/`)

The landing page is a standalone marketing page with its own header. The global `NavBar` is hidden on `/` (returns `null` when `pathname === "/"`). The page has its own sticky header with the OURO wordmark and a "Dashboard" link.

Route structure:
- `/` — Landing page (introduces Ouro, CTAs to submit and dashboard)
- `/dashboard` — Operator dashboard (wallet, P&L, stats, attribution)
- `/submit`, `/history`, `/admin`, `/pay/[sessionId]` — App pages (use NavBar)

Design philosophy: **show, don't describe**. The terminal showing the real x402 API flow IS the "how it works" — no description cards. The page is ~2 viewports total, dense with actual information.

Sections (top to bottom):

1. **Header** — Sticky, `bg-o-bg/80 backdrop-blur-md`. OURO wordmark, Dashboard link, GitHub icon, ConnectButton. `h-14`.
2. **Hero** — `font-display` heading (`text-4xl` to `text-6xl`) with `tracking-tight`. One-sentence technical description + two CTAs (primary blue, secondary ghost). Spacing: `pt-24 pb-6 md:pt-32 md:pb-8`. Flows directly into terminal.
3. **Terminal Window** — The centerpiece. Styled terminal with chrome (three dots + "terminal" label) showing the real x402 API conversation: curl request → 402 Payment Required with price headers → 200 OK with job result and proof hash. Uses `bg-o-surface`, `border-o-border`, `rounded-xl`. Lines animate in sequentially via `.terminal-line` class with staggered `animation-delay`. Spacing: `pb-10 md:pb-14`.
4. **Stats Bar** — `border-t` separator + 4 inline stats with tight `gap-x-8`. Values `text-2xl sm:text-3xl` with `tabular-nums`. Always shows "—" placeholder. Spacing: `pt-6 pb-10 md:pt-8 md:pb-14`.
5. **Agent Section** — Label ("For agents", uppercase muted) + heading ("Other agents can buy compute too.") + one sentence about MCP. No cards. Spacing: `pb-10 md:pb-14`.
6. **Footer** — `border-t`, `py-6`. Dashboard and Submit links. "Built on Base".

Max container width: `max-w-5xl`.

---

## Responsive Rules

### Breakpoints (Tailwind defaults)

| Breakpoint | Width | Target |
|---|---|---|
| Default | < 640px | Phone portrait |
| `sm` | ≥ 640px | Phone landscape / small tablet |
| `md` | ≥ 768px | Tablet |
| `lg` | ≥ 1024px | Desktop |

### Mobile-First Approach

Write styles for mobile first, then add `sm:`, `md:`, `lg:` overrides:

```html
<div class="flex flex-col sm:flex-row gap-4">
```

### Touch Targets

**Minimum 44px height** for all interactive elements (per WCAG 2.5.8):

- Buttons: `py-3` minimum
- Nav links: full nav bar height clickable
- Form inputs: `py-2.5` minimum
- Expandable rows: entire row is the button

### What Stacks Where

| Component | Mobile | Desktop |
|---|---|---|
| WalletBalance hero | Vertical (value above sparkline) | Horizontal |
| RevenueModel flow | Vertical with down-arrows | Horizontal with right-arrows |
| History job cards | 2-row header (ID+status, then meta) | Single row |
| JobsPanel | Card layout | Grid with column headers |
| AttributionPanel TXs | Stacked card per TX | Horizontal row |
| AuditPanel | Horizontal scroll | Full table |

---

## Animation

### Allowed

| Animation | Class | Usage |
|---|---|---|
| Fade in | `animate-fade-in` | Page load, initial card entrance |
| Slide up | `animate-slide-up` | Card entrance |
| Pulse | `animate-pulse` | Status dots (running/processing), live indicators |
| Spin | `animate-spin` | Loading spinners |
| Hover transition | `transition-colors duration-150` | Borders, backgrounds |

### NOT Allowed

- `pulse-glow` (breathing opacity)
- `scanline` (moving line)
- `glow-*` text shadows (any)
- Noise texture overlays
- Gradient backgrounds on cards
- `::before` decorative pseudo-elements on cards
- Any animation that draws attention to itself rather than communicating state

---

## Accessibility

- **Minimum text size**: 12px (`text-xs`). Never use `text-[10px]` or smaller
- **Focus rings**: `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-o-blueText/30`
- **Color contrast**: All text passes WCAG AA on its background
- **Semantic HTML**: Use `<nav>`, `<main>`, `<button>`, `<table>` appropriately
- **No focus ring on mouse click** — handled by `focus-visible`
- **Screen reader text** where visual meaning isn't conveyed by text (e.g., status dots)

---

## Icons

- Style: Line-art SVGs with 1.5–2px stroke width
- Sizing: 12px (inline), 14px (buttons/labels), 16–20px (section headers), 48px (empty states)
- Color: `currentColor` — inherits from parent text color
- Source: Inline SVGs (no icon library dependency)

---

## Do's and Don'ts

### DO

- Use `bg-o-bg` for inset/sub-card areas
- Use opacity modifiers for muted colors (`bg-o-blue/10`)
- Keep card backgrounds flat (`bg-o-surface`)
- Use `font-mono` for all data: IDs, hashes, prices, addresses
- Use `font-display` for all headings and stat values
- Use `uppercase tracking-wider` for section labels
- Test on 320px width (iPhone SE)

### DON'T

- Use `bg-black/30` or `bg-black/40` (use `bg-o-bg` instead)
- Use raw Tailwind colors like `bg-emerald-500/10` (use `bg-o-green/10`)
- Use `text-[10px]` (use `text-xs`)
- Add glow effects, text shadows, or scanline animations
- Use gradient backgrounds on cards
- Use `::before` pseudo-elements for decorative card borders
- Use JetBrains Mono, IBM Plex Sans, Inter, or Roboto (use Geist Sans / Geist Mono)
- Use cyan (`#22d3ee`) anywhere — the accent is blue (`#0052ff` / `#4C8FFF`)
- Add `col-span-full` to components that aren't children of a grid

---

## Syntax Highlighting

Code blocks in docs use **Shiki** (the VS Code TextMate grammar engine) with CSS variable theming. Highlighting runs entirely server-side via React Server Components — zero JS ships to the client. The `CodeBlock` component (`components/docs/CodeBlock.tsx`) is an async server component; only the copy button (`CopyButton.tsx`) is a client component.

### CSS Variable Theme

Defined in `globals.css` under `:root`. All map to existing `o-*` design tokens:

| Variable | Value | Maps To |
|---|---|---|
| `--shiki-foreground` | `#8a919e` | `o-textSecondary` — default code text |
| `--shiki-background` | `transparent` | CodeBlock card handles bg |
| `--shiki-token-keyword` | `#c084fc` | Purple — keywords (`import`, `const`, `def`, etc.) |
| `--shiki-token-constant` | `#eab308` | `o-amber` — constants, booleans, numbers |
| `--shiki-token-string` | `#22c55e` | `o-green` — string literals |
| `--shiki-token-comment` | `#5b616e` | `o-muted` — comments |
| `--shiki-token-function` | `#f5f5f5` | `o-text` — function calls |
| `--shiki-token-parameter` | `#8a919e` | `o-textSecondary` — parameters |
| `--shiki-token-punctuation` | `#5b616e` | `o-muted` — punctuation |
| `--shiki-token-link` | `#4C8FFF` | `o-blueText` — URLs |

To customize highlighting colors, update the CSS variables — no Shiki theme file changes needed.

---

## Code Patterns

### New card component

```tsx
export default function MyComponent() {
  return (
    <div className="card animate-slide-up">
      <div className="stat-label mb-4">Section Title</div>
      {/* content */}
    </div>
  );
}
```

### New stat display

```tsx
<div className="bg-o-bg rounded-lg p-3 border border-o-border">
  <div className="text-xs text-o-textSecondary uppercase tracking-wider">Label</div>
  <div className="font-display text-xl font-semibold text-o-text mt-1">
    {value}
  </div>
</div>
```

### New responsive grid

```tsx
<div className="grid grid-cols-2 md:grid-cols-4 gap-4">
  {items.map(item => (
    <div key={item.id} className="bg-o-bg rounded-lg p-3 border border-o-border">
      {/* ... */}
    </div>
  ))}
</div>
```

### New page

```tsx
export default function NewPage() {
  return (
    <main className="min-h-screen px-4 py-6 md:px-8 lg:px-12 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="font-display text-2xl md:text-3xl font-bold tracking-tight text-o-text">
          Page Title
        </h1>
        <p className="font-body text-sm text-o-textSecondary mt-1">
          Page description
        </p>
      </div>
      {/* content */}
    </main>
  );
}
```
