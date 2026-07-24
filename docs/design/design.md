---
name: Adlign
description: Banking-fintech trust aesthetic for a marketing-compliance monitoring product. shadcn/ui default theme as the base; one blue accent; semantic colors only with meaning.
colors:
  primary: "#2563eb"
  on-primary: "#ffffff"
  foreground: "#0a0a0a"
  secondary: "#71717a"
  neutral: "#ffffff"
  surface: "#fafafa"
  border: "#e4e4e7"
  success: "#16a34a"
  success-bg: "#f0fdf4"
  success-text: "#15803d"
  warning: "#d97706"
  warning-bg: "#fffbeb"
  warning-text: "#b45309"
  danger: "#dc2626"
  danger-bg: "#fef2f2"
  danger-text: "#b91c1c"
  accent-bg: "#eff6ff"
  accent-text: "#1d4ed8"
typography:
  h1:
    fontFamily: Inter
    fontSize: 1.25rem
    fontWeight: 500
  h2:
    fontFamily: Inter
    fontSize: 1rem
    fontWeight: 500
  body:
    fontFamily: Inter
    fontSize: 0.875rem
    fontWeight: 400
  body-sm:
    fontFamily: Inter
    fontSize: 0.75rem
    fontWeight: 400
  metric-value:
    fontFamily: Inter
    fontSize: 1.375rem
    fontWeight: 500
  mono-evidence:
    fontFamily: JetBrains Mono
    fontSize: 0.75rem
rounded:
  sm: 6px
  md: 8px
  lg: 12px
  pill: 999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: 8px 14px
  button-outline:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.secondary}"
    rounded: "{rounded.md}"
    padding: 8px 14px
  card:
    backgroundColor: "{colors.neutral}"
    rounded: "{rounded.lg}"
    padding: 16px
  metric-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    padding: 12px 14px
  badge-danger:
    backgroundColor: "{colors.danger-bg}"
    textColor: "{colors.danger-text}"
    rounded: "{rounded.pill}"
    padding: 2px 9px
  badge-warning:
    backgroundColor: "{colors.warning-bg}"
    textColor: "{colors.warning-text}"
    rounded: "{rounded.pill}"
    padding: 2px 9px
  badge-success:
    backgroundColor: "{colors.success-bg}"
    textColor: "{colors.success-text}"
    rounded: "{rounded.pill}"
    padding: 2px 9px
  badge-accent:
    backgroundColor: "{colors.accent-bg}"
    textColor: "{colors.accent-text}"
    rounded: "{rounded.pill}"
    padding: 2px 9px
  hairline:
    backgroundColor: "{colors.border}"
    height: 1px
  status-dot-clear:
    backgroundColor: "{colors.success}"
    size: 8px
    rounded: "{rounded.pill}"
  status-dot-flagged:
    backgroundColor: "{colors.warning}"
    size: 8px
    rounded: "{rounded.pill}"
  evidence-underline:
    backgroundColor: "{colors.danger}"
    height: 2px
---

## Overview

Adlign's UI is minimal, clean banking-fintech trust: white surfaces, hairline borders, generous whitespace, calm and reliable like a well-made financial tool. Built exclusively on shadcn/ui (default theme, Tailwind) with lucide icons; charts exclusively via shadcn/ui Charts (Recharts v3). The single blue accent is reserved for active navigation, primary CTAs, and AI activity. This file is the binding UI contract for the v1 build (Tier 1 + Tier 2 surfaces of `06_prd_adlign_v1` §4).

**Source-of-truth precedence:** 1) this file for anything it states; 2) the prototype `design-files/Adlign-marketing-compliance-checker-v1/` (UX Version 2) for layout, spacing, and visual composition; 3) `03_design_delta_adlign_v2.2_2026-07-09.pdf` for verdict tags, lifecycle chips, and metric card contents (the prototype has NOT absorbed these; the delta PDF wins where they conflict); 4) `03_design_handoff_adlign_v2_2026-07-08.pdf` for anything else.

## Colors

- **Primary (#2563eb):** the sole interaction driver. Active nav item, primary buttons, AI-activity indicators, checking-state progress. Never decorative.
- **Foreground (#0a0a0a) / Secondary (#71717a):** ink for headings and body; slate for supporting text, captions, metadata.
- **Neutral (#ffffff) / Surface (#fafafa):** page and card surfaces; metric cards sit on the soft surface tone.
- **Semantic tints, only with meaning:** green = pass / done / closed; amber = warning / needs-review / drift / fix-pending; red = fail / unapproved / missing. Each pairs its `-bg` tint with its `-text` shade (never black on a tint).
- No gradients, no shadows beyond shadcn defaults, no decoration.

## Typography

Inter everywhere (shadcn default sans). Sentence case in all UI copy. Evidence quotes and rule/check identifiers render in the mono face (`mono-evidence`) so quoted material is visually distinct from UI chrome. Dense app scale: 14px body, 12px supporting, 22px metric values; headings weight 500, never bolder.

## Layout

Desktop 1440 only for v1. App shell: fixed left sidebar (Customize scorecard button, New check primary button, PRODUCTS list with status dots, user chip at bottom; expanded only), main panel renders the active surface. Breadcrumbs for depth: Dashboard › product › flag. Spacing rhythm from the `spacing` scale; cards use `rounded.lg`, controls `rounded.md`, badges and chips `rounded.pill`.

## Components

Reusable primitives, built once and reused everywhere:

- **MetricCard** — muted 12px label + info tooltip (the metric's intent line from `01_spec_v1` §10), `metric-value` number, muted sublabel, optional sparkline slot (shadcn Charts area or line).
- **VerdictTags** — three compact pill badges on one line: axis A `Compliant`/`Non-compliant`, axis B `Matches approval`/`Differs from approval`/`N/A` (gray), and the visually dominant named intersection: `All good`, `Drifted but compliant`, `Approved but non-compliant`, `Unapproved violation`.
- **LifecycleChip** — current state only: Open (danger tint), Confirmed (accent tint), Assigned · team (accent), Fix pending verification (warning, clock icon), Closed (success, check icon), Dismissed (muted, strikethrough row).
- **FlagRow** — property icon, mono snippet + location, VerdictTags, LifecycleChip or Dismiss/Confirm buttons, "Open ›" link. States: untriaged, confirmed+assigned, dismissed, missing-variant (day 2).
- **PropertyLane** — property icon + name, status pill, streamed step list. States: done, checking, needs-input (warning + Paste content / Skip).
- **RuleRow** — chevron, mono rule id, verbatim rule text, SeverityBadge (High/Medium/Low, dropdown-editable), decomposition status, edit + delete icons; expands to binary check cards (accent border + book icon when library-linked).
- **PropertyChip** — platform icon + label + remove X (website, instagram, facebook).

Surface contracts (U1 shell, U2 dashboard, U3 new-check modal, U4 scorecard studio, U5 run view, U6 product detail, U7 flag detail), their exact metric card contents, states, and the report block: as specified in `06_prd_adlign_v1` §4-§5 and the prototype per the precedence order above. Deferred UI (design exists, do not build in v1): Missing-flag row and inventory-diff card, full audit accordion, insights tab, view toggle, screenshot tab, PDF export, sidebar collapse.

## Do's and Don'ts

- Do keep one accent: blue is interaction and AI activity only; a screen with more than one solid-blue element besides the primary CTA is wrong.
- Do use semantic colors only when they carry their meaning; never as decoration.
- Do render every AI output as editable and deletable; the human always has the last word.
- Do stream intermediate steps for anything async; never block the user behind a spinner.
- Do use progressive disclosure: dense bordered rows collapsed by default, expand for detail.
- Do show the draft score only alongside the verified score at product level; never show draft at portfolio level.
- Don't use any chart library other than shadcn/ui Charts (Recharts v3); don't use any icon set other than lucide.
- Don't use em-dashes or exclamation marks in product copy; sentence case, verb-first CTAs.
- Don't invent screens, stages, or features beyond the PRD; anything tempting goes to the day-2 backlog.
- Don't paraphrase the scorecard rule text anywhere it renders; doc 05 §1 is verbatim canonical.

## Demo Dataset

TurboTax Free product; rules R-01..R-04 verbatim (doc 05 §1); library entry D-01 (~37% disclosure, Approved); example flags per the v2.2 delta PDF including one "Approved but non-compliant" case; supporting products QuickBooks Money (clear, 93) and Credit Karma Money (checking) for dashboard states. Real-feeling data, no lorem ipsum.
