"""
meta:
  purpose: Unit tests for the corpus loader (written before implementation).
           Corpus mode is the acceptance path (08 §2): snapshots bind by
           sha256-of-stripped-body; a hash mismatch must be a hard error,
           never a silent skip (never fabricate/alter ground truth).
  contract: parse_snapshot handles the snapshot front-matter format;
            load_corpus verifies every hash; the real-corpus test covers all
            54 pages + 17 synthetics when ground-truth/ is present.
  deps: pytest; ../ground-truth for the real-corpus test (skipped if absent).
"""

import hashlib

import pytest

from adlign.config import REPO_ROOT
from adlign.services.ingestion.corpus import (
    CorpusIntegrityError,
    load_corpus,
    parse_snapshot,
)

GROUND_TRUTH = REPO_ROOT.parent / "ground-truth"


def make_snapshot(body: str, sha: str | None = None, extra: str = "") -> str:
    # plain concatenation: dedent breaks on interpolated unindented lines
    digest = sha or hashlib.sha256(body.strip().encode()).hexdigest()
    return (
        "---\n"
        "id: T01\n"
        "url: https://example.com/\n"
        "discovery: free\n"
        "fetched_at: 2026-07-10T01:00:00Z\n"
        "fetcher: crawl4ai\n"
        f"content_sha256: {digest}\n"
        "quality: good\n"
        "notes: test fixture\n"
        f"{extra}---\n\n{body}\n"
    )


class TestParseSnapshot:
    def test_parses_front_matter_and_body(self):
        doc = parse_snapshot(make_snapshot("Hello marketing world."), source="T01.md")
        assert doc.page_id == "T01"
        assert doc.url == "https://example.com/"
        assert doc.body == "Hello marketing world."
        assert doc.synthetic is False

    def test_hash_verified_on_parse(self):
        with pytest.raises(CorpusIntegrityError, match="T01"):
            parse_snapshot(
                make_snapshot("Body text.", sha="0" * 64), source="T01.md"
            )

    def test_synthetic_flag_read(self):
        doc = parse_snapshot(
            make_snapshot("Synthetic body.", extra="synthetic: true\n"),
            source="S99.md",
        )
        assert doc.synthetic is True

    def test_body_hash_uses_stripped_convention(self):
        # trailing newlines in the file must not break hash verification
        body = "Line one.\n\nLine two."
        doc = parse_snapshot(make_snapshot(body + "\n\n"), source="T01.md")
        assert doc.content_hash == hashlib.sha256(body.strip().encode()).hexdigest()


needs_corpus = pytest.mark.skipif(
    not GROUND_TRUTH.exists(), reason="ground-truth/ not present (standalone clone)"
)


@needs_corpus
class TestRealCorpus:
    def test_loads_54_snapshots_all_hashes_verify(self):
        docs = load_corpus(GROUND_TRUTH / "snapshots")
        assert len(docs) == 54
        assert all(not d.synthetic for d in docs)

    def test_loads_17_synthetics_all_hashes_verify(self):
        docs = load_corpus(GROUND_TRUTH / "snapshots-synthetic")
        assert len(docs) == 17
        assert all(d.synthetic for d in docs)
        assert any(d.page_id == "S17" for d in docs)

    def test_page_ids_unique_across_both_sets(self):
        all_docs = load_corpus(GROUND_TRUTH / "snapshots") + load_corpus(
            GROUND_TRUTH / "snapshots-synthetic"
        )
        ids = [d.page_id for d in all_docs]
        assert len(ids) == len(set(ids)) == 71
