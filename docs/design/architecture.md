# Adlign architecture v1 (2026-07-09)

> The HOW document. Scope: the five things no other doc answers: runtime choreography, the pause/resume decision, frontend architecture, concrete scaffolding, and cross-cutting payload contracts. Precedence: `prd.md` defines WHY, `spec.md` defines WHAT, this document defines HOW; where they conflict, the spec wins. See `README.md`.

## 1. System diagram

```
Browser (Next.js, shadcn/ui)
   │  REST (JSON)                        │  SSE (run events)
   ▼                                     ▼
FastAPI (apps/api) ──────────────────────────────────────────────
   │  create run / disposition / edits        │ events table tail
   ▼                                          │
 In-process async task (one per run)          │
   ▼                                          │
 LangGraph StateGraph  ── emits events ───────┘
   N1 extract → N2 ingest → [barrier] → N4 check → N5 reconcile → N6 cluster → N7 score+report
   │ (N3 decompose runs at Customize time, not in the scan graph)
   ▼
 Postgres (SQL + JSONB + pgvector)  ←── cache/dedup, run inventory, events, flags, scores
   ▲
 crawl4ai (Playwright) ── the ONLY component that touches the live internet, inside N2
 LangSmith ← tracing on every LLM call + eval harnesses (offline)
```

## 2. The pause/resume decision (pinned; do not improvise)

**DB-as-checkpoint with a single ingest barrier.** No LangGraph in-memory interrupts across process boundaries.

- N2 ingest processes every property independently. A property ends in one of: `fetched`, `needs_input` (fetch failed inside the time-box), `skipped`.
- After N2, the graph hits the **barrier**: if any property is `needs_input`, the graph run ENDS (persisting all state to Postgres) and the run status becomes `awaiting_input`. SSE emits `needs_input` per property and `run_awaiting_input`.
- `POST /runs/{id}/paste-content` stores pasted text as materials (same content-hash path); `POST /runs/{id}/skip-property` marks skipped. When no property remains `needs_input`, the API **re-invokes the graph from the checks stage**, reconstructing state from the DB (`run_id` is the thread id; the DB is the checkpoint).
- Rationale: deterministic, testable without a live process, survives restarts, and resume-from-DB is one code path shared with re-runs. The cost: website checks wait for the barrier instead of streaming early; accepted for correctness (logged deviation from the earlier run-view mock).

## 3. Runtime sequences (the choreography)

**S1 Start check.** UI modal → `POST /checks` {product, raw_links_text, config} → API calls extract-properties (N1 service function, same one the live chips use) → creates product/properties/run rows (scorecard snapshot + model config frozen onto the run) → spawns async task → task runs graph N2.. → each node emits events (persist to `events`, push to SSE) → run finishes → scores written to `runs.scores` → SSE `run_finished` → UI invalidates product queries.

**S2 Needs-input.** As pinned in §2. UI: lane shows Paste content / Skip; paste dialog posts; on resume SSE emits `run_resumed` and checking proceeds.

**S3 Disposition.** Flag detail → `POST /flags/{id}/disposition` {action, team?, note?} → validates lifecycle transition → updates flag state → appends `eval_items` row (dismissed = FP label) → recomputes verified scores (pure SQL/Python, no LLM) → returns updated flag + scores → UI updates row and metric cards from the response (no SSE needed).

**S4 Cached re-run.** Re-run button → `POST /checks` for the existing product → N2 checks freshness per material (content-hash + TTL 24h): fresh = reuse stored material (emit `material_fetched` with `cache_hit: true`), stale/missing = fetch → new run inventory persisted → diff vs previous inventory computes Missing candidates (model only in v1) → checks run against the store as always.

**S5 Edit rule in Customize.** `PATCH /rules/{id}` → rule text updated (verbatim field) → decomposition job re-runs for THAT rule only → its checks replaced (links re-suggested) → SSE-free: studio polls or refetches on mutation response. Scorecard version bumps; existing runs keep their frozen snapshot.

## 4. Frontend architecture (pinned)

- Next.js App Router, **all data fetching client-side via TanStack Query** against the FastAPI REST API; no server actions, no route handlers doing data work (one data path, lean).
- Routes: `/` dashboard, `/scorecard` customize studio, `/products/[id]` product detail (flags + report block), `/products/[id]/flags/[flagId]` flag detail, `/products/[id]/run` watchable run view. New check is a client-state Dialog, not a route.
- SSE: one `useRunEvents(runId)` hook wrapping EventSource; events append to a per-run Zustand store that the run view and checking-card render from; `run_finished`/`run_awaiting_input` trigger Query invalidations.
- Components: `src/components/primitives/` implements exactly the DESIGN.md primitives (MetricCard, VerdictTags, LifecycleChip, FlagRow, PropertyLane, RuleRow, PropertyChip, SeverityBadge); `src/components/surfaces/` composes them per surface. No primitive logic inside surfaces.
- Types in `src/lib/types.ts` mirror the Pydantic schemas 1:1 (§6); if a field changes, both sides change in the same commit.

## 5. Repo scaffold (P0 creates exactly this)

```
code/
├── CLAUDE.md                  (gitignored; intent, doctrine, phase status, decisions)
├── .env  /  .env.example      (02_handoff §2 key list)
├── docker-compose.yml         (postgres:16 + pgvector)
├── Makefile                   (dev, test, lint, evals)
├── apps/api/                  (Python 3.12, uv)
│   ├── pyproject.toml
│   ├── src/adlign/
│   │   ├── main.py            (FastAPI app + SSE endpoint)
│   │   ├── config.py          (env load + verify, model registry per stage)
│   │   ├── db/                (engine, models.py, alembic migrations)
│   │   ├── domain/schemas.py  (the §6 Pydantic contracts)
│   │   ├── services/
│   │   │   ├── ingestion/     (crawler.py, social.py, cache.py, extract.py)
│   │   │   ├── scorecard/     (parser.py, decompose.py, library.py, linking.py)
│   │   │   ├── scoring/       (formulas.py, metrics.py)
│   │   │   └── reporting/     (report.py)
│   │   ├── pipeline/          (state.py, graph.py, nodes/, events.py)
│   │   ├── evals/             (harnesses/, golden/)
│   │   └── api/routes/        (checks.py, products.py, scorecard.py, flags.py, metrics.py)
│   └── tests/                 (unit/, integration/, e2e/, fixtures/site/)
└── apps/web/                  (Next.js + shadcn/ui)
    └── src/ (app/, components/primitives/, components/surfaces/, lib/)
```

Service functions in `services/` are tool-shaped (Pydantic in/out) per the MCP-ready rule (04 §6g).

## 6. Cross-cutting contracts (frontend and backend implement these identically)

**SSE event envelope:** `{event_id, run_id, ts, type, node, property_id?, flag_id?, payload}`. Types: `run_started`, `node_started`, `material_fetched` (payload: url, cache_hit), `property_status` (fetched|needs_input|skipped), `check_result` (flag summary), `node_finished` (stats), `needs_input`, `run_awaiting_input`, `run_resumed`, `scores_updated`, `run_finished` (status), `error` (message). Events are persisted rows first, SSE second; the audit chain in flag detail renders from the same rows.

**Core Pydantic schemas (full field lists derive from 01_spec §5):** `Property {id, kind, url_or_handle, config}`; `Rule {id, verbatim_text, severity, position}`; `BinaryCheck {id, rule_id, kind: trigger|requirement, text, evidence_criteria, library_entry_id?}`; `Material {id, property_id, ref, kind, content_hash, extracted_text, fetched_at}`; `CheckResult {material_id, check_id, trigger_met, requirement_met?, axis_a, axis_b, intersection_tag, evidence_quote, location, reason, confidence}`; `Flag {id, ..., state, assigned_team?, note?, verdicts: CheckResult}`; `RunScores {draft, verified, per_property: {property_id: score}}`; `Disposition {action: confirm|dismiss, team?, note?}`.

**Graph state (`ScanState`):** `{run_id, product_id, properties[], scorecard_snapshot, materials[], inventory[], check_results[], reconciliation[], clusters[], scores?, report?}` — every node reads/writes only its declared fields.

**Intersection tag derivation (single source, `scoring/formulas.py`):** (A=yes,B=yes)→`all_good`; (A=yes,B=no)→`drifted_but_compliant`; (A=no,B=yes)→`approved_but_non_compliant`; (A=no,B=no)→`unapproved_violation`; B=na → tag derives from A alone (`all_good`/`unapproved_violation` with `approval_na` marker).

## 7. Autonomy dial for Claude Code

Decide freely and log in `code/CLAUDE.md`: anything implementation-level not stated here or in the spec. **Surface to Aarvin before proceeding: any change to the §6 contracts, the §2 pause/resume mechanic, the data model, the scoring formulas, the phase order, or anything in the nine guardrails.** When two reasonable options exist for a contract-level choice, present both with a recommendation instead of picking silently.
