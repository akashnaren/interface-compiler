"""Mutating affordances on a real site cannot be recorded as probed_ok."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from interface_compiler.contract import ContractError, ViewDoc, validate_doc, validate_effect
from interface_compiler.contract.models import AffordanceX

ROOT = Path(__file__).resolve().parents[2]
PAPER_PATH = ROOT / "tests" / "fixtures" / "paper_example.json"


def _paper() -> dict:
    return json.loads(PAPER_PATH.read_text(encoding="utf-8"))


def _with_probe(
    url: str | None,
    *,
    tag: str | None,
    verified: str = "probed_ok",
    loose_page: bool = False,
) -> dict:
    doc = _paper()
    extra: dict[str, object] = {}
    if url is not None:
        extra["url"] = url
    # page stays an open object in the frozen schema. A loose value must not
    # be required for the probe check, and must not be echoed into its error.
    if loose_page:
        extra["page"] = {"products": "not-a-cursor"}
    doc["x"] = extra
    affordance_x: dict[str, object] = {"verified": verified}
    if tag is not None:
        affordance_x["tag"] = tag
    doc["affordances"][2]["x"] = affordance_x
    return doc


def test_checker_mutating_probed_ok_rejected_on_real_site() -> None:
    doc = _with_probe("https://example.com/product", tag="mutating", loose_page=True)
    with pytest.raises(ContractError) as exc:
        validate_doc(doc)
    message = str(exc.value)
    assert "affordances/2/x/verified" in message
    assert "mutating affordance cannot be probed_ok" in message
    assert "not-a-cursor" not in message
    with pytest.raises(ValidationError) as model_error:
        ViewDoc.model_validate(doc)
    assert "mutating affordance cannot be probed_ok" in str(model_error.value)


def test_checker_missing_tag_is_treated_as_mutating() -> None:
    doc = _with_probe("https://example.com/product", tag=None)
    with pytest.raises(ContractError) as exc:
        validate_doc(doc)
    assert "mutating affordance cannot be probed_ok" in str(exc.value)


def test_checker_missing_url_is_not_a_fixture_host() -> None:
    doc = _with_probe(None, tag="mutating")
    with pytest.raises(ContractError) as exc:
        validate_doc(doc)
    assert "mutating affordance cannot be probed_ok" in str(exc.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:9/minishop/product.html",
        "http://localhost/fixture",
        "http://[::1]/fixture",
    ],
)
def test_checker_loopback_mutating_may_be_probed_ok(url: str) -> None:
    doc = _with_probe(url, tag="mutating")
    validate_doc(doc)
    assert ViewDoc.model_validate(doc).affordances[2].x is not None


def test_checker_safe_probe_is_allowed_on_a_real_site() -> None:
    doc = _with_probe("https://example.com/product", tag="safe")
    validate_doc(doc)


def test_checker_stopped_before_commit_is_allowed_on_a_real_site() -> None:
    doc = _with_probe(
        "https://example.com/product",
        tag="mutating",
        verified="stopped_before_commit",
    )
    validate_doc(doc)


def test_checker_lookalike_host_is_not_loopback() -> None:
    doc = _with_probe("http://127.0.0.1.example.com/product", tag="mutating")
    with pytest.raises(ContractError) as exc:
        validate_doc(doc)
    assert "mutating affordance cannot be probed_ok" in str(exc.value)


def test_checker_act_response_uses_the_nested_page_url() -> None:
    doc = _with_probe("https://example.com/product", tag="mutating")
    result = {
        "status": "ok",
        "doc_rev": 1,
        "doc": doc,
        "counters": {
            "illegal": 0,
            "malformed": 0,
            "ignored": 0,
            "stale": 0,
            "blocked": 0,
            "acts": 1,
        },
    }
    with pytest.raises(ContractError) as exc:
        validate_effect(result)
    assert "doc/affordances/2/x/verified" in str(exc.value)


def test_checker_setter_refuses_probed_ok_for_mutating_real_site() -> None:
    affordance_x = AffordanceX(tag="mutating", verified="unverified")
    with pytest.raises(ContractError) as exc:
        affordance_x.set_verified("probed_ok", page_url="https://example.com/p")
    assert "mutating affordance cannot be probed_ok" in str(exc.value)
    assert affordance_x.verified == "unverified"
    affordance_x.set_verified(
        "stopped_before_commit",
        page_url="https://example.com/p",
    )
    assert affordance_x.verified == "stopped_before_commit"


def test_checker_setter_allows_loopback_and_safe() -> None:
    mutating = AffordanceX(tag="mutating")
    mutating.set_verified("probed_ok", page_url="http://127.0.0.1/fixture")
    assert mutating.verified == "probed_ok"
    safe = AffordanceX(tag="safe")
    safe.set_verified("probed_ok", page_url="https://example.com/p")
    assert safe.verified == "probed_ok"
    unknown = AffordanceX()
    with pytest.raises(ContractError):
        unknown.set_verified("probed_ok", page_url="https://example.com/p")
