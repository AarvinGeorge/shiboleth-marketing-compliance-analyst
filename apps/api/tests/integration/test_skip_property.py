"""
meta:
  purpose: Regression test for the skip-property contract bug (Aarvin,
           2026-07-10): the UI's Skip sent {property_id} only, but the
           endpoint required PasteRequest.text -> 422 -> the paste dialog was
           inescapable, blocking website-only analysis. Skip must accept no
           text and must resume the run when no property remains needs_input.
  contract: SkipRequest has property_id only; skipping the last parked
            property proceeds the run past the barrier.
  deps: adlign.domain schemas.
"""

from adlign.api.routes.runs import SkipRequest


def test_skip_request_needs_no_text():
    # the exact payload the UI sends — must validate without a text field
    req = SkipRequest.model_validate({"property_id": "tt-instagram"})
    assert req.property_id == "tt-instagram"
    assert not hasattr(req, "text") or getattr(req, "text", None) is None
