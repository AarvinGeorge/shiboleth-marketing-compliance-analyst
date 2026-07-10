"""
meta:
  purpose: Unit tests (first) for N6 clustering — grouping is pure code:
           flags cluster by (check_id, normalized evidence quote). The
           template-propagation case (identical footer drift on 44 pages)
           must collapse into ONE cluster. Labeling is injected (no LLM in
           unit tests).
  contract: cluster_flags(flags, labeler) -> list of clusters with stable
            member ordering; singletons stay unclustered (cluster_id None).
  deps: pytest.
"""

from shiboleth.pipeline.nodes.cluster import cluster_flags


def flag(fid: str, check_id: str, quote: str) -> dict:
    return {"id": fid, "check_id": check_id, "evidence_quote": quote}


def test_identical_evidence_same_check_clusters():
    flags = [
        flag("f1", "R-01-REQ", "Roughly 37% of taxpayers qualify."),
        flag("f2", "R-01-REQ", "Roughly 37%  of taxpayers qualify."),  # ws differs
        flag("f3", "R-01-REQ", "roughly 37% of taxpayers qualify."),  # case differs
    ]
    clusters = cluster_flags(flags, labeler=lambda quotes: "Footer drift")
    assert len(clusters) == 1
    assert set(clusters[0]["member_flag_ids"]) == {"f1", "f2", "f3"}
    assert clusters[0]["label"] == "Footer drift"


def test_different_checks_never_cluster():
    flags = [
        flag("f1", "R-01-REQ", "same words"),
        flag("f2", "R-03-REQ", "same words"),
    ]
    assert cluster_flags(flags, labeler=lambda q: "x") == []


def test_singletons_stay_unclustered():
    flags = [flag("f1", "R-01-REQ", "unique quote one"),
             flag("f2", "R-01-REQ", "another unique quote")]
    assert cluster_flags(flags, labeler=lambda q: "x") == []


def test_labeler_called_once_per_cluster_with_sample():
    calls = []

    def labeler(quotes):
        calls.append(quotes)
        return "label"

    flags = [flag(f"f{i}", "R-02-REQ", "loan fee 4%") for i in range(5)]
    clusters = cluster_flags(flags, labeler=labeler)
    assert len(clusters) == 1 and len(calls) == 1
    assert calls[0][0] == "loan fee 4%"
