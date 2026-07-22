# Architecture: Components & Design System

## Design Tokens

### Colour System (OKLCH)

The design system uses OKLCH colour values with warm neutral tones. All colours are defined as CSS custom properties in `src/index.css`.

**Light Mode Core:**
```
Background:   oklch(0.98 0.008 85)     — warm off-white
Foreground:   oklch(0.18 0.02 70)      — near-black warm
Card:         oklch(1 0 0)             — pure white
Primary:      oklch(0.25 0.03 65)      — dark warm
Secondary:    oklch(0.945 0.01 85)     — light warm
Muted:        oklch(0.945 0.01 85)     — same as secondary
Destructive:  oklch(0.577 0.245 27.3)  — vivid red
Border:       oklch(0.90 0.012 85)     — subtle warm line
Ring:         oklch(0.68 0.03 75)      — focus ring
```

**Chart Colours:**
```
chart-1: oklch(0.62 0.17 250)   — blue
chart-2: oklch(0.60 0.12 300)   — purple
chart-3: oklch(0.55 0.12 170)   — teal
chart-4: oklch(0.70 0.16 55)    — amber
chart-5: oklch(0.65 0.02 75)    — neutral
```

**Sidebar:**
```
sidebar:         oklch(0.965 0.01 85)   — slightly darker than page bg
sidebar-primary: oklch(0.25 0.03 65)    — matches primary
sidebar-accent:  oklch(0.93 0.012 85)   — hover/active state
```

Dark mode inverts all values while maintaining the warm hue family (70-85 range).

### Typography

- **Body/UI:** Geist Variable (loaded via `@fontsource-variable/geist`)
- **Base size:** 12.5px with `leading-snug tracking-tight`
- **Font smoothing:** Antialiased on both webkit and moz

### Border Radius

Base radius: `0.625rem` with computed scale:
```
sm:  0.375rem (0.6x)
md:  0.5rem   (0.8x)
lg:  0.625rem (1x — base)
xl:  0.875rem (1.4x)
2xl: 1.125rem (1.8x)
3xl: 1.375rem (2.2x)
4xl: 1.625rem (2.6x)
```

## Tailwind CSS v4 Configuration

Tailwind v4 uses the new `@theme inline` directive instead of `tailwind.config.js`. All design tokens are mapped in `src/index.css`:

```css
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";
@import "@fontsource-variable/geist";

@custom-variant dark (&:is(.dark *));

@theme inline {
    --font-sans: 'Geist Variable', sans-serif;
    --color-background: var(--background);
    --color-primary: var(--primary);
    /* ... all token mappings */
}
```

## shadcn/ui Components

Components are installed via the shadcn CLI and live in `src/components/ui/`. They use Base UI (Radix) primitives under the hood.

**Installed components:**
avatar, badge, button, card, collapsible, command, dialog, dropdown-menu, input, input-group, label, popover, scroll-area, select, separator, sheet, sidebar, skeleton, table, tabs, textarea, tooltip

**Configuration** (`components.json`):
- Style: default
- Path alias: `@/components/ui`
- Tailwind CSS v4 mode

**Rules:**
- Never modify shadcn component files directly — restyle via Tailwind classes at the usage site
- Add new components via `npx shadcn@latest add <component>`
- Components use `class-variance-authority` for variant management and `tailwind-merge` for class deduplication

## Shared Components

Located in `src/components/shared/`:

| Component | Purpose |
|-----------|---------|
| `stat-card.tsx` | Reusable metric card with label, value, trend |
| `stepper.tsx` | Multi-step wizard progress indicator |

## Layout Components

Located in `src/components/layout/`:

| Component | Purpose |
|-----------|---------|
| `app-sidebar.tsx` | Main navigation sidebar (collapsible) |
| `top-bar.tsx` | Header with breadcrumbs, search, user menu |
| `theme-toggle.tsx` | Dark/light mode switch |
| `nav-config.ts` | Navigation structure definition |

## Component Conventions

- Components are functional with hooks
- Props use TypeScript interfaces
- Loading states use `<Skeleton />` components, not spinners
- Empty states use dashed-border placeholder divs with descriptive text
- Icons from `lucide-react` only
- `cn()` utility (clsx + tailwind-merge) for conditional classes
