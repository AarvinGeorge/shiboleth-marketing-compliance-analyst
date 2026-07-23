"""
meta:
  purpose: Unit tests for the issue-cluster suggestion layer (pure logic;
           LLM judgments injected as deterministic fakes — CI never calls out).
  contract: suggestions only within one rule; >=2 members; adjudicator can
            veto; rejected snapshots are never re-suggested; every suggestion
            carries signatures + rationale (explainability contract).
  deps: pytest.
"""

from adlign.pipeline.nodes.issues import (
    IssueSignature,
    MergeVerdict,
    suggest_issue_groups,
)


def _cluster(cid, rule, quote, label="some cluster"):
    return {"id": cid, "rule_id": rule, "label": label, "sample_quote": quote}


def _signer(cluster) -> IssueSignature:
    mode = ("missing_disclosure" if "free" in cluster["sample_quote"]
            else "fdic_formulation")
    return IssueSignature(violation_mode=mode, subject="free filing claim",
                          rationale="test signature")


def _merge_all(members) -> MergeVerdict:
    return MergeVerdict(same_issue=True, label="Free claim missing disclosure",
                        rationale="same obligation, different wording")


def _merge_none(members) -> MergeVerdict:
    return MergeVerdict(same_issue=False, label="", rationale="distinct")


class TestSuggestIssueGroups:
    def test_same_rule_same_mode_becomes_one_suggestion(self):
        clusters = [
            _cluster("c1", "R-01", "File 100% free with TurboTax"),
            _cluster("c2", "R-01", "File your taxes for $0, free of charge"),
        ]
        out = suggest_issue_groups(clusters, _signer, _merge_all)
        assert len(out) == 1
        s = out[0]
        assert s["member_cluster_ids"] == ["c1", "c2"]
        assert s["label"] == "Free claim missing disclosure"
        assert s["rationale"]  # explainability is mandatory
        assert set(s["signatures"]) == {"c1", "c2"}

    def test_never_groups_across_rules(self):
        clusters = [
            _cluster("c1", "R-01", "free filing"),
            _cluster("c2", "R-03", "free checking account FDIC"),
        ]
        assert suggest_issue_groups(clusters, _signer, _merge_all) == []

    def test_adjudicator_veto_blocks_suggestion(self):
        clusters = [
            _cluster("c1", "R-01", "free filing"),
            _cluster("c2", "R-01", "free expert review"),
        ]
        assert suggest_issue_groups(clusters, _signer, _merge_none) == []

    def test_rejected_snapshot_never_resuggested(self):
        clusters = [
            _cluster("c1", "R-01", "free filing"),
            _cluster("c2", "R-01", "free to file"),
        ]
        out = suggest_issue_groups(
            clusters, _signer, _merge_all,
            rejected_snapshots=[{"c1", "c2", "c9"}],  # superset rejected
        )
        assert out == []

    def test_singletons_stay_unsuggested(self):
        clusters = [_cluster("c1", "R-01", "free filing")]
        assert suggest_issue_groups(clusters, _signer, _merge_all) == []
