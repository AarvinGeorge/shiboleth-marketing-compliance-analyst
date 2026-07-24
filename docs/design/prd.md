# Adlign PRD v1 (2026-07-09)

> The product requirements document for MVP v1: the full intent and mission. Companion docs in this folder: `spec.md` (technical spec), `architecture.md` (the HOW), `design.md` (UI contract). See `README.md` for how this folder relates to the shipped product.

## 1. Mission and intent

Adlign is a continuous marketing-compliance monitoring product for compliance analysts at fintechs whose bank partners require their marketing to comply with a defined scorecard. It flags violations across large volumes of live marketing material (websites, social), with cited evidence, human disposition, and defensible scoring.

**MVP v1 mission:** prove the entire loop works end to end, correctly, on real data, once, and freeze the proof. Success = ONE scan of Intuit TurboTax Free runs smoothly end to end and yields a correct **base condition**: the frozen run outputs + eval scores that all future changes are measured against. This is a real product, not a demo rig: **nothing is hardcoded to TurboTax**; the product under scan, its properties, the scorecard, and the disclosure library are runtime data flowing through a fixed, opinionated architecture.

**Development doctrine (binding):** intent-driven, spec-driven, test-driven; reusability and appropriate abstraction; graph-orchestrated sub-agents; MCP adopt-or-build; minimum cost (free tiers, cheap models first) with completeness and correctness as the end goal; meta-snippet code hygiene (every code file carries a functionality-describing header kept in sync); data-driven enhancement via three eval harnesses from day one. Full doctrine: 04 §6f.

## 2. Users and validated pain points

Primary user: a single marketing-compliance analyst. Validated pains (sources in 04 §2): (P1) volume and manual overwhelm; (P1) post-publication drift of approved content; (P1) bypass, content shipping without pre-approval; (P1) evidence and audit burden; (P1) bank-partner oversight pressure; (P2) setup fatigue; (P2) slow review loop with marketing; (P2) false positives without triage. V1 visibly addresses all eight.

## 3. Problem statement (from the company, doc 05 §3)

Root cause: in pre-approval the population is given; in monitoring the population is **discovered**, and it changes between runs. Consequences bound into this product: coverage is itself a finding (Missing flags via run-inventory diff); the unit of review inverts (cluster = the issue, bulk disposition with individual exclusions); the verdict splits into two independent axes (compliant × matches-approval, with the named intersection as a first-class tag); the lifecycle is remediation, not adjudication (detect → confirm → assign → fix pending verification → close). The human judgment layer (disposition, FP tracking, audit trail) transfers unchanged.

## 4. Scope

**IA:** Dashboard (home) → Product detail → Flag detail; standing surfaces: Customize scorecard studio (sidebar) and New check modal. The check pipeline runs under the hood, watchable via the run view.

**Tier 1 (build first; runs and verifies the base condition):** Customize studio (seed + review decomposition, the first correctness gate); New check modal (product + links, live extracted chips); watchable run view with paste-content fallback; product detail flags list with per-flag disposition (second correctness gate); flag detail (highlighted evidence + compact why-flagged chain + Disposition with assign); report block (executive summary + per-property results inside product detail).

**Tier 2 (after Tier 1 runs):** dashboard hero metrics + product cards with sparklines; shell polish, empty states.

**Out of v1 (data modeled day 1, UI/feature day 2+):** PDF export, screenshots + positioned pins, insights tab, view toggle, full audit accordion, Missing-flag UI, audit-the-library, daily cron, auto-verify closure, Adlign MCP server, sidebar collapse. Email is completely out of scope (Aarvin, 2026-07-09).

## 5. Functional requirements

- **F1 Scorecard studio:** upload .xlsx; rules preserved VERBATIM (doc 05 §1 is canonical, never paraphrased); LLM decomposition into binary trigger + requirement checks with evidence criteria; severity from Excel column, LLM-suggested fallback, always editable; edit/delete on every rule and check; editing a rule re-decomposes only that rule; library entries (approved wording, status, provenance) with LLM auto-linking to checks, editable; async, observable synthesis; one global scorecard used by all products.
- **F2 New check:** create-or-pick product; freeform links box with live AI extraction into typed, removable chips (website / instagram / facebook); crawl depth (2), page cap (20), post timeframe (Feb 1 to Mar 31 default for the demo product); the global scorecard applies automatically.
- **F3 Ingestion:** batch crawl (domain link discovery, BFS depth/cap) + social fetch inside a hard time-box; **cache/dedup**: content-hash + timestamp per material, freshness policy (per-property TTL, default 24h), fetch only missing/stale; run inventory persisted per crawl; paste-content fallback as a first-class run state; analysis never touches the live web.
- **F4 Check pipeline:** LangGraph StateGraph, nodes per 01_spec §4 (extract, ingest, decompose-load, check, reconcile, cluster, score+report); per-material × per-rule binary checks; untriggered = N/A, never pass; evidence quote must substring-match stored material or the flag becomes needs-review; per-stage model selection via config.
- **F5 Verdict model:** every material carries axis A (compliant y/n), axis B (matches approval y/n/na), and the named intersection tag (All good / Drifted but compliant / Approved but non-compliant / Unapproved violation); three tags rendered wherever flags appear.
- **F6 Disposition and lifecycle:** per-flag Dismiss (note optional) or Confirm → Assign to team with traveling note; lifecycle open → confirmed → assigned → fix pending verification → closed (+ terminal dismissed); v1 transitions manual, auto-verify day 2; every disposition writes a labeled row feeding the eval golden set; verified score recomputes arithmetically on each disposition.
- **F7 Scoring and metrics:** severity-weighted formulas per 01_spec §5; draft vs verified; five hero metrics and product-level mirrors exactly per 01_spec §10 (each metric bound to its intent); scores-per-run persisted as the trend series.
- **F8 Report:** executive summary (one LLM call), per-property results, confirmed findings with notes; rendered as a block in product detail.
- **F9 Observability:** every pipeline step emits a persisted event (audit chain + SSE + LangSmith); LangSmith tracing on from the first commit.

## 6. Non-functional requirements

Correctness end to end above all; a scan of 20 pages + fetched/pasted social completes in under ~10 minutes on free-tier rate limits; total v1 cost $0 (free tiers; paid models one config away); all secrets in `code/.env` per best practices (see 02 handoff §env); single reviewer, no auth in v1; desktop 1440 only.

## 7. Data, API, evals, tests

Data model: 01_spec §5. API contract: 01_spec §6. Eval plan (three harnesses: retrieval, decomposition, checker; golden sets Aarvin-approved; base-condition freeze as LangSmith experiment `base-condition-v1`): 01_spec §7. Test plan (TDD anchors): 01_spec §8.

## 8. Acceptance criteria (the base condition checklist)

1. Scorecard uploaded; 4 rules verbatim; decomposition reviewed and approved in the studio.
2. New check on TurboTax Free properties completes end to end; Meta fetch failure degrades to paste fallback without breaking the run.
3. Every flag carries three tags, valid evidence (substring-verified), location, and reason.
4. Disposition works: dismiss with note, confirm with team assignment; verified score visibly recomputes.
5. Report block renders: executive summary + per-property results.
6. All pipeline events persisted; run fully traced in LangSmith.
7. Three eval harnesses run; scores recorded; `base-condition-v1` frozen.
8. Zero TurboTax-specific logic in code (verified by grep and by QA review).
9. Every code file carries a current meta-snippet header; all tests green.

## 9. References

Context: `CLAUDE.md` → `04_trial_context...md` (§6b metrics, §6d roles, §6e verdict/lifecycle, §6f intent, §6g stack) → `05_shibboleth_problem_context...md` (VERBATIM scorecard). Technical: `01_spec_v1_2026-07-09.md`. UI: `DESIGN.md`, prototype `design-files/Adlign-marketing-compliance-checker-v1/` (UX Version 2), `03_design_handoff_adlign_v2_2026-07-08.pdf`, `03_design_delta_adlign_v2.2_2026-07-09.pdf`. Build: `02_handoff_to_claude_code_v1_2026-07-09.md`.
