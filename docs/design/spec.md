# Adlign technical spec v1 (2026-07-09)

> The v1 specification: architecture, node contracts, data model, scoring, evals, tests, metrics. The scorecard text is used verbatim. Doctrine: intent-driven, spec-driven, test-driven, reusable, lean, minimum cost, correctness end to end. Companion: `prd.md` (WHY), `architecture.md` (HOW), `design.md` (UI). See `README.md`.

## 1. Intent and definition of done

Build Adlign, a marketing-compliance monitoring system with a fixed, opinionated architecture, user flow, and UI, that is **product-agnostic and scorecard-agnostic**: the product under scan, its properties, the scorecard, and the library are runtime data, never code. V1 is done when ONE scan of Intuit TurboTax runs end to end, correctly:

- Input: product "TurboTax Free" with properties `https://turbotax.intuit.com/` (domain link discovery, depth 2, cap 20 pages), `instagram.com/turbotax`, `facebook.com/turbotax` (posts Feb 1 to Mar 31), the verbatim 4-rule scorecard (doc 05 §1), library entry D-01.
- Output: the report (per-property analysis + executive summary), two-axis three-tag verdicts per material, draft and verified scores, the five hero metrics, flags with evidence and disposition.
- That run's results freeze as the **base condition**: the regression baseline in LangSmith for all future changes.
- Nothing hardcoded to TurboTax: swapping in another product and scorecard is a data change, not a code change. Social fetch failures degrade to the paste-content fallback without breaking the run.

## 2. Essential UI (v1 surfaces, from design-files/ prototype)

Seven surfaces, four reusable primitives. Desktop 1440 only. shadcn/ui components only.

| # | Surface | Essential contents | Key states |
|---|---|---|---|
| U1 | App shell | Sidebar: Customize scorecard, New check (accent), product list w/ status dots, user chip | expanded only (collapse deferred) |
| U2 | Dashboard | 5 hero metric cards; product cards | card: flagged / clear / checking(progress + View steps) / empty |
| U3 | New check modal | product create-or-pick; freeform links textarea + live extracted chips; crawl depth / page cap / timeframe selects | empty, chips-populated, submitting |
| U4 | Customize studio | scorecard .xlsx upload; rule rows (severity select, edit, delete); expandable binary checks (trigger+requirement); library entries; Add entry/companion | synthesizing (streamed), ready |
| U5 | Watchable run view | per-property lanes streaming steps; progress counter; check-stage model select | running, needs-input (paste dialog / skip), done |
| U6 | Product detail | product metric row (4 cards); flags list grouped by cluster; per-flag disposition buttons; lifecycle chips | untriaged, confirmed+assigned, dismissed(strikethrough+note) |
| U7 | Flag detail | breadcrumb; extracted text with inline highlight; compact why-flagged chain (5 steps, one expandable); Disposition panel (Dismiss / Confirm → Assign team + note); flag facts | open, confirmed, assigned, dismissed |

Reusable primitives (build once): `MetricCard`, `FlagRow` (with lifecycle chip + disposition actions), `PropertyLane`, `RuleRow` (with checks expansion). Also shared: `PropertyChip`, `SeverityBadge`, `VerdictTags` (3 tags).

Deferred (data modeled, no UI): PDF export, screenshot tab, insights tab, view toggle, full audit accordion (v1 shows the compact chain), Missing-flag badge, audit-the-library, sidebar collapse.

## 3. System architecture

Next.js (UI) → FastAPI (REST + SSE) → LangGraph pipeline → Postgres. LangSmith wired via env vars from the first commit.

**Services (backend packages, each MCP-ready: tool-shaped functions with Pydantic I/O):**
- `ingestion`: crawl4ai crawl (BFS depth 2 cap 20, domain-scoped) + social fetch attempt (hard time-box 10 min total, then needs-input) + paste-content intake. Extracts LLM-ready markdown. **Cache/dedup: content-hash + timestamp per material; freshness policy (TTL per property, default 24h); fetch only missing/stale.** Writes run inventory.
- `scorecard`: .xlsx parse (openpyxl), decomposition via LLM, library synthesis, auto-linking. Verbatim rule text preserved alongside decomposition.
- `pipeline`: the LangGraph StateGraph (§4).
- `scoring`: pure-Python severity-weighted scoring + metrics SQL aggregates. No LLM.
- `api`: FastAPI routes + SSE event stream; one in-process async task per run.

**Run flow:** POST /checks → create run → async task executes graph → nodes emit events (persisted to `events`, streamed via SSE, traced in LangSmith) → run completes → metrics refresh.

## 4. Agent architecture (LangGraph StateGraph)

Typed state `ScanState` (Pydantic): product, properties, scorecard snapshot, inventory, materials, check results, clusters, reconciliation results, scores, report. Nodes are deterministic in flow; intelligence lives inside nodes via `create_agent`/structured-output calls (reference-repo patterns: Pydantic `response_format`, `Command`-style state updates, thread-per-run checkpointing with InMemorySaver).

| Node | Type | Contract (in → out) |
|---|---|---|
| N1 extract_properties | LLM (cheap) | freeform text → typed properties[] (also used live by U3 chips via its service function) |
| N2 ingest | code | properties + freshness policy → materials[] + run_inventory (cache-aware) |
| N3 decompose | LLM sub-agent | rule text (verbatim) → binary checks[] {id, rule_id, kind: trigger|requirement, text, evidence_criteria, severity, library_link?} (runs at Customize time; pipeline loads the frozen snapshot) |
| N4 check | LLM sub-agent (per material × rule) | material + rule's checks + linked library entries → {trigger_met, requirement_met?, axisA compliant y/n, axisB matches_approval y/n/na, intersection_tag, evidence_quote, location, reason, confidence} — untriggered = N/A, never pass |
| N5 reconcile | code + LLM assist | published text vs library entries (fuzzy match) → drift/unapproved contributions to axisB |
| N6 cluster | code (embeddings, pgvector) + LLM labeler | flags[] → clusters[] {label, member flag ids} |
| N7 score_and_report | code + one LLM call | results → scores (draft), metrics, executive summary |

Evidence validity is checked programmatically after N4: `evidence_quote` must be a substring of the stored material, else the flag is marked needs-review.

**Model policy:** per-stage `init_chat_model` strings from config; defaults Gemini 2.5 Flash (N1, N4, N7) and Groq Llama 3.3 (N3, N6 labeling); every call tagged run_id + node + model + prompt_version in LangSmith.

## 5. Data model (Postgres; JSONB for unstructured; pgvector for embeddings)

- `products` (id, name, status)
- `properties` (id, product_id, kind[website|instagram|facebook], url/handle, config JSONB)
- `scorecards` (id, name, version) / `rules` (id, scorecard_id, verbatim_text, severity, position) / `checks` (id, rule_id, kind, text, evidence_criteria, library_entry_id?)
- `library_entries` (id, kind[disclosure|claim], title, approved_text, status, provenance JSONB)
- `runs` (id, product_id, scorecard_snapshot JSONB, model_config JSONB, status, started/finished, scores JSONB {draft, verified, per_property}) — scores-per-run is the time series behind card sparklines and the 7-day trend
- `run_inventory` (run_id, url/post_ref, content_hash, first_seen_run_id) — feeds Missing diffs (model only in v1)
- `materials` (id, property_id, url/ref, kind, content_hash UNIQUE, extracted_text, raw JSONB, fetched_at, embedding vector)
- `flags` (id, run_id, material_id?, check_id, axis_a, axis_b, intersection_tag, evidence_quote, location, reason, confidence, cluster_id?, state[open|confirmed|assigned|fix_pending_verification|closed|dismissed], assigned_team?, note?, dispositioned_at)
- `clusters` (id, run_id, label, kind)
- `events` (id, run_id, flag_id?, node, payload JSONB, ts) — the audit chain and SSE source
- `eval_items` (id, harness[retrieval|decomposition|checker], input JSONB, expected JSONB, source[seed|disposition])

Scoring: property score = 100 × weighted(pass) / weighted(pass+fail), severity weights High 3 / Medium 2 / Low 1, N/A and needs-review excluded from the denominator, needs-review counted separately. Draft = all AI flags; verified = after dispositions. Product score = weighted mean over properties by material count.

## 6. API contract (FastAPI)

- `POST /products`, `GET /products`, `GET /products/{id}` (detail incl. metrics)
- `POST /scorecard/upload`, `GET/PATCH/DELETE /rules/{id}`, `/checks/{id}`, `/library/{id}` (edits re-decompose only the edited rule)
- `POST /checks` {product_id | new product, raw_links_text, config} → run_id
- `GET /runs/{id}/events` (SSE: node_started, material_fetched, check_result, needs_input, node_finished, run_finished)
- `POST /runs/{id}/paste-content` {property_id, text} (fallback intake)
- `GET /runs/{id}/report`, `GET /metrics` (hero strip)
- `POST /flags/{id}/disposition` {action: confirm|dismiss, team?, note?} → recomputed verified score
- `GET /extract-properties` {text} (live chips for U3)

## 7. Eval plan (LangSmith, from first commit)

- Tracing: `LANGSMITH_TRACING=true`, project `adlign-v1`.
- **E1 retrieval quality:** deterministic: pages fetched vs cap, inventory completeness vs a hand-listed expected set for turbotax.intuit.com (~10 known URLs), extraction non-empty rate; judged: extraction fidelity on 5 sampled pages (LLM-as-judge, stronger model).
- **E2 decomposition quality:** golden set = the 4 verbatim rules with hand-approved reference decompositions (Aarvin approves before freeze). Metrics: coverage (every rule → ≥1 trigger + ≥1 requirement check), atomicity, faithfulness (no invented requirements). LLM-as-judge with rubric.
- **E3 checker quality:** golden set = ~25 labeled (material, check, expected verdict) triples drafted from real crawled TurboTax content + synthetic positives (since live true positives may not exist), Aarvin approves. Metrics: verdict accuracy per class (fail-recall weighted highest), evidence validity (programmatic substring check), reason quality (judge).
- Dispositions append to `eval_items` (dismissed = FP labels).
- **Base condition:** when the TurboTax scan first completes correctly, its run outputs + all three eval scores freeze as LangSmith experiment `base-condition-v1`. Every later change reruns E1-E3 against it.

## 8. Test plan (TDD anchors, written before code)

- **Unit:** scorecard xlsx parse → 4 rules verbatim; severity fallback; content-hash dedup (same page twice → one material); freshness policy (fresh skip, stale refetch); scoring math incl. N/A exclusion and verified recompute on dismissal; evidence substring validator; lifecycle transitions (invalid transitions rejected); intersection tag derivation from axis pair.
- **Integration:** ingest against a fixture site (local static HTML, depth/cap respected); decompose with recorded LLM cassettes (deterministic CI); check node on fixture material with known violation → correct flag shape; SSE event order; paste-content fallback path; disposition endpoint → score change.
- **E2E (the base-condition test):** seeded scorecard + fixture TurboTax-like site → full scan → report exists, ≥1 flag with valid evidence, metrics populated, all events persisted. Then the real TurboTax run, manually verified, becomes the base condition.
- Every code file: metadata snippet header (purpose, contract, updated-with-code rule). CI: pytest + a minimal frontend build check.

## 9. Build order (v1 day)

1. Repo scaffold (`code/`: `apps/web` Next.js + shadcn, `apps/api` FastAPI, docker-compose Postgres+pgvector), env wiring incl. LangSmith, meta-snippet convention, CI.
2. Data model + migrations + scoring unit tests (pure logic first).
3. Scorecard service: upload → parse → decompose → U4 studio (seed the verbatim scorecard + D-01).
4. Ingestion service with cache/dedup + fixture-site integration tests.
5. Pipeline graph N1-N7 + SSE + U5 run view.
6. Flags + disposition + U6/U7 + verified scoring.
7. Dashboard U2 + metrics + U3 modal.
8. E1-E3 harnesses + golden set seeding.
9. The real TurboTax run → fix → freeze base condition.

Day 2 (from the locked backlog): screenshots + pins, clustering polish, Missing UI, audit accordion, insights, daily cron, auto-verify lifecycle, Adlign MCP server, library audit, PDF export.

## 10. Dashboard metrics: definitions and intent (finalized 2026-07-09, research-backed)

Charting: **shadcn/ui Charts (Recharts v3)** only; sparklines via the stats-card pattern. No other chart library.

**Hero strip (portfolio, U2).** Each metric = the analyst question it answers → the decision it drives:
1. **Verified portfolio score + 7-day trend** (area sparkline; severity-weighted mean over products) = "are we getting safer or riskier?" → where the week goes; the bank-partner number. Draft never shown at portfolio level; verified only.
2. **Open violations by severity + aging** (count; high count; oldest open in days) = "what's exposed and how long has it festered?" → today's escalations.
3. **Awaiting triage + median time to disposition** = "is the queue under control?" → staffing and scorecard-noise tuning.
4. **Coverage** (% of tracked assets checked ≤24h; total assets discovered) = "can I attest to what's live?" → expand scope; the exam-readiness answer; coverage-is-a-finding (doc 05).
5. **Caught this week: unapproved + drift** = "is anything shipping around the process?" → which team gets the process conversation.

**Product detail metric row (U6):** verified score (with draft + n-of-m dispositioned), open violations + aging, awaiting triage + median, coverage + asset count (pasted content flagged). **Product card (U2):** verified score, score-per-run sparkline (runs.scores), open-flag count, AI summary note; the card answers "has anything changed since I last looked?"

**Insights tab (day 2, data captured from day 1):** remediation cycle time per team (sum(close−open)/closed), repeat violations by rule, false-positive rate per rule (dismissals/total; feeds evals), violations by rule and by channel, audit readiness (% findings with disposition + note + evidence).

Evidence base: PerformLine (compliance scoring, partner risk-ranking), Alessa (alert volume + mean time to disposition), AuditBoard (aging, repeat findings), Sprinto (coverage %), MetricStream (remediation cycle formula, board scorecards), Pagefreezer (unapproved/drift detection), doc 05 (coverage as finding). Full links in 04 §6b and the chat log of 2026-07-09.

## 11. Risks

- Meta properties resist crawling → paste fallback is a first-class path (U5); time-box enforced in code.
- Live TurboTax may contain no true positive → E3 synthetic positives + fixture E2E keep the demo evidentiary; report renders clean-pass states gracefully.
- Free-tier rate limits (Gemini 1.5k req/day) → cache/dedup + per-run check count (~20 pages × 4 rules) stays well inside; Groq as pressure valve.
- Scope creep → anything not in §2/§9 goes to the day-2 backlog, no exceptions.
