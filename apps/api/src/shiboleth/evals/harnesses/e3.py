"""
meta:
  purpose: E3 checker harness — THE acceptance instrument (08 §3.1). Runs the
           corpus-mode checker (production windowing + footer inheritance +
           N4/N5) over 54 snapshots + 17 synthetics and scores against the
           FROZEN ground truth. Every invocation is a named LangSmith run;
           results also land in evals/results/<name>.json.
  contract: python -m shiboleth.evals.harnesses.e3 --name e3-iter-1
            [--subset P05,P18,S01] [--no-cache]. Scoring: strict set =
            analyst + footer_inherited records with GT verdict pass|flag|
            not_applicable (GT needs_review excluded per ground-truth README;
            system needs_review vs GT pass/flag counts half). Synthetics
            scored separately (must be 100%). Evidence validity programmatic.
            Ambiguity recognition reported per class, never in accuracy.
            Threshold claims ONLY from full runs (no --subset).
  deps: production code (windows, check, seed data); LLM cache at
        evals/.cache/e3_cache.json (gitignored) keyed sha256(model+prompt) —
        subset iteration re-calls only changed prompts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path

from shiboleth.config import REPO_ROOT, load_settings
from shiboleth.db.seed import CHECKS
from shiboleth.db.seed_rules import D01_APPROVED_TEXT, RULES
from shiboleth.pipeline.nodes.check import CheckerVerdict, run_check
from shiboleth.services.ingestion.corpus import load_corpus
from shiboleth.services.ingestion.windows import (
    detect_shared_block,
    extract_windows,
    library_anchor_keywords,
    page_has_shared_block,
    strip_shared,
)

GROUND_TRUTH_DIR = REPO_ROOT.parent / "ground-truth"
CACHE_PATH = Path(__file__).resolve().parents[2] / "evals" / ".cache" / "e3_cache.json"
RESULTS_DIR = Path(__file__).resolve().parents[2] / "evals" / "results"

RULE_IDS = ["R-01", "R-02", "R-03", "R-04"]


def rule_bundle(rule_id: str):
    row = next(r for r in RULES if r[0] == rule_id)
    rule = {"id": row[0], "verbatim_text": row[1], "severity": row[2]}
    checks = [c for c in CHECKS if c["rule_id"] == rule_id]
    library = (
        {"id": "D-01", "approved_text": D01_APPROVED_TEXT}
        if any(c["library_entry_id"] == "D-01" for c in checks)
        else None
    )
    return rule, checks, library


class PacedCachedInvoke:
    """Wraps the production checker model with: JSON response cache (keyed by
    model+prompt), ~10k tokens/min pacing under Groq's measured 12k TPM, and
    429 retry with backoff. Cache hits cost nothing (subset iteration)."""

    # tokens-per-minute budget by provider (measured: Groq 12k TPM + hidden
    # 100k TPD; Anthropic 10M input TPM — effectively unpaced)
    TPM_BUDGETS = {"groq": 8_000, "anthropic": 1_000_000, "google_genai": 8_000}

    def __init__(self, model_string: str, use_cache: bool = True):
        self.model_string = model_string
        self.tpm_budget = self.TPM_BUDGETS.get(model_string.split(":")[0], 8_000)
        self.use_cache = use_cache
        self.cache: dict[str, dict] = {}
        if use_cache and CACHE_PATH.exists():
            self.cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        self._live = None
        self._window_start = time.monotonic()
        self._window_tokens = 0
        self.calls_live = 0
        self.calls_cached = 0

    def _key(self, prompt: str) -> str:
        return hashlib.sha256(f"{self.model_string}\n{prompt}".encode()).hexdigest()

    def _pace(self, est_tokens: int) -> None:
        elapsed = time.monotonic() - self._window_start
        if elapsed > 60:
            self._window_start, self._window_tokens = time.monotonic(), 0
        elif self._window_tokens + est_tokens > self.tpm_budget:
            time.sleep(60 - elapsed)
            self._window_start, self._window_tokens = time.monotonic(), 0
        self._window_tokens += est_tokens

    def __call__(self, prompt: str) -> CheckerVerdict:
        key = self._key(prompt)
        if self.use_cache and key in self.cache:
            self.calls_cached += 1
            return CheckerVerdict.model_validate(self.cache[key])
        if self._live is None:
            from shiboleth.pipeline.nodes.check import production_invoke

            self._live = production_invoke(self.model_string)
        # conservative estimate: markdown tokenizes ~3 chars/token, plus
        # schema + completion overhead (iter-1 postmortem: len//4 + 600
        # undercounted -> TPM overspend -> 429 streak outlasted 6 retries)
        self._pace(len(prompt) // 3 + 1200)
        delay = 20.0
        for attempt in range(10):
            try:
                verdict = self._live(prompt)
                break
            except Exception as exc:
                if "429" in str(exc) or "rate" in str(exc).lower():
                    # NEVER retry silently (TPD postmortem: silent retry
                    # ladders are indistinguishable from hangs)
                    print(f"[e3] 429 on attempt {attempt + 1}: "
                          f"{str(exc)[:160]} — sleeping {delay:.0f}s", flush=True)
                    time.sleep(delay)
                    delay = min(delay * 1.5, 90)
                    self._window_start = time.monotonic()
                    self._window_tokens = self.tpm_budget
                    continue
                raise
        else:
            raise RuntimeError("rate-limit retries exhausted")
        self.calls_live += 1
        print(f"[e3] live call #{self.calls_live} done (cache={len(self.cache)})",
              flush=True)
        self.cache[key] = verdict.model_dump()
        if self.use_cache:
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            CACHE_PATH.write_text(json.dumps(self.cache), encoding="utf-8")
        return verdict


def corpus_outcomes(invoke, subset: set[str] | None = None):
    """Run the production corpus-mode checker. Returns
    {(page_id, rule_id, scope): CheckOutcome} with scope in {page, footer}."""
    snapshots = load_corpus(GROUND_TRUTH_DIR / "snapshots")
    synthetics = load_corpus(GROUND_TRUTH_DIR / "snapshots-synthetic")

    bodies = [d.body for d in snapshots]
    shared = detect_shared_block(bodies, min_pages=20)
    shared_text = "\n\n".join(shared)
    outcomes: dict[tuple[str, str, str], object] = {}

    # 1. footer: judged ONCE per rule, inherited to carrying pages.
    # Library anchors + a larger cap: the boilerplate block is judged once,
    # so spending 12k chars on it is cheap and prevents the GT-F03 failure
    # (drifted disclosure truncated out of the windows).
    footer_verdicts = {}
    for rule_id in RULE_IDS:
        rule, checks, library = rule_bundle(rule_id)
        anchors = library_anchor_keywords(library["approved_text"]) if library else None
        windows = extract_windows(
            shared_text, rule_id, max_total_chars=12_000, extra_keywords=anchors
        )
        if not windows:
            continue
        footer_verdicts[rule_id] = run_check(
            "\n\n".join(windows), rule, checks, library, invoke
        )
    for doc in snapshots:
        if subset and doc.page_id not in subset:
            continue
        if page_has_shared_block(doc.body, shared):
            for rule_id, outcome in footer_verdicts.items():
                outcomes[(doc.page_id, rule_id, "footer")] = outcome

    # 2. page bodies (footer stripped), windowed per rule
    for doc in snapshots:
        if subset and doc.page_id not in subset:
            continue
        body = strip_shared(doc.body, shared)
        for rule_id in RULE_IDS:
            rule, checks, library = rule_bundle(rule_id)
            anchors = library_anchor_keywords(library["approved_text"]) if library else None
            windows = extract_windows(body, rule_id, extra_keywords=anchors)
            if not windows:
                outcomes[(doc.page_id, rule_id, "page")] = None  # no signal -> N/A
                continue
            outcomes[(doc.page_id, rule_id, "page")] = run_check(
                "\n\n".join(windows), rule, checks, library, invoke
            )

    # 3. synthetics: standalone materials, same production path
    for doc in synthetics:
        if subset and doc.page_id not in subset:
            continue
        # each synthetic targets one rule, encoded in its filename: Sxx_r-0N_*
        rule_id = "R-0" + doc.source.split("_r-0")[1][0]
        rule, checks, library = rule_bundle(rule_id)
        windows = extract_windows(doc.body, rule_id) or [doc.body]
        outcomes[(doc.page_id, rule_id, "synthetic")] = run_check(
            "\n\n".join(windows), rule, checks, library, invoke
        )
    return outcomes


def system_verdict(outcome) -> str:
    return "not_applicable" if outcome is None else outcome.verdict_status


def _evidence_overlap(quote_a: str, quote_b: str) -> bool:
    """Token-overlap heuristic: do two evidence quotes point at the same text?"""
    tokens_a = {t.lower().strip(".,;:()") for t in quote_a.split() if len(t) > 3}
    tokens_b = {t.lower().strip(".,;:()") for t in quote_b.split() if len(t) > 3}
    if not tokens_a or not tokens_b:
        return False
    return len(tokens_a & tokens_b) / min(len(tokens_a), len(tokens_b)) > 0.4


def score(outcomes, subset: set[str] | None = None, footer_text: str = "") -> dict:
    gt = json.loads((GROUND_TRUTH_DIR / "ground_truth.json").read_text(encoding="utf-8"))
    records = gt["records"]
    strict_hits, strict_total = 0.0, 0
    per_class: dict[str, list[float]] = defaultdict(list)
    per_rule: dict[str, list[float]] = defaultdict(list)
    synth_hits, synth_total = 0, 0
    flags_seen, evidence_ok = 0, 0
    ambiguity: dict[str, list[bool]] = defaultdict(list)
    misses: list[dict] = []

    for rec in records:
        page, rule_id, source = rec["page_id"], rec["rule_id"], rec["judgment_source"]
        if subset and page not in subset:
            continue
        if page == "_footer":
            # canonical footer judgments: compare via any carrying page
            candidates = [v for (p, r, s), v in outcomes.items() if r == rule_id and s == "footer"]
            outcome = candidates[0] if candidates else None
            got = system_verdict(outcome)
        elif source == "footer_inherited":
            outcome = outcomes.get((page, rule_id, "footer"))
            got = system_verdict(outcome)
        elif source == "synthetic_author":
            outcome = outcomes.get((page, rule_id, "synthetic"))
            got = system_verdict(outcome)
        else:  # analyst page records + screened_policy
            outcome = outcomes.get((page, rule_id, "page"))
            got = system_verdict(outcome)
            # Ruling B (Aarvin 2026-07-10): a page record whose GT evidence
            # actually lives in the shared footer TEXT is matched against the
            # footer verdict — the judgment exists, bookkept on footer scope.
            # (Compare against the footer text, not the footer verdict's own
            # chosen quote: two different footer passages both live there.)
            if got == "not_applicable" and rec.get("evidence_quote") and footer_text:
                footer_outcome = outcomes.get((page, rule_id, "footer"))
                if footer_outcome is not None and _evidence_overlap(
                    rec["evidence_quote"], footer_text
                ):
                    outcome = footer_outcome
                    got = system_verdict(footer_outcome)

        expected = rec["verdict_status"]

        # multi-record (page,rule) pairs (e.g. P18 R-03: CKM flag + Credit
        # Builder pass): a system flag is judged against the record whose
        # evidence it actually targets. If the system flagged and this GT
        # record is a pass whose evidence does NOT overlap the system's
        # evidence, the pass record is not contradicted -> score by the
        # sibling flag record instead of double-charging one outcome.
        if (
            source == "analyst"
            and expected == "pass"
            and outcome is not None
            and getattr(outcome, "verdict_status", None) == "flag"
        ):
            siblings = [
                r for r in records
                if r["page_id"] == page and r["rule_id"] == rule_id
                and r["id"] != rec["id"] and r["verdict_status"] == "flag"
            ]
            if siblings and not _evidence_overlap(
                outcome.evidence_quote, rec.get("evidence_quote", "")
            ):
                got = "pass"  # the flag targeted the sibling, not this aspect

        if source == "synthetic_author":
            synth_total += 1
            synth_hits += got == expected
            if got != expected:
                misses.append({"id": rec["id"], "expected": expected, "got": got})
        elif source == "screened_policy":
            if expected == "needs_review":
                ambiguity["screened_policy"].append(got in ("needs_review", "flag"))
            continue
        elif expected == "needs_review":
            ambiguity[source].append(got in ("needs_review", "flag"))
            continue
        else:
            credit = 1.0 if got == expected else (0.5 if got == "needs_review" else 0.0)
            strict_hits += credit
            strict_total += 1
            per_class[source].append(credit)
            per_rule[rule_id].append(credit)
            if credit < 1.0:
                misses.append({"id": rec["id"], "expected": expected, "got": got,
                               "credit": credit})

        if outcome is not None and system_verdict(outcome) == "flag":
            flags_seen += 1
            evidence_ok += outcome.evidence_valid

    return {
        "strict_accuracy": round(strict_hits / strict_total, 4) if strict_total else None,
        "strict_n": strict_total,
        "per_class": {k: round(sum(v) / len(v), 4) for k, v in per_class.items()},
        "per_rule": {k: round(sum(v) / len(v), 4) for k, v in sorted(per_rule.items())},
        "synthetics": f"{synth_hits}/{synth_total}",
        "synthetics_pct": round(synth_hits / synth_total, 4) if synth_total else None,
        "evidence_validity": round(evidence_ok / flags_seen, 4) if flags_seen else 1.0,
        "flags_emitted": flags_seen,
        "ambiguity_recognition": {
            k: f"{sum(v)}/{len(v)} ({sum(v)/len(v):.0%})" for k, v in ambiguity.items()
        },
        "misses": misses,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--subset", default=None, help="comma-separated page ids")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()
    subset = set(args.subset.split(",")) if args.subset else None

    settings = load_settings()
    from shiboleth.main import propagate_env

    propagate_env(settings)
    invoke = PacedCachedInvoke(settings.model_for("check"), use_cache=not args.no_cache)

    from langsmith import trace

    started = time.monotonic()
    with trace(name=args.name, project_name=settings.langsmith_project,
               inputs={"subset": args.subset or "FULL",
                       "model": settings.model_for("check")}) as run:
        outcomes = corpus_outcomes(invoke, subset)
        snapshots = load_corpus(GROUND_TRUTH_DIR / "snapshots")
        footer_text = "\n\n".join(
            detect_shared_block([d.body for d in snapshots], min_pages=20)
        )
        result = score(outcomes, subset, footer_text=footer_text)
        run.end(outputs={k: v for k, v in result.items() if k != "misses"})

    result["run_seconds"] = round(time.monotonic() - started, 1)
    result["llm_calls_live"] = invoke.calls_live
    result["llm_calls_cached"] = invoke.calls_cached
    result["full_run"] = subset is None

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{args.name}.json"
    out_path.write_text(json.dumps(result, indent=1), encoding="utf-8")

    print(json.dumps({k: v for k, v in result.items() if k != "misses"}, indent=1))
    print(f"misses: {len(result['misses'])} (full list in {out_path})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
