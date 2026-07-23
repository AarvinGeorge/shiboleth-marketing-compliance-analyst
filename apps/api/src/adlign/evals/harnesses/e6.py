"""
meta:
  purpose: E6 — issue-grouping quality harness (clustering C1). Scores the
           signer+adjudicator pipeline against the golden pair set: for each
           labeled pair of flag quotes, does the issue layer group them iff
           an analyst would? Metrics: accuracy, precision/recall/F1 on the
           "same issue" class. Each run is a named LangSmith experiment
           (e6-*), same discipline as E3/E5.
  contract: python -m adlign.evals.harnesses.e6 --name e6-baseline
            [--model provider:id]. Results -> evals/results/<name>.json.
            Golden set grows via analyst confirm/reject dispositions.
  deps: pipeline.nodes.issues, config, langsmith.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from adlign.config import load_settings
from adlign.main import propagate_env
from adlign.pipeline.nodes.issues import (production_adjudicator,
                                             production_signer)

HERE = Path(__file__).resolve().parent
GOLDEN = HERE.parent / "golden" / "e6_issue_pairs.json"
RESULTS_DIR = HERE.parent / "results"


def predict_same(signer, adjudicator, pair: dict) -> tuple[bool, dict]:
    a = {"id": "a", "rule_id": pair["rule_id"], "label": "cluster a",
         "sample_quote": pair["quote_a"]}
    b = {"id": "b", "rule_id": pair["rule_id"], "label": "cluster b",
         "sample_quote": pair["quote_b"]}
    sig_a, sig_b = signer(a), signer(b)
    detail = {"sig_a": sig_a.model_dump(), "sig_b": sig_b.model_dump()}
    if sig_a.violation_mode != sig_b.violation_mode:
        detail["decided_by"] = "signature_mode_mismatch"
        return False, detail
    verdict = adjudicator([
        {**a, "signature": sig_a.model_dump()},
        {**b, "signature": sig_b.model_dump()},
    ])
    detail["decided_by"] = "adjudicator"
    detail["verdict"] = verdict.model_dump()
    return verdict.same_issue, detail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    settings = load_settings()
    propagate_env(settings)
    model = args.model or settings.model_for("issue")
    signer = production_signer(model)
    adjudicator = production_adjudicator(model)
    pairs = json.loads(GOLDEN.read_text())["pairs"]

    from langsmith import trace
    t0 = time.time()
    tp = fp = fn = tn = 0
    misses = []
    with trace(name=args.name, project_name=settings.langsmith_project,
               inputs={"harness": "e6", "model": model,
                       "pairs": len(pairs)}) as run:
        for p in pairs:
            got, detail = predict_same(signer, adjudicator, p)
            want = p["same_issue"]
            if got and want:
                tp += 1
            elif got and not want:
                fp += 1
                misses.append({"id": p["id"], "want": want, "got": got,
                               "detail": detail})
            elif not got and want:
                fn += 1
                misses.append({"id": p["id"], "want": want, "got": got,
                               "detail": detail})
            else:
                tn += 1
            print(f"  {p['id']}: want={want} got={got} "
                  f"({detail['decided_by']})")
        n = len(pairs)
        result = {
            "accuracy": round((tp + tn) / n, 4),
            "precision_same": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall_same": round(tp / (tp + fn), 4) if tp + fn else None,
            "n_pairs": n, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "model": model,
        }
        run.end(outputs=result)

    result["run_seconds"] = round(time.time() - t0, 1)
    result["misses"] = misses
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{args.name}.json"
    out.write_text(json.dumps(result, indent=1))
    for k, v in result.items():
        if k != "misses":
            print(f"{k}: {v}")
    print(f"misses: {len(misses)} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
