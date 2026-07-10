"""
meta:
  purpose: N6 clustering (01_spec §4). v1 groups flags by (check_id,
           normalized evidence quote) — pure code; captures the core
           template-propagation case (one edit -> N identical flags -> ONE
           analyst decision). LLM labeler injected (Groq per-stage model);
           singleton groups stay unclustered.
  limitation: identical-wording only. Day-2: pgvector embedding similarity
           for near-duplicate wording (logged in code/CLAUDE.md backlog with
           the retrieval upgrade). Google embeddings quota-dead + Groq has no
           embedding endpoint -> $0 rule keeps v1 lexical.
  contract: cluster_flags(flags, labeler) -> [{key, label, member_flag_ids}].
  deps: stdlib; labeler: (sample quotes) -> str.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable

_WS = re.compile(r"\s+")


def _norm(quote: str) -> str:
    return _WS.sub(" ", quote).strip().lower()


def cluster_flags(
    flags: list[dict], labeler: Callable[[list[str]], str]
) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for f in flags:
        groups[(f["check_id"], _norm(f["evidence_quote"]))].append(f)

    clusters = []
    for (check_id, norm_quote), members in groups.items():
        if len(members) < 2:
            continue
        sample = [members[0]["evidence_quote"]]
        clusters.append({
            "key": f"{check_id}:{norm_quote[:60]}",
            "label": labeler(sample),
            "member_flag_ids": [m["id"] for m in members],
        })
    return clusters


def groq_labeler(model_string: str) -> Callable[[list[str]], str]:
    """Production labeler: one short LLM call per cluster."""
    from langchain.chat_models import init_chat_model

    model = init_chat_model(model_string, temperature=0)

    def label(quotes: list[str]) -> str:
        reply = model.invoke(
            "Name this compliance-finding cluster in at most 6 words, "
            "sentence case, no punctuation at the end. The repeated evidence "
            f"is: {quotes[0][:300]}"
        )
        return str(reply.content).strip()

    return label
