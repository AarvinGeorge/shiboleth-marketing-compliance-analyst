"""
meta:
  purpose: Issue-cluster suggestion layer (roadmap doc 11, clustering C1).
           Groups N6 wording clusters into ISSUE suggestions — the analyst's
           unit of decision ("one problem, one disposition"). Sentry-pattern:
           deterministic fingerprints stay; similar clusters are SUGGESTED
           for merge; a human confirms/rejects; rejections are remembered
           and never re-suggested.
  contract: suggest_issue_groups(clusters, signer, adjudicator,
            rejected_snapshots) -> [IssueSuggestion dicts]. Pure logic; the
            two LLM judgments are injected callables so tests are
            deterministic and CI never calls out. Explainability: every
            suggestion carries per-member signatures AND the adjudicator's
            merge rationale — the UI can always answer "why grouped?".
            Grouping NEVER crosses rules (compliance trust constraint,
            doc 11).
  deps: pydantic; langchain (production callables only).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field

# Fixed violation-mode vocabulary: constrains the signature space so equal
# modes are comparable across wording variants (and across products — the
# modes describe HOW marketing violates, not WHAT product it markets).
ViolationMode = Literal[
    "missing_disclosure", "drifted_wording", "placement",
    "rate_without_apr", "fdic_formulation", "missing_bonus_terms",
    "unapproved_claim", "other",
]


class IssueSignature(BaseModel):
    violation_mode: ViolationMode = Field(description="HOW the material violates (or would violate) the rule, from the fixed vocabulary.")
    subject: str = Field(description="WHAT is at issue, canonical noun phrase, max 6 words, e.g. 'free filing claim' or 'Credit Karma Money FDIC language'.")
    rationale: str = Field(description="One sentence: why this cluster has this signature.")


class MergeVerdict(BaseModel):
    same_issue: bool = Field(description="Would a compliance analyst treat these as ONE problem with one disposition?")
    label: str = Field(description="If same_issue: an issue title in at most 8 words, sentence case (e.g. 'Free claim missing eligibility disclosure'). Empty otherwise.")
    rationale: str = Field(description="One or two sentences explaining the decision; shown to the analyst as 'why grouped'.")


def suggest_issue_groups(
    clusters: list[dict],
    signer: Callable[[dict], IssueSignature],
    adjudicator: Callable[[list[dict]], MergeVerdict],
    rejected_snapshots: list[set[str]] | None = None,
) -> list[dict]:
    """clusters: [{id, rule_id, label, sample_quote}]. Returns suggestions:
    [{member_cluster_ids, label, rationale, signatures: {cid: sig dict}}].
    Only groups of >=2 members become suggestions. A candidate group whose
    member set is a subset of a previously REJECTED snapshot is skipped."""
    rejected = rejected_snapshots or []
    signatures = {c["id"]: signer(c) for c in clusters}

    by_class: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for c in clusters:
        sig = signatures[c["id"]]
        by_class[(c["rule_id"], sig.violation_mode)].append(c)

    suggestions: list[dict] = []
    for (_rule, _mode), members in sorted(by_class.items()):
        if len(members) < 2:
            continue
        member_ids = {m["id"] for m in members}
        if any(member_ids <= snap for snap in rejected):
            continue  # analyst already said no to this grouping
        enriched = [
            {**m, "signature": signatures[m["id"]].model_dump()}
            for m in members
        ]
        verdict = adjudicator(enriched)
        if not verdict.same_issue:
            continue
        suggestions.append({
            "member_cluster_ids": sorted(member_ids),
            "label": verdict.label.strip() or members[0]["label"],
            "rationale": verdict.rationale.strip(),
            "signatures": {m["id"]: signatures[m["id"]].model_dump()
                           for m in members},
        })
    return suggestions


# --- production LLM callables -------------------------------------------

_SIGNER_SYSTEM = (
    "You classify marketing-compliance finding clusters for an analyst "
    "dashboard. Given a rule and one representative evidence quote, emit "
    "the cluster's issue signature. Be product-agnostic: describe the "
    "violation pattern, not the brand."
)

_ADJUDICATOR_SYSTEM = (
    "You are a marketing-compliance analyst deciding whether several "
    "finding clusters are ONE underlying issue deserving a single "
    "disposition, or genuinely distinct problems. Different wording of the "
    "same problem = one issue. Different obligations, products, or failure "
    "modes = distinct. Be conservative: when unsure, same_issue=false — a "
    "wrong merge damages analyst trust more than a missed one. Your "
    "rationale is shown to the analyst verbatim."
)


def production_signer(model_string: str) -> Callable[[dict], IssueSignature]:
    from langchain.chat_models import init_chat_model
    bound = init_chat_model(model_string, temperature=0,
                            timeout=60, max_retries=2
                            ).with_structured_output(IssueSignature)

    def sign(cluster: dict) -> IssueSignature:
        return bound.invoke([
            {"role": "system", "content": _SIGNER_SYSTEM},
            {"role": "user", "content": (
                f"Rule {cluster['rule_id']} (verbatim): "
                f"{cluster.get('rule_text', '')}\n"
                f"Cluster label: {cluster['label']}\n"
                f"Representative evidence quote:\n{cluster['sample_quote'][:600]}"
            )},
        ])
    return sign


def production_adjudicator(model_string: str) -> Callable[[list[dict]], MergeVerdict]:
    from langchain.chat_models import init_chat_model
    bound = init_chat_model(model_string, temperature=0,
                            timeout=60, max_retries=2
                            ).with_structured_output(MergeVerdict)

    def adjudicate(members: list[dict]) -> MergeVerdict:
        blocks = "\n\n".join(
            f"Cluster {i + 1} [{m['signature']['violation_mode']} / "
            f"{m['signature']['subject']}]:\n\"{m['sample_quote'][:400]}\""
            for i, m in enumerate(members)
        )
        return bound.invoke([
            {"role": "system", "content": _ADJUDICATOR_SYSTEM},
            {"role": "user", "content": (
                f"Rule {members[0]['rule_id']}. Are these clusters one "
                f"issue?\n\n{blocks}"
            )},
        ])
    return adjudicate
