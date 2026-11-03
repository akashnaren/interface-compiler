"""Mutating affordances on a real site cannot be recorded as probed_ok."""

import json
from pathlib import Path

import pydantic_core
import pytest
from pydantic import TypeAdapter, ValidationError

from interface_compiler.browser.facts import normalized_page_url
from interface_compiler.contract import (
    ActResult,
    ContractError,
    DocX,
    ViewDoc,
    dump_act_result,
    dump_view_doc,
    validate_doc,
    validate_effect,
)
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
        "https://127.0.0.1/fixture",
        "http://127.0.0.1:80/fixture",
        "HTTP://LocalHost/fixture",
        "http://[::1]:443/fixture",
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


_NOT_LOOPBACK = (
    "http://evil.com\\@127.0.0.1/",
    "http://user@127.0.0.1/",
    "javascript://127.0.0.1/",
    "ws://127.0.0.1/",
    "file://localhost/tmp/x",
    "//127.0.0.1/",
    "http://127.0.0.1:99999/",
    "http://127.0.0.1:0/x",
    "http://127.0.0.1:/x",
    "http://127.0.0.1:²/",
    "http://[::1]:³/",
    "http://127.0.0.1:" + ("1" * 5000) + "/",
    "http://127.0.0.1:８０/",
    "http://127.0.0.1:٨٠/",
    "http://127.0.0.1 /x",
    "http://127.0.0.1/\n",
    "http://127.0.0.1/\x00x",
    "http://127.0.0.1/\x7fx",
)


@pytest.mark.parametrize("url", _NOT_LOOPBACK)
def test_checker_spoofed_loopback_cannot_be_probed_ok(url: str) -> None:
    doc = _with_probe(url, tag="mutating")
    with pytest.raises(ContractError) as doc_error:
        validate_doc(doc)
    assert "mutating affordance cannot be probed_ok" in str(doc_error.value)
    with pytest.raises(ValidationError) as model_error:
        ViewDoc.model_validate(doc)
    assert "mutating affordance cannot be probed_ok" in str(model_error.value)
    with pytest.raises(ValidationError) as json_error:
        ViewDoc.model_validate_json(json.dumps(doc))
    assert "mutating affordance cannot be probed_ok" in str(json_error.value)
    row = AffordanceX(tag="mutating", verified="unverified")
    with pytest.raises(ContractError) as setter_error:
        row.set_verified("probed_ok", page_url=url)
    assert "mutating affordance cannot be probed_ok" in str(setter_error.value)
    assert row.verified == "unverified"


def test_checker_direct_assignment_refuses_probed_ok_without_a_page_url() -> None:
    row = AffordanceX(tag="mutating", verified="unverified")
    with pytest.raises(ContractError) as exc:
        row.verified = "probed_ok"
    assert "mutating affordance cannot be probed_ok" in str(exc.value)
    assert row.verified == "unverified"
    row.verified = "probed_failed"
    assert row.verified == "probed_failed"
    missing = AffordanceX(verified="unverified")
    with pytest.raises(ContractError):
        missing.verified = "probed_ok"
    assert missing.verified == "unverified"
    safe = AffordanceX(tag="safe", verified="unverified")
    safe.verified = "probed_ok"
    assert safe.verified == "probed_ok"
    with pytest.raises(ContractError) as unknown:
        row.verified = "nope"
    assert "not a probe outcome" in str(unknown.value)
    assert row.verified == "probed_failed"


def test_checker_normalized_page_url_allows_a_loopback_probe(
    facts_page,
    fixture_base_url: str,
) -> None:
    facts_page.goto(f"{fixture_base_url}/link.html", wait_until="domcontentloaded")
    url = normalized_page_url(facts_page)
    assert url.startswith("http://127.0.0.1:")
    doc = _with_probe(url, tag="mutating")
    validate_doc(doc)
    assert ViewDoc.model_validate(doc).affordances[2].x is not None
    assert ViewDoc.model_validate_json(json.dumps(doc)).affordances[2].x is not None
    row = AffordanceX(tag="mutating", verified="unverified")
    row.set_verified("probed_ok", page_url=url)
    assert row.verified == "probed_ok"
    spoof = "http://evil.com\\@127.0.0.1/"
    with pytest.raises(ContractError):
        row.set_verified("probed_ok", page_url=spoof)


@pytest.mark.parametrize("path", ["construct", "retag", "copy"])
def test_checker_mutating_probed_ok_cannot_be_built(path: str) -> None:
    if path == "construct":
        with pytest.raises(ContractError) as exc:
            AffordanceX(tag="mutating", verified="probed_ok")
        assert "mutating affordance cannot be probed_ok" in str(exc.value)
        return
    if path == "retag":
        row = AffordanceX(tag="safe")
        row.verified = "probed_ok"
        with pytest.raises(ContractError) as exc:
            row.tag = "mutating"
        assert "mutating affordance cannot be probed_ok" in str(exc.value)
        assert row.tag == "safe"
        assert row.verified == "probed_ok"
        return
    if path == "copy":
        row = AffordanceX(tag="mutating", verified="unverified")
        with pytest.raises(ContractError) as exc:
            row.model_copy(update={"verified": "probed_ok"})
        assert "mutating affordance cannot be probed_ok" in str(exc.value)
        assert row.verified == "unverified"
        return
    raise AssertionError(path)


@pytest.mark.parametrize("path", ["setter", "assign", "copy"])
def test_checker_document_probe_follows_the_document_url(path: str) -> None:
    if path == "setter":
        doc = ViewDoc.model_validate(
            _with_probe("https://example.com/p", tag="mutating", verified="unverified")
        )
        row = doc.affordances[2].x
        assert row is not None
        with pytest.raises(ContractError) as exc:
            row.set_verified("probed_ok", page_url="http://127.0.0.1/x")
        assert "mutating affordance cannot be probed_ok" in str(exc.value)
        assert row.verified == "unverified"
        return
    doc = ViewDoc.model_validate(_with_probe("http://127.0.0.1/x", tag="mutating"))
    assert doc.x is not None
    if path == "assign":
        with pytest.raises(ContractError) as exc:
            doc.x.url = "https://example.com/other"
        assert "mutating affordance cannot be probed_ok" in str(exc.value)
        assert doc.x.url == "http://127.0.0.1/x"
        dump_view_doc(doc)
        return
    if path == "copy":
        with pytest.raises(ContractError) as exc:
            doc.model_copy(update={"x": DocX(url="https://example.com/other")})
        assert "mutating affordance cannot be probed_ok" in str(exc.value)
        assert doc.x.url == "http://127.0.0.1/x"
        dump_view_doc(doc)
        return
    raise AssertionError(path)


def _public_probe_bypassing_the_url_guard() -> ViewDoc:
    """A probed loopback document whose URL was replaced without the guard."""
    doc = ViewDoc.model_validate(_with_probe("http://127.0.0.1/x", tag="mutating"))
    assert doc.x is not None
    doc.x._guard_url = None
    doc.x.url = "https://example.com/p"
    return doc


@pytest.mark.parametrize(
    "path",
    ["setter", "model_dump", "model_dump_json", "act_dump", "replace_x"],
)
def test_checker_serialized_probe_matches_the_document_url(path: str) -> None:
    if path == "setter":
        legal = ViewDoc.model_validate(
            _with_probe("http://127.0.0.1/x", tag="mutating", verified="unverified")
        )
        legal_row = legal.affordances[2].x
        assert legal_row is not None
        legal_row.set_verified("probed_ok", page_url="http://127.0.0.1/x")
        assert legal_row.verified == "probed_ok"
        dump_view_doc(legal)
        public = ViewDoc.model_validate(
            _with_probe("https://example.com/p", tag="mutating", verified="unverified")
        )
        row = public.affordances[2].x
        assert row is not None
        with pytest.raises(ContractError) as exc:
            row.set_verified("probed_ok", page_url="http://127.0.0.1/x")
        assert "mutating affordance cannot be probed_ok" in str(exc.value)
        assert row.verified == "unverified"
        return
    if path == "replace_x":
        owned = ViewDoc.model_validate(
            _with_probe("https://example.com/p", tag="mutating", verified="unverified")
        )
        row = owned.affordances[2]
        row.x = AffordanceX(tag="mutating")
        replaced = row.x
        assert replaced is not None
        with pytest.raises(ContractError, match="mutating affordance cannot be probed_ok"):
            replaced.set_verified("probed_ok", page_url="http://127.0.0.1/x")
        assert replaced.verified is None
        extra = json.loads(owned.model_dump_json())["affordances"][2]["x"]
        assert extra.get("verified") != "probed_ok"
        return
    doc = _public_probe_bypassing_the_url_guard()
    if path == "model_dump":
        with pytest.raises(ContractError) as exc:
            doc.model_dump()
        assert "mutating affordance cannot be probed_ok" in str(exc.value)
        return
    if path == "model_dump_json":
        with pytest.raises(ContractError) as exc:
            doc.model_dump_json()
        assert "mutating affordance cannot be probed_ok" in str(exc.value)
        return
    if path == "act_dump":
        result = ActResult.model_validate(
            {
                "status": "ok",
                "doc_rev": 1,
                "doc": _with_probe("http://127.0.0.1/x", tag="mutating"),
                "counters": {
                    "illegal": 0,
                    "malformed": 0,
                    "ignored": 0,
                    "stale": 0,
                    "blocked": 0,
                    "acts": 1,
                },
            }
        )
        result.doc = doc
        with pytest.raises(ContractError) as exc:
            dump_act_result(result)
        assert "mutating affordance cannot be probed_ok" in str(exc.value)
        with pytest.raises(ContractError):
            result.model_dump()
        return
    raise AssertionError(path)


def _dump_probe(model: ViewDoc | ActResult, dump: str) -> None:
    if dump == "model_dump":
        model.model_dump()
        return
    if dump == "model_dump_json":
        model.model_dump_json()
        return
    if dump == "to_json":
        pydantic_core.to_json(model)
        return
    if dump == "dump_json":
        TypeAdapter(type(model)).dump_json(model)
        return
    if dump == "dump_python":
        TypeAdapter(type(model)).dump_python(model)
        return
    raise AssertionError(dump)


@pytest.mark.parametrize(
    "dump",
    ["model_dump", "model_dump_json", "to_json", "dump_json", "dump_python"],
)
def test_checker_serializers_refuse_a_public_probe(dump: str) -> None:
    doc = _public_probe_bypassing_the_url_guard()
    with pytest.raises(ContractError, match="mutating affordance cannot be probed_ok"):
        _dump_probe(doc, dump)
    result = ActResult.model_validate(
        {
            "status": "ok",
            "doc_rev": 1,
            "doc": _with_probe("http://127.0.0.1/x", tag="mutating"),
            "counters": {
                "illegal": 0,
                "malformed": 0,
                "ignored": 0,
                "stale": 0,
                "blocked": 0,
                "acts": 1,
            },
        }
    )
    result.doc = doc
    with pytest.raises(ContractError, match="mutating affordance cannot be probed_ok"):
        _dump_probe(result, dump)


@pytest.mark.parametrize(
    ("url", "tag", "accepted"),
    [
        ("https://example.com/p", "mutating", False),
        ("https://example.com/p", "safe", True),
        ("http://127.0.0.1/x", "mutating", True),
    ],
)
def test_checker_later_affordance_x_keeps_the_document_url(
    url: str,
    tag: str,
    accepted: bool,
) -> None:
    doc = ViewDoc.model_validate(_with_probe(url, tag="safe", verified="unverified"))
    bare = doc.affordances[0]
    assert bare.x is None
    row = AffordanceX(tag=tag, verified="unverified")
    if tag == "mutating":
        row.set_verified("probed_ok", page_url="http://127.0.0.1/x")
    else:
        row.verified = "probed_ok"
    assert row.verified == "probed_ok"
    if not accepted:
        with pytest.raises(ContractError, match="mutating affordance cannot be probed_ok"):
            bare.x = row
        assert bare.x is None
        assert row.verified == "probed_ok"
        bare.x = AffordanceX(tag="mutating")
        with pytest.raises(ContractError, match="mutating affordance cannot be probed_ok"):
            bare.x.set_verified("probed_ok", page_url="http://127.0.0.1/x")
        assert bare.x is not None
        assert bare.x.verified is None
        return
    bare.x = row
    assert bare.x is row
    assert row.verified == "probed_ok"
    with pytest.raises(ContractError, match="page_url does not match"):
        row.set_verified("probed_ok", page_url="https://example.com/other")
    assert row.verified == "probed_ok"


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
