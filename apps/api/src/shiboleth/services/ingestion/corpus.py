"""
meta:
  purpose: Corpus loader — the input side of corpus-mode runs (08 §2), reading
           the frozen ground-truth snapshots + synthetic fixtures. Ground
           truth binds by content hash, so every file's sha256-of-stripped-
           body is verified on parse; a mismatch is a hard CorpusIntegrityError
           (never a silent skip, never fabricated content).
  contract: parse_snapshot(text, source) -> CorpusDoc (verified);
            load_corpus(dir) -> [CorpusDoc] sorted by page_id, all verified.
            Pure file I/O, no DB, no network.
  deps: stdlib + shiboleth.services.scoring.formulas.content_hash (the single
        hash implementation — do not reimplement).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from shiboleth.services.scoring.formulas import content_hash


class CorpusIntegrityError(RuntimeError):
    """A snapshot's body no longer matches its recorded content_sha256."""


@dataclass(frozen=True)
class CorpusDoc:
    page_id: str
    url: str
    discovery: str
    fetcher: str
    content_hash: str
    body: str
    synthetic: bool
    source: str


def parse_snapshot(text: str, source: str) -> CorpusDoc:
    if not text.startswith("---"):
        raise CorpusIntegrityError(f"{source}: missing front matter")
    try:
        _, front, body = text.split("---", 2)
    except ValueError as exc:
        raise CorpusIntegrityError(f"{source}: malformed front matter") from exc

    fields: dict[str, str] = {}
    for line in front.strip().splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()

    body = body.strip()
    recorded = fields.get("content_sha256", "")
    actual = content_hash(body)
    page_id = fields.get("id", "?")
    if actual != recorded:
        raise CorpusIntegrityError(
            f"{source}: hash mismatch for {page_id}: "
            f"recorded {recorded[:12]}…, computed {actual[:12]}…"
        )

    return CorpusDoc(
        page_id=page_id,
        url=fields.get("url", ""),
        discovery=fields.get("discovery", ""),
        fetcher=fields.get("fetcher", ""),
        content_hash=actual,
        body=body,
        synthetic=fields.get("synthetic", "").lower() == "true",
        source=source,
    )


def load_corpus(directory: Path) -> list[CorpusDoc]:
    docs = [
        parse_snapshot(path.read_text(encoding="utf-8"), source=path.name)
        for path in sorted(directory.glob("*.md"))
    ]
    return sorted(docs, key=lambda d: d.page_id)
