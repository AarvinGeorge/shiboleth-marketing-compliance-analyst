# 11 — Product roadmap: incremental improvements (2026-07-13)

> Agreed direction from the post-GT-v2 strategy discussion (Aarvin + Cowork
> acting as product strategist / AI engineer / compliance officer). Aarvin's
> standing constraint: MINIMUM VIABLE UPDATES, small increments, each
> independently shippable, nothing rearchitected. Aarvin: "I like all of
> these ideas and we might have to implement it soon."

## The vision (Aarvin, verbatim intent)

Compliance analyst lands on the dashboard → new check → adds a product →
adds its marketing mediums (website, social channels) → sets scope →
system retrieves the N most relevant marketing pages/posts → stores them
appropriately in Postgres → checker applies EVERY scorecard rule to EVERY
retrieved material (multiple rules can flag the same page) → flags →
intelligent clustering → analyst dispositions. Goal: analysts stop reading
large volumes of marketing material manually.

## The increment sequence (locked order, rationale recorded)

| # | Increment | Status | Why this order |
|---|---|---|---|
| 1 | Checker optimization vs GT v2: baseline on train+test, diagnose misses on TRAIN only, fix, re-measure; test split touched exactly twice (baseline + final) | **DONE 2026-07-13**: baseline 71.2% → final 78.8% strict (train 71.5→80.6, held-out TEST 70.4→74.1); all fixes were retrieval plumbing (match-centered windows, keyword tiers, fallback); evidence validity 1.0 throughout; details in code/CLAUDE.md decision log | Trust in flags is the foundation; everything else just displays them |
| 2 | Empty-window fallback (windows find nothing but rule could apply → full-body check instead of silent not_applicable) + trigger-scope fixes from baseline diagnosis (esp. R-03 strict ruling: incidental deposit-product promotion triggers) | next | Small, measurable, closes recall holes the baseline exposes |
| 3 | pgvector migration: semantic retrieval + semantic clustering TOGETHER (one embedding column serves both) | after 2 | Biggest recall win + fixes clustering in one schema change |
| 4 | Sitemap-first discovery ported from gt2 harness into product ingestion | **DONE 2026-07-13** (commit f88a5c4, pulled forward at Aarvin's direction): semantic discovery vs the LIVE DB scorecard, per-medium page cap, optional mediums with auto-skip (barrier/modal removed), async runs, run deletion, "marketing mediums" vocabulary (display layer; schema identifiers kept — expert pushback, Aarvin informed). E2E-verified live: 8,776 sitemap URLs → exactly the rule-relevant pages (incl. the Spanish free-edition page) → 18 flags / 3 clusters / 1 auto-issue in 9.5 min. diversify() postmortem regression-tested. Depth/timeframe knobs removed per Aarvin | Better coverage, fewer knobs |
| 5 | Disposition feedback loop surfaced in UI (FP-rate trend, "your dismissals taught the system", golden set growth; plumbing already exists in eval_items) | after 4 | Free expert ground truth (v3 accumulates itself) + visible self-improvement = retention |
| 6 | Social media ingestion | LAST, deliberately | Meta blocks scrapers; paste-fallback exists; do not spend increments here until the website loop is excellent |

## Clustering v2 design (committed)

Three-level hierarchy, not two modes:

```
Level 1: RULE (scorecard item)      — exists today (check_id grouping)
Level 2: SEMANTIC ISSUE within rule — the new layer (analyst's decision unit)
Level 3: EXACT WORDING within issue — exists today (normalized-identical);
                                      stays deterministic for the audit trail
```

- Embed each flag's evidence quote (pgvector column, shared with retrieval).
- Cosine-similarity grouping WITHIN the same check_id only — NEVER across
  rules (an analyst never wants an FDIC flag merged with an APR flag).
- Exact-match pass stays first so identical-wording clusters remain provable.
- Existing LLM labeler names the semantic groups.
- **Compliance-trust constraint: semantic merges are suggest-and-confirm in
  the UI ("review as group"), never silent.** Wrong merge = trust-killer;
  under-grouping is merely tedious.

## The Customize-scorecard layer — SHIPPED 2026-07-13 (commit d89e298)

Delivered ahead of schedule at Aarvin's direction: /scorecard studio UI
(verbatim rule cards, dropdown severity, editable binary decompositions,
add-rule with live LLM decomposition + auto-derived primary/broad retrieval
keyword chips, 409 audit guards surfaced). Architecture: LIVE runs are
DB-driven (edited/custom rules actually check); CORPUS runs stay on the
frozen seeded benchmark; run rows snapshot the scorecard in force.
Still pending from the original plan: rule CALIBRATION with probe fixtures
(the signature move) and the E2 decomposition-quality harness — both remain
below.

## The Customize-scorecard layer (original plan, 2026-07-13 — for the parts not yet built)

The preloaded 4-rule scorecard is seed data, not the product. The dashboard's
Customize button lets analysts ADD scorecard items; the system auto-decomposes
each into binary trigger/requirement checks. Everything in this roadmap must
stay compatible with user-added rules. Additions agreed for when this layer
is built:

- **Rule calibration on creation (the signature move):** after
  auto-decomposition, the system generates a handful of synthetic probe
  fixtures for the new rule (clear pass, clear violation, non-trigger — the
  gt2 synthetics machinery repurposed), runs its own checker on them, and
  shows the analyst "rule calibrated: 5/5 probes correct ✓" before the rule
  goes live. Turns rule-adding into a visible-trust moment and gives every
  user rule its own mini ground truth. Failed calibration = the decomposition
  gets revised automatically or flagged for wording help.
- **Auto-derived retrieval keywords per user rule:** keyword families are
  hand-coded for the 4 seeded rules today; a new rule needs its trigger
  keywords extracted from its decomposition at creation time, else it gets
  no retrieval. Superseded later by semantic retrieval, needed until then.
- E2 (decomposition-quality eval harness) returns with this layer, per spec.

## Clustering C1 status (2026-07-13, evening): BACKEND SHIPPED

Issue-suggestion layer live (commit eba10ab, pushed): Sentry-pattern
validated against industry (Sentry fingerprint→issue→merge/unmerge;
PerformLine curated-alert workflows). Deterministic wording clusters
unchanged; AI layer = signer (constrained violation-mode signature) +
adjudicator (same-issue verdict with recorded rationale); NOT agentic by
design — two narrow explainable judgments. Never crosses rules; suggestions
require human confirm; rejections remembered, never re-suggested. Additive
migration applied. E6 eval harness + golden set (grows via analyst
dispositions): baseline accuracy 0.83, same-issue recall 1.0, precision
0.78 (over-suggests = safe direction). Live smoke on certified run: 8/9
wording clusters -> one suggested issue with label + rationale.
C2+C3 SHIPPED same day (commit 9c50f75): product payload carries the issue
layer; cluster surface renders suggestion cards (AI badge, always-visible
"Why grouped:" rationale, nested members, accept/keep-separate) and
confirmed grouped cards; verified live in-browser on the certified run,
zero console errors, demo DB left pristine. 152 API tests + web build green.
Clustering increment COMPLETE; pgvector upgrade (roadmap #3) later swaps
the grouping mechanism, UI unchanged.

## Checker-harness improvement queue (2026-07-13, expert review)

Binary trigger/requirement decomposition is CONFIRMED intact and is the
protocol both the checker and the GT v2 judge panel share. Improvements, in
value order:

1. **Position-annotated windows:** stamp windows with paragraph position
   ("¶3 of 42") so placement/attribution rules (R-01 "right underneath") can
   be judged with real layout distance. Cheap; targets R-01's miss class.
2. **Flag-verifier pass:** one cheap second-model check per FLAG only
   ("does this quote support this verdict?"); fail -> needs_review. The
   production-priced version of the GT v2 judge panel; buys precision where
   errors are most expensive.
3. **Multi-finding runner:** finding-per-aspect per (page, rule); v2
   contains pass+flag record pairs so this finally has a metric.
4. (DONE 2026-07-13) Budget-priority windowing, empty-window fallback
   (24k chars), bare "rate(s)" in R-02 keywords, R-03 strict trigger.

## Standing pushbacks (so they don't get relitigated)

1. **Analysts are not crawl engineers.** Smart defaults + honest coverage
   numbers beat depth/page knobs as the primary interface.
2. **Recall is the existential product risk.** A compliance tool that
   silently misses violations manufactures false confidence; one
   regulator-found miss destroys all trust. Semantic retrieval outranks any
   UI increment. (GT v2's stealth synthetics + semantically-discovered
   pages exist to measure exactly this.)
3. **The disposition loop is the most under-leveraged asset.** Every
   confirm/dismiss is a free expert label.
4. **Social last.** Sequence coverage breadth after flag quality.

## Related artifacts

- `ground-truth-v2/` — frozen GT v2 (367 records, train/test split),
  REVIEW.md rulings, eval_v2.py (production-code baseline harness).
- `ground-truth-v2/results/` — e5v2-* experiment results (also in LangSmith,
  product project).
- `09_mvp1_knowledge_base_2026-07-10.md` — the certified MVP1 state this
  roadmap builds on.
