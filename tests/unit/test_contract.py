"""Unit tests for the frozen v1 compiled view document contract."""

import json
import re
import signal
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from interface_compiler.cli import app
from interface_compiler.contract import (
    ActResult,
    ContractError,
    Effect,
    ViewDoc,
    ablate,
    count_tokens,
    dump_act_result,
    dump_view_doc,
    load_schema,
    strip_x,
    to_flat_tools,
    token_counts,
    validate_args,
    validate_doc,
    validate_effect,
)
from interface_compiler.contract.models import ClientValidation, Counters
from interface_compiler.contract.validate import _check_json_shape

ROOT = Path(__file__).resolve().parents[2]
PAPER_PATH = ROOT / "tests" / "fixtures" / "paper_example.json"
RUNNER = CliRunner()


def _paper() -> dict:
    return json.loads(PAPER_PATH.read_text(encoding="utf-8"))


def _fenced_json(path: Path, heading: str) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"{re.escape(heading)}.*?```json\n(.*?)\n```", text, re.DOTALL)
    if match is None:
        raise AssertionError(f"no JSON fence under {heading} in {path.name}")
    return json.loads(match.group(1))


def _act_result() -> dict:
    return {
        "status": "ok",
        "doc_rev": 1,
        "doc": _paper(),
        "effect": {
            "predicted": {"kind": "state_change", "detail": {"selected_size": "L"}},
            "observed": {
                "url_before": "http://127.0.0.1/product",
                "url_after": "http://127.0.0.1/product",
                "view_before": "product",
                "view_after": "product",
                "state_diff": {"selected_size": {"before": None, "after": "L"}},
                "entities_diff": {},
                "main_status": 200,
                "dialogs": [],
                "console_errors": [],
            },
            "match": True,
            "blocked_requests": [
                {
                    "method": "POST",
                    "url": "http://127.0.0.1/cart",
                    "fields": {"card": "<redacted>"},
                    "reason": "non-GET aborted",
                }
            ],
            "demoted": [],
        },
        "counters": {
            "illegal": 0,
            "malformed": 0,
            "ignored": 0,
            "stale": 0,
            "blocked": 0,
            "acts": 1,
        },
    }


def test_contract_view_doc_schema_matches_plan() -> None:
    expected = _fenced_json(ROOT / "PLAN.md", "### 3.2 `view-doc.v1.json`")
    assert load_schema("view-doc") == expected


def test_contract_schema_ids_and_required_keys() -> None:
    view_doc = load_schema("view-doc")
    effect = load_schema("effect")
    assert view_doc["$id"] == "urn:interface-compiler:schema:view-doc:1"
    assert effect["$id"] == "urn:interface-compiler:schema:effect:1"
    assert sorted(view_doc["required"]) == ["affordances", "entities", "state", "view"]


def test_contract_paper_example_validates() -> None:
    validate_doc(_paper())
    assert ViewDoc.model_validate(_paper()).view == "product"


def test_contract_fifth_top_level_key_fails() -> None:
    doc = _paper()
    doc["extra"] = 1
    with pytest.raises(ContractError):
        validate_doc(doc)


def test_contract_top_level_provenance_fails() -> None:
    doc = _paper()
    doc["provenance"] = {"from": "page"}
    with pytest.raises(ContractError):
        validate_doc(doc)


def test_contract_affordance_extra_key_outside_x_fails() -> None:
    doc = _paper()
    doc["affordances"][0]["label"] = "Open product"
    with pytest.raises(ContractError):
        validate_doc(doc)


def test_contract_empty_required_fails() -> None:
    doc = _paper()
    doc["affordances"][2]["input"]["required"] = []
    with pytest.raises(ContractError):
        validate_doc(doc)


def test_contract_x_is_the_only_extension_point() -> None:
    doc = _paper()
    doc["x"] = {
        "schema_version": "1",
        "source": "compiled",
        "url": "http://127.0.0.1/product",
        "blocked": None,
    }
    doc["affordances"][0]["x"] = {
        "tag": "safe",
        "label": "Open product",
        "source": "owner",
        "locator": {"kind": "ax", "role": "link", "name": "Navy Crew Tee", "owner_key": "z"},
        "verified": "unverified",
        "verified_at": "2026-11-03T03:33:00Z",
    }
    validate_doc(doc)


def test_contract_nested_record_object_fails() -> None:
    doc = _paper()
    doc["entities"]["product"]["price"] = {"amount": 28}
    with pytest.raises(ContractError):
        validate_doc(doc)


def test_contract_flat_state_rejects_lists() -> None:
    doc = _paper()
    doc["state"]["selected_size"] = ["L"]
    with pytest.raises(ContractError):
        validate_doc(doc)


def test_contract_verified_at_must_be_rfc3339() -> None:
    doc = _paper()
    doc["affordances"][0]["x"] = {"verified_at": "yesterday"}
    with pytest.raises(ContractError):
        validate_doc(doc)
    doc["affordances"][0]["x"] = {"verified_at": "2026-11-03T03:33:00Z"}
    validate_doc(doc)
    doc["affordances"][0]["x"] = {"verified_at": "2026-11-03T03:33:00"}
    with pytest.raises(ContractError):
        validate_doc(doc)
    doc["affordances"][0]["x"] = {"verified_at": "2026-02-31T00:00:00Z"}
    with pytest.raises(ContractError):
        validate_doc(doc)


def test_contract_strip_x_yields_exactly_four_keys() -> None:
    doc = _paper()
    doc["x"] = {"schema_version": "1", "source": "compiled", "title": "Navy Crew Tee"}
    doc["affordances"][0]["x"] = {"label": "Open product", "tag": "safe", "reason": "visible"}
    original = json.loads(json.dumps(doc))

    stripped = strip_x(doc)

    assert list(stripped) == ["view", "state", "entities", "affordances"]
    assert all("x" not in affordance for affordance in stripped["affordances"])
    assert stripped["affordances"][0]["id"] == "open_product"
    assert stripped["affordances"][1]["input"]["required"] == ["size"]
    assert doc == original
    validate_doc(stripped)


def test_contract_ablate_removes_enabled_and_constraints() -> None:
    doc = _paper()
    size = doc["affordances"][1]["input"]["properties"]["size"]
    size["pattern"] = "^[SML]$"
    size["minLength"] = 1
    size["maxLength"] = 1
    size["format"] = "tel"
    doc["affordances"][1]["input"]["properties"]["qty"] = {
        "type": "number",
        "minimum": 0,
        "maximum": 10,
        "multipleOf": 0.5,
    }
    doc["affordances"][1]["input"]["properties"]["tags"] = {
        "type": "array",
        "items": {"type": "string", "enum": ["a"], "minLength": 1},
    }
    doc["x"] = {"schema_version": "1"}
    original = json.loads(json.dumps(doc))

    ablated = ablate(doc)

    size_out = ablated["affordances"][1]
    assert "enabled" not in size_out
    assert "required" not in size_out["input"]
    assert size_out["input"]["properties"]["size"] == {"type": "string", "format": "tel"}
    assert size_out["input"]["properties"]["qty"] == {"type": "number", "multipleOf": 0.5}
    assert size_out["input"]["properties"]["tags"] == {
        "type": "array",
        "items": {"type": "string"},
    }
    assert ablated["view"] == "product"
    assert ablated["x"]["schema_version"] == "1"
    assert "enabled" not in ablated["affordances"][5]
    assert doc == original


def test_contract_token_counts_split_core_and_x() -> None:
    doc = _paper()
    base = token_counts(doc)
    assert base.x == 0
    assert base.core == count_tokens(
        json.dumps(strip_x(doc), ensure_ascii=False, separators=(",", ":"))
    )
    assert base.core > 0

    with_x = _paper()
    with_x["x"] = {"schema_version": "1", "title": "Navy Crew Tee"}
    with_x["affordances"][2]["x"] = {"reason": "missing: size", "tag": "mutating"}
    more = token_counts(with_x)
    assert more.core == base.core
    assert more.x > 0


def test_contract_validate_args_checks_input_schema() -> None:
    doc = _paper()
    set_size = doc["affordances"][1]
    add_to_cart = doc["affordances"][2]
    validate_args(set_size, {"size": "L"})
    validate_args(add_to_cart, {})
    with pytest.raises(ContractError):
        validate_args(set_size, {"size": "XL"})
    with pytest.raises(ContractError):
        validate_args(set_size, {})
    with pytest.raises(ContractError):
        validate_args(add_to_cart, ["nope"])
    email = {
        "id": "set_email",
        "enabled": True,
        "input": {
            "type": "object",
            "properties": {"email": {"type": "string", "format": "email"}},
            "required": ["email"],
        },
    }
    validate_args(email, {"email": "a@b.co"})
    with pytest.raises(ContractError):
        validate_args(email, {"email": "nope"})
    # The frozen input schema cannot carry additionalProperties, so unknown
    # argument keys follow JSON Schema's default and are accepted.
    validate_args(add_to_cart, {"unexpected": 1})
    stamped = {
        "id": "set_when",
        "enabled": True,
        "input": {
            "type": "object",
            "properties": {"when": {"type": "string", "format": "date-time"}},
            "required": ["when"],
        },
    }
    validate_args(stamped, {"when": "2026-11-03T03:33:00Z"})
    with pytest.raises(ContractError):
        validate_args(stamped, {"when": "yesterday"})


def test_contract_validate_effect_accepts_act_response() -> None:
    result = _act_result()
    validate_effect(result)
    result["effect"]["match"] = None
    result["effect"]["observed"]["main_status"] = None
    validate_effect(result)
    parsed = ActResult.model_validate(result)
    validate_effect(dump_act_result(parsed))


def test_contract_validate_effect_rejects_bad_status() -> None:
    result = _act_result()
    result["status"] = "nope"
    with pytest.raises(ContractError):
        validate_effect(result)
    del result["status"]
    result["counters"] = {"illegal": 0}
    with pytest.raises(ContractError):
        validate_effect(result)


def test_contract_echo_errors_defaults_on() -> None:
    result = ActResult.model_validate(
        {
            **_act_result(),
            "status": "error",
            "error": {"code": "boom", "message": "failed", "details": {"status": 500}},
        }
    )
    kept = dump_act_result(result)
    assert kept["error"]["code"] == "boom"
    omitted = dump_act_result(result, echo_errors=False)
    assert "error" not in omitted
    assert omitted["counters"]["acts"] == 1
    validate_effect(omitted)


def test_contract_to_flat_tools_uses_id_and_input() -> None:
    tools = to_flat_tools(_paper())
    assert [tool["name"] for tool in tools] == [
        "open_product",
        "set_size",
        "add_to_cart",
        "go_catalog",
        "go_checkout",
        "set_address",
        "pay",
    ]
    assert tools[1]["parameters"]["properties"]["size"]["enum"] == ["S", "M", "L"]
    assert tools[2]["parameters"] == {"type": "object", "properties": {}}


def test_contract_model_preserves_nullable_extension_nulls() -> None:
    doc = _paper()
    doc["x"] = {
        "schema_version": "1",
        "blocked": None,
        "page": {"products": {"offset": 0, "limit": 10, "total": None, "next": None}},
    }
    dumped = dump_view_doc(ViewDoc.model_validate(doc))
    assert dumped["x"]["blocked"] is None
    assert dumped["x"]["page"]["products"]["total"] is None
    assert dumped["x"]["page"]["products"]["next"] is None
    validate_doc(dumped)


def test_contract_model_round_trip_preserves_scalars() -> None:
    dumped = dump_view_doc(ViewDoc.model_validate(_paper()))
    assert list(dumped) == ["view", "state", "entities", "affordances"]
    assert dumped["state"]["cart_count"] == 1
    assert isinstance(dumped["state"]["cart_count"], int)
    assert dumped["state"]["address"] == ""
    assert dumped["entities"]["product"]["price"] == 28
    assert dumped["entities"]["product"]["sizes_in_stock"] == ["S", "M", "L"]
    assert dumped["affordances"][2]["input"] == {"type": "object", "properties": {}}
    assert dumped["affordances"][5]["enabled"] is False
    validate_doc(dumped)


def test_contract_cli_validate_and_schema() -> None:
    valid = RUNNER.invoke(app, ["validate", str(PAPER_PATH)])
    assert valid.exit_code == 0
    assert valid.stdout.strip() == "valid"

    schema = RUNNER.invoke(app, ["schema", "view-doc"])
    assert schema.exit_code == 0
    assert sorted(json.loads(schema.stdout)["required"]) == [
        "affordances",
        "entities",
        "state",
        "view",
    ]

    effect = RUNNER.invoke(app, ["schema", "effect"])
    assert effect.exit_code == 0
    assert json.loads(effect.stdout)["$id"] == "urn:interface-compiler:schema:effect:1"

    unknown = RUNNER.invoke(app, ["schema", "nope"])
    assert unknown.exit_code == 2

    version = RUNNER.invoke(app, ["--version"])
    assert version.exit_code == 0
    assert version.stdout.strip() == "interface-compiler 0.1.0"


def test_contract_cli_validate_rejects_bad_document(tmp_path: Path) -> None:
    path = tmp_path / "doc.json"
    doc = _paper()
    doc["provenance"] = {}
    path.write_text(json.dumps(doc), encoding="utf-8")
    result = RUNNER.invoke(app, ["validate", str(path)])
    assert result.exit_code == 1
    assert "valid" not in result.stdout


def _cli_validate(doc: dict, tmp_path: Path):
    path = tmp_path / "doc.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return RUNNER.invoke(app, ["validate", str(path)])


def test_contract_view_rejects_trailing_newline(tmp_path: Path) -> None:
    doc = _paper()
    doc["view"] = "product\n"
    with pytest.raises(ContractError):
        validate_doc(doc)
    result = _cli_validate(doc, tmp_path)
    assert result.exit_code == 1
    assert result.stdout.strip() != "valid"


def test_contract_affordance_id_rejects_trailing_newline(tmp_path: Path) -> None:
    doc = _paper()
    doc["affordances"][6]["id"] = "pay\n"
    with pytest.raises(ContractError):
        validate_doc(doc)
    result = _cli_validate(doc, tmp_path)
    assert result.exit_code == 1
    assert result.stdout.strip() != "valid"


def test_contract_model_rejects_enabled_true_string() -> None:
    doc = _paper()
    doc["affordances"][0]["enabled"] = "true"
    with pytest.raises(ValidationError):
        ViewDoc.model_validate(doc)


def test_contract_model_rejects_enabled_one() -> None:
    doc = _paper()
    doc["affordances"][0]["enabled"] = 1
    with pytest.raises(ValidationError):
        ViewDoc.model_validate(doc)


def test_contract_model_rejects_doc_rev_string() -> None:
    result = _act_result()
    result["doc_rev"] = "1"
    with pytest.raises(ValidationError):
        ActResult.model_validate(result)


def test_contract_model_rejects_document_x_null() -> None:
    doc = _paper()
    doc["x"] = None
    with pytest.raises(ValidationError):
        ViewDoc.model_validate(doc)


def test_contract_model_rejects_affordance_x_null() -> None:
    doc = _paper()
    doc["affordances"][0]["x"] = None
    with pytest.raises(ValidationError):
        ViewDoc.model_validate(doc)


def test_contract_model_rejects_required_null() -> None:
    doc = _paper()
    doc["affordances"][0]["input"]["required"] = None
    with pytest.raises(ValidationError):
        ViewDoc.model_validate(doc)


def test_contract_invalid_pattern_rejected() -> None:
    doc = _paper()
    doc["affordances"][1]["input"]["properties"]["size"]["pattern"] = "("
    with pytest.raises(ContractError) as exc:
        validate_doc(doc)
    assert "affordances/1/input/properties/size/pattern" in str(exc.value)
    with pytest.raises(ValidationError):
        ViewDoc.model_validate(doc)
    with pytest.raises(ValidationError):
        ViewDoc.model_validate_json(json.dumps(doc))

    nested = _paper()
    nested["affordances"][1]["input"]["properties"]["tags"] = {
        "type": "array",
        "items": {"type": "string", "pattern": "("},
    }
    with pytest.raises(ContractError) as exc:
        validate_doc(nested)
    assert "affordances/1/input/properties/tags/items/pattern" in str(exc.value)

    valid = _paper()
    valid["affordances"][1]["input"]["properties"]["size"]["pattern"] = "^[SML]$"
    validate_doc(valid)
    validate_args(valid["affordances"][1], {"size": "L"})


def test_contract_validate_args_invalid_pattern_is_contract_error() -> None:
    affordance = {
        "id": "set_size",
        "enabled": True,
        "input": {
            "type": "object",
            "properties": {"size": {"type": "string", "pattern": "("}},
            "required": ["size"],
        },
    }
    with pytest.raises(ContractError) as exc:
        validate_args(affordance, {"size": "L"})
    assert "pattern" in str(exc.value)


_UNCOMPILABLE_PATTERNS = {
    "overflow": "a{4294967296}",
    "recursion": "(" * 5000 + "a" + ")" * 5000,
}


@pytest.mark.parametrize(
    "pattern",
    _UNCOMPILABLE_PATTERNS.values(),
    ids=_UNCOMPILABLE_PATTERNS.keys(),
)
def test_contract_pattern_compile_errors_are_contract_errors(pattern: str, tmp_path: Path) -> None:
    doc = _paper()
    doc["affordances"][1]["input"]["properties"]["size"]["pattern"] = pattern
    where = "affordances/1/input/properties/size/pattern"

    with pytest.raises(ContractError) as doc_error:
        validate_doc(doc)
    assert where in str(doc_error.value)
    if len(pattern) > 80:
        assert pattern[:81] not in str(doc_error.value)

    with pytest.raises(ValidationError) as model_error:
        ViewDoc.model_validate(doc)
    assert where in str(model_error.value)

    with pytest.raises(ValidationError) as json_error:
        ViewDoc.model_validate_json(json.dumps(doc))
    assert where in str(json_error.value)

    with pytest.raises(ContractError) as args_error:
        validate_args(doc["affordances"][1], {"size": "L"})
    assert "input/properties/size/pattern" in str(args_error.value)

    result = _cli_validate(doc, tmp_path)
    assert result.exit_code != 0
    assert isinstance(result.exception, SystemExit)
    captured = f"{result.stdout}\n{result.stderr}\n{result.output}"
    assert "Traceback" not in captured
    assert where in result.stderr


_MALFORMED_INPUTS = [
    pytest.param(
        {"type": "object", "properties": {"q": {"type": "string", "pattern": 123}}},
        {"q": "x"},
        id="pattern-int",
    ),
    pytest.param(
        {"type": "object", "properties": {"q": {"type": "string", "pattern": ["a"]}}},
        {"q": "x"},
        id="pattern-list",
    ),
    pytest.param(
        {"type": "object", "properties": {"q": {"type": "strin"}}},
        {"q": "x"},
        id="type",
    ),
    pytest.param(
        {"type": "object", "properties": {"q": {"type": "number", "minimum": "a"}}},
        {"q": 1},
        id="minimum",
    ),
    pytest.param(
        {"type": "object", "properties": ["q"]},
        {"q": "x"},
        id="properties",
    ),
    pytest.param(
        {"type": "object", "properties": {"q": {"type": "array", "items": 5}}},
        {"q": [1]},
        id="items",
    ),
    pytest.param(
        {"type": "object", "properties": {"q": {"type": "string"}}, "required": [["q"]]},
        {},
        id="required",
    ),
]


@pytest.mark.parametrize(("schema", "args"), _MALFORMED_INPUTS)
def test_contract_validate_args_rejects_malformed_input(schema: dict, args: dict) -> None:
    affordance = {"id": "go", "enabled": True, "input": schema}
    with pytest.raises(ContractError) as exc:
        validate_args(affordance, args)
    assert "input" in str(exc.value)


def _items_chain(depth: int) -> dict:
    node: dict = {"type": "string"}
    for _ in range(depth):
        node = {"type": "array", "items": node}
    return node


def test_contract_items_nesting_limit(tmp_path: Path) -> None:
    doc = _paper()
    doc["affordances"][1]["input"]["properties"]["size"] = _items_chain(300)
    where = "affordances/1/input"

    with pytest.raises(ContractError) as doc_error:
        validate_doc(doc)
    assert where in str(doc_error.value)
    assert "nesting exceeds max 32" in str(doc_error.value)

    with pytest.raises(ValidationError) as model_error:
        ViewDoc.model_validate(doc)
    assert "nesting exceeds max 32" in str(model_error.value)

    with pytest.raises(ContractError) as args_error:
        validate_args(doc["affordances"][1], {"size": []})
    assert "nesting exceeds max 32" in str(args_error.value)

    result = _cli_validate(doc, tmp_path)
    assert result.exit_code != 0
    assert isinstance(result.exception, SystemExit)
    captured = f"{result.stdout}\n{result.stderr}\n{result.output}"
    assert "Traceback" not in captured
    assert "nesting exceeds max 32" in result.stderr
    wide = _paper()
    key = "k" * 80
    node: dict = {"type": "string"}
    for _ in range(40):
        node = {"type": "object", "properties": {key: node}}
    wide["affordances"][1]["input"]["properties"]["size"] = node
    with pytest.raises(ContractError) as wide_error:
        validate_doc(wide)
    wide_message = str(wide_error.value)
    assert wide_message.startswith("nesting exceeds max 32")
    assert len(wide_message) <= 400


def test_contract_items_nesting_boundary() -> None:
    allowed = _paper()
    allowed["affordances"][1]["input"]["properties"]["size"] = _items_chain(32)
    validate_doc(allowed)
    ViewDoc.model_validate(allowed)

    rejected = _paper()
    rejected["affordances"][1]["input"]["properties"]["size"] = _items_chain(33)
    with pytest.raises(ContractError) as exc:
        validate_doc(rejected)
    assert "nesting exceeds max 32" in str(exc.value)
    with pytest.raises(ValidationError) as model_error:
        ViewDoc.model_validate(rejected)
    assert "nesting exceeds max 32" in str(model_error.value)


def _deep_object(depth: int) -> dict:
    node: dict = {"leaf": True}
    for _ in range(depth):
        node = {"n": node}
    return node


def _deep_list(depth: int) -> list:
    node: list = ["leaf"]
    for _ in range(depth):
        node = [node]
    return node


@contextmanager
def _deadline(seconds: int = 5) -> Iterator[None]:
    """Fail the test if a walk hangs instead of returning."""

    def _handle(signum: int, frame: object) -> None:
        raise TimeoutError(f"timed out after {seconds}s")

    previous = signal.signal(signal.SIGALRM, _handle)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _with_locator_extra(extra: object) -> dict:
    doc = _paper()
    doc["affordances"][0]["x"] = {"locator": {"kind": "ax", "extra": extra}}
    return doc


def test_contract_model_validate_deep_values_are_not_recursion_errors() -> None:
    items = _paper()
    items["affordances"][1]["input"]["properties"]["size"] = _items_chain(3000)
    with _deadline():
        with pytest.raises(ValidationError) as view_items:
            ViewDoc.model_validate(items)
        assert "nesting exceeds max 32" in str(view_items.value)

        act = _act_result()
        act["doc"]["affordances"][1]["input"]["properties"]["size"] = _items_chain(3000)
        with pytest.raises(ValidationError) as act_items:
            ActResult.model_validate(act)
        assert "nesting exceeds max 32" in str(act_items.value)

        located = _with_locator_extra(_deep_object(3000))
        with pytest.raises(ValidationError) as view_open:
            ViewDoc.model_validate(located)
        assert "nesting exceeds max 64" in str(view_open.value)

        detailed = _act_result()
        detailed["effect"]["predicted"]["detail"] = _deep_object(3000)
        with pytest.raises(ValidationError) as act_open:
            ActResult.model_validate(detailed)
        assert "nesting exceeds max 64" in str(act_open.value)


def test_contract_validate_args_lets_memory_error_propagate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise MemoryError("nope")

    monkeypatch.setattr("interface_compiler.contract.validate._Validator", _boom)
    affordance = {"id": "go", "enabled": True, "input": {"type": "object", "properties": {}}}
    with pytest.raises(MemoryError):
        validate_args(affordance, {})


def test_contract_duplicate_affordance_ids_rejected() -> None:
    doc = _paper()
    clone = json.loads(json.dumps(doc["affordances"][6]))
    clone["enabled"] = True
    doc["affordances"].append(clone)
    with pytest.raises(ContractError) as exc:
        validate_doc(doc)
    message = str(exc.value)
    assert "pay" in message
    assert "affordances/7/id" in message


def test_contract_duplicate_affordance_ids_in_act_doc_rejected() -> None:
    result = _act_result()
    clone = json.loads(json.dumps(result["doc"]["affordances"][6]))
    clone["enabled"] = True
    result["doc"]["affordances"].append(clone)
    with pytest.raises(ContractError) as exc:
        validate_effect(result)
    message = str(exc.value)
    assert "pay" in message
    assert "doc/affordances/7/id" in message


def test_contract_required_must_name_a_property() -> None:
    doc = _paper()
    doc["affordances"][1]["input"]["required"] = ["color"]
    with pytest.raises(ContractError) as exc:
        validate_doc(doc)
    assert "affordances/1/input/required/0" in str(exc.value)
    assert "color" in str(exc.value)

    result = _act_result()
    result["doc"]["affordances"][1]["input"]["required"] = ["color"]
    with pytest.raises(ContractError) as exc:
        validate_effect(result)
    assert "doc/affordances/1/input/required/0" in str(exc.value)


def test_contract_model_strict_act_scalars() -> None:
    with pytest.raises(ValidationError):
        ClientValidation.model_validate({"valid": "true", "messages": []})
    with pytest.raises(ValidationError):
        ClientValidation.model_validate({"valid": 1, "messages": []})
    effect = _act_result()["effect"]
    effect["match"] = "true"
    with pytest.raises(ValidationError):
        Effect.model_validate(effect)
    effect["match"] = 1
    with pytest.raises(ValidationError):
        Effect.model_validate(effect)
    counters = {
        "illegal": 0,
        "malformed": 0,
        "ignored": 0,
        "stale": 0,
        "blocked": 0,
        "acts": "1",
    }
    with pytest.raises(ValidationError):
        Counters.model_validate(counters)


def test_contract_json_value_depth_boundary() -> None:
    # Locator extra sits 5 container edges below the document. _deep_object(k)
    # adds k edges, so k=59 is depth 64 and k=60 is depth 65.
    allowed = _with_locator_extra(_deep_object(59))
    rejected = _with_locator_extra(_deep_object(60))
    act = _act_result()
    act["effect"]["predicted"]["detail"] = _deep_object(61)
    act_too_deep = _act_result()
    act_too_deep["effect"]["predicted"]["detail"] = _deep_object(62)
    with _deadline():
        _check_json_shape(_deep_object(64))
        _check_json_shape(_deep_list(64))
        with pytest.raises(ContractError) as direct:
            _check_json_shape(_deep_object(65))
        assert "nesting exceeds max 64" in str(direct.value)
        with pytest.raises(ContractError) as direct_list:
            _check_json_shape(_deep_list(65))
        assert "nesting exceeds max 64" in str(direct_list.value)

        validate_doc(allowed)
        ViewDoc.model_validate(allowed)
        validate_effect(act)
        ActResult.model_validate(act)
        strip_x(allowed)
        ablate(allowed)
        to_flat_tools(allowed)
        token_counts(allowed)

        with pytest.raises(ContractError) as doc_error:
            validate_doc(rejected)
        assert "nesting exceeds max 64" in str(doc_error.value)
        with pytest.raises(ValidationError) as model_error:
            ViewDoc.model_validate(rejected)
        assert "nesting exceeds max 64" in str(model_error.value)
        with pytest.raises(ContractError) as effect_error:
            validate_effect(act_too_deep)
        assert "nesting exceeds max 64" in str(effect_error.value)
        with pytest.raises(ValidationError) as act_error:
            ActResult.model_validate(act_too_deep)
        assert "nesting exceeds max 64" in str(act_error.value)
        with pytest.raises(ValidationError) as json_error:
            ViewDoc.model_validate_json(json.dumps(rejected))
        assert "nesting exceeds max 64" in str(json_error.value)


def test_contract_cyclic_open_object_is_rejected() -> None:
    extra: dict = {}
    extra["self"] = extra
    doc = _with_locator_extra(extra)
    loop: list = []
    loop.append(loop)
    act = _act_result()
    act["effect"]["predicted"]["detail"] = {"loop": loop}
    with _deadline():
        with pytest.raises(ContractError) as doc_error:
            validate_doc(doc)
        assert "cyclic container" in str(doc_error.value)
        with pytest.raises(ValidationError) as view_error:
            ViewDoc.model_validate(doc)
        assert "cyclic container" in str(view_error.value)
        with pytest.raises(ContractError) as effect_error:
            validate_effect(act)
        assert "cyclic container" in str(effect_error.value)
        with pytest.raises(ValidationError) as act_error:
            ActResult.model_validate(act)
        assert "cyclic container" in str(act_error.value)


def _shared_diamond(levels: int) -> dict:
    node: dict = {"leaf": True}
    for _ in range(levels):
        node = {"l": node, "r": node}
    return node


def test_contract_shared_container_reuse_is_allowed() -> None:
    shared_input = {"type": "object", "properties": {"q": {"type": "string"}}}
    doc = _paper()
    doc["affordances"][0]["input"] = shared_input
    doc["affordances"][1]["input"] = shared_input
    empty: dict = {}
    doc["entities"]["left"] = empty
    doc["entities"]["right"] = empty
    with _deadline():
        validate_doc(doc)
        ViewDoc.model_validate(doc)
        strip_x(doc)
        ablate(doc)
        to_flat_tools(doc)
        token_counts(doc)


def _limit_visits(monkeypatch: pytest.MonkeyPatch, limit: int = 1_000) -> int:
    """Use a small visit budget so a shared diamond does not walk millions of nodes."""
    monkeypatch.setattr("interface_compiler.contract.validate._MAX_JSON_VISITS", limit)
    return limit


def test_contract_shared_references_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    limit = _limit_visits(monkeypatch)
    node = _shared_diamond(40)
    doc = _with_locator_extra(node)
    act = _act_result()
    act["effect"]["predicted"]["detail"] = node
    schema_node: dict = {"type": "string"}
    for _ in range(40):
        schema_node = {"type": "object", "properties": {"l": schema_node, "r": schema_node}}
    schema_doc = _paper()
    schema_doc["affordances"][1]["input"]["properties"]["size"] = schema_node
    with _deadline():
        with pytest.raises(ContractError) as doc_error:
            validate_doc(doc)
        assert f"node visits exceed max {limit}" in str(doc_error.value)
        with pytest.raises(ValidationError) as view_error:
            ViewDoc.model_validate(doc)
        assert f"node visits exceed max {limit}" in str(view_error.value)
        with pytest.raises(ValidationError) as act_error:
            ActResult.model_validate(act)
        assert f"node visits exceed max {limit}" in str(act_error.value)
        with pytest.raises(ContractError):
            validate_doc(schema_doc)


def test_contract_validation_error_hides_shared_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limit = _limit_visits(monkeypatch)
    doc = _with_locator_extra(_shared_diamond(40))
    with _deadline():
        with pytest.raises(ValidationError) as caught:
            ViewDoc.model_validate(doc)
        started = time.perf_counter()
        rendered = str(caught.value)
        repr_rendered = repr(caught.value)
        elapsed = time.perf_counter() - started
    assert elapsed < 0.25
    assert f"node visits exceed max {limit}" in rendered
    assert "input_value" not in rendered
    assert len(rendered) < 2_000
    assert len(repr_rendered) < 2_000


def test_contract_cli_rejects_oversized_integer(tmp_path: Path) -> None:
    path = tmp_path / "huge.json"
    path.write_text('{"n": ' + ("1" * 4301) + "}", encoding="utf-8")
    with _deadline():
        result = RUNNER.invoke(app, ["validate", str(path)])
    assert result.exit_code != 0
    assert isinstance(result.exception, SystemExit)
    captured = f"{result.stdout}\n{result.stderr}\n{result.output}"
    assert "Traceback" not in captured
    assert "4301" in result.stderr


def test_contract_wide_shared_list_hits_visit_budget() -> None:
    rows = [list(range(100_000))] * 10_000
    doc = _with_locator_extra(rows)
    affordance = {
        "id": "go",
        "enabled": True,
        "input": {"type": "object", "properties": {}},
    }
    # Three walks of the visit budget are a few seconds. The alarm only
    # catches a walk that does not stop.
    with _deadline(20):
        with pytest.raises(ContractError) as doc_error:
            validate_doc(doc)
        assert "node visits exceed max 4000000" in str(doc_error.value)
        with pytest.raises(ValidationError) as model_error:
            ViewDoc.model_validate(doc)
        assert "node visits exceed max 4000000" in str(model_error.value)
        with pytest.raises(ContractError) as args_error:
            validate_args(affordance, {"rows": rows})
        assert "node visits exceed max 4000000" in str(args_error.value)


def test_contract_error_message_truncates_long_value() -> None:
    pattern_doc = _paper()
    pattern_doc["view"] = "Z" + ("a" * 3_000)
    newline_doc = _paper()
    newline_doc["view"] = ("a" * 3_000) + "\n"
    short_doc = _paper()
    short_doc["view"] = "Nope"
    huge_doc = _paper()
    huge_doc["view"] = "Z" + ("a" * 20_000)
    with pytest.raises(ContractError) as pattern_error:
        validate_doc(pattern_doc)
    with pytest.raises(ContractError) as newline_error:
        validate_doc(newline_doc)
    with pytest.raises(ContractError) as short_error:
        validate_doc(short_doc)
    with pytest.raises(ContractError) as huge_error:
        validate_doc(huge_doc)
    pattern_message = str(pattern_error.value)
    newline_message = str(newline_error.value)
    huge_message = str(huge_error.value)
    assert "does not match" in pattern_message
    assert "does not match" in newline_message
    assert len(pattern_message) < 400
    assert len(newline_message) < 400
    assert "a" * 250 not in pattern_message
    assert "a" * 250 not in newline_message
    assert "'Nope'" in str(short_error.value)
    assert "string is too long to match" in huge_message
    assert "a" * 250 not in huge_message
    assert len(huge_message) < 400


def test_contract_integer_must_fit_in_js_safe_range() -> None:
    allowed = _paper()
    allowed["state"]["cart_count"] = 2**53 - 1
    allowed["state"]["order_count"] = -(2**53 - 1)
    rejected = _paper()
    rejected["state"]["cart_count"] = 2**60
    with _deadline():
        validate_doc(allowed)
        ViewDoc.model_validate(allowed)
        for outside in (2**53, -(2**53)):
            edge = _paper()
            edge["state"]["cart_count"] = outside
            with pytest.raises(ContractError) as edge_error:
                validate_doc(edge)
            assert "integer must be within ±(2**53 - 1)" in str(edge_error.value)
        with pytest.raises(ContractError) as exc:
            validate_doc(rejected)
        assert "integer must be within ±(2**53 - 1)" in str(exc.value)
        for transform in (strip_x, ablate, to_flat_tools, token_counts):
            with pytest.raises(ContractError) as transform_error:
                transform(rejected)
            assert "integer must be within ±(2**53 - 1)" in str(transform_error.value)


def test_contract_transforms_reject_deep_open_object() -> None:
    doc = _with_locator_extra(_deep_object(3000))
    with _deadline():
        for transform in (strip_x, ablate, to_flat_tools, token_counts):
            with pytest.raises(ContractError) as exc:
                transform(doc)
            assert "nesting exceeds max 64" in str(exc.value)
        with pytest.raises(ContractError) as doc_error:
            validate_doc(doc)
        assert "nesting exceeds max 64" in str(doc_error.value)


@pytest.mark.parametrize(
    ("value", "detail"),
    [
        (set(), "set is not a JSON value"),
        (b"abc", "bytes is not a JSON value"),
        (float("nan"), "number must be finite"),
        (float("inf"), "number must be finite"),
        ((1, 2), "tuple is not a JSON value"),
    ],
)
def test_contract_open_object_rejects_non_json(value: object, detail: str) -> None:
    doc = _with_locator_extra({"v": value})
    affordance = {
        "id": "go",
        "enabled": True,
        "input": {"type": "object", "properties": {"q": {"type": "number"}}},
    }
    with _deadline():
        with pytest.raises(ContractError) as exc:
            validate_doc(doc)
        assert detail in str(exc.value)
        with pytest.raises(ValidationError) as model_error:
            ViewDoc.model_validate(doc)
        assert detail in str(model_error.value)
        with pytest.raises(ContractError) as args_error:
            validate_args(affordance, {"q": value})
        assert detail in str(args_error.value)


def test_contract_lone_surrogate_rejected_on_every_path(tmp_path: Path) -> None:
    doc = _paper()
    doc["state"]["address"] = "a\ud800b"
    text = json.dumps(_paper()).replace('"address": ""', '"address": "a\\ud800b"')
    keyed = _with_locator_extra({"\ud800": "x"})
    with _deadline():
        with pytest.raises(ContractError) as doc_error:
            validate_doc(doc)
        assert "lone surrogate" in str(doc_error.value)
        with pytest.raises(ValidationError) as model_error:
            ViewDoc.model_validate(doc)
        assert "lone surrogate" in str(model_error.value)
        with pytest.raises(ValidationError):
            ViewDoc.model_validate_json(text)
        with pytest.raises(ContractError) as key_error:
            validate_doc(keyed)
        assert "lone surrogate" in str(key_error.value)
        result = _cli_validate(doc, tmp_path)
        assert result.exit_code != 0
        assert isinstance(result.exception, SystemExit)
        captured = f"{result.stdout}\n{result.stderr}\n{result.output}"
        assert "Traceback" not in captured
        assert "lone surrogate" in result.stderr


_BACKTRACKING_PATTERNS = (
    r"^(a+)+$",
    r"^(a|a)*$",
    r"^(a|aa)+$",
    r"^(a*a)*$",
    r"^(a+){1,19}$",
    r"^(.*a){12}$",
    "a*" * 10 + "b$",
    "^" + ".*" * 10 + "=$",
)


def _pattern_affordance(pattern: str) -> dict:
    return {
        "id": "go",
        "enabled": True,
        "input": {
            "type": "object",
            "properties": {"q": {"type": "string", "pattern": pattern}},
            "required": ["q"],
        },
    }


@pytest.mark.parametrize("pattern", _BACKTRACKING_PATTERNS)
def test_contract_backtracking_pattern_matches_in_bounded_time(pattern: str) -> None:
    """RE2 accepts these shapes and searches a long failing input quickly.

    A static screen cannot cover every exponential form, and several of these
    used to hang ``validate_args``. The document keeps the pattern. The match
    fails because the input does not match, and it finishes inside the deadline.
    """
    affordance = _pattern_affordance(pattern)
    doc = _paper()
    doc["affordances"][1]["input"]["properties"]["size"]["pattern"] = pattern
    validate_doc(doc)
    ViewDoc.model_validate(doc)
    started = time.perf_counter()
    with _deadline(1), pytest.raises(ContractError) as exc:
        validate_args(affordance, {"q": ("a" * 4000) + "!"})
    elapsed = time.perf_counter() - started
    message = str(exc.value)
    assert "does not match" in message
    assert "rejected" not in message
    assert elapsed < 0.25


_UNMATCHABLE_PATTERNS = (
    r"^((a)\2?)+$",
    r"^(a)?(?(1)(a+)+|b)$",
    r"(?=a)",
    r"(?<=a)",
)


@pytest.mark.parametrize("pattern", _UNMATCHABLE_PATTERNS)
def test_contract_re2_rejects_patterns_it_cannot_compile(pattern: str) -> None:
    """Backreferences, conditionals, and lookaround are rejected before matching."""
    affordance = _pattern_affordance(pattern)
    doc = _paper()
    doc["affordances"][1]["input"]["properties"]["size"]["pattern"] = pattern
    where = "affordances/1/input/properties/size/pattern"
    started = time.perf_counter()
    with _deadline(1):
        with pytest.raises(ContractError) as doc_error:
            validate_doc(doc)
        with pytest.raises(ValidationError) as model_error:
            ViewDoc.model_validate(doc)
        with pytest.raises(ContractError) as args_error:
            validate_args(affordance, {"q": ("a" * 4000) + "!"})
    elapsed = time.perf_counter() - started
    for message in (str(doc_error.value), str(model_error.value), str(args_error.value)):
        assert "rejected" in message
        assert "does not match" not in message
    assert where in str(doc_error.value)
    assert elapsed < 0.25


@pytest.mark.parametrize(
    ("pattern", "value"),
    [
        (r"^[SML]$", "L"),
        (r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", "ada@example.com"),
        (
            (
                r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}"
                r"-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
            ),
            "550e8400-e29b-41d4-a716-446655440000",
        ),
        (r"^\d{4}-\d{2}-\d{2}$", "2026-11-03"),
        (r"^\+?[0-9 .()-]{7,20}$", "+1 415 555 0100"),
        (r"^(?:\d{1,3}\.){3}\d{1,3}$", "1.2.3.4"),
        (r"^(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$", "2001:0db8:0000:0000:0000:0000:0000:0001"),
        (r"^[a-z0-9]+(?:-[a-z0-9]+)*$", "my-page"),
        (r"^#[0-9A-Fa-f]{6}$", "#A1B2C3"),
        (r"^https?://[A-Za-z0-9.-]+(?::\d{1,5})?(?:/[^\s]*)?$", "https://example.com/a"),
        (r"^(?:[01]\d|2[0-3]):[0-5]\d$", "23:59"),
        (r"^\d{5}(-\d{4})?$", "12345-6789"),
        (r"^[A-Za-z][A-Za-z0-9_]{0,31}$", "Name_1"),
        (r"^(?:0|[1-9]\d*)(?:\.\d+)?$", "10.5"),
        (r"^[A-Z]{2,3}$", "USD"),
        (r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)$", "Mon"),
        (r"^([A-Za-z]+\s?)+$", "Hello World"),
        (r"(?:[ _-][A-Za-z0-9]+)*", " foo"),
        (r"(https?://)?example", "https://example"),
        (r"(a+b)+", "aaabaaab"),
    ],
)
def test_contract_bounded_patterns_still_match(pattern: str, value: str) -> None:
    affordance = {
        "id": "go",
        "enabled": True,
        "input": {
            "type": "object",
            "properties": {"q": {"type": "string", "pattern": pattern}},
            "required": ["q"],
        },
    }
    validate_args(affordance, {"q": value})


def test_contract_error_message_caps_long_keys() -> None:
    key = "k" * 100_000
    doc = _paper()
    doc[key] = 1
    with pytest.raises(ContractError) as unexpected:
        validate_doc(doc)
    unexpected_message = str(unexpected.value)
    assert len(unexpected_message) <= 500
    assert all(len(item) <= 500 for item in unexpected.value.errors)
    assert "was unexpected" in unexpected_message
    assert key not in unexpected_message

    affordance = {
        "id": "go",
        "enabled": True,
        "input": {
            "type": "object",
            "properties": {key: {"type": "string"}},
            "required": [key],
        },
    }
    with pytest.raises(ContractError) as typed:
        validate_args(affordance, {key: 1})
    typed_message = str(typed.value)
    assert len(typed_message) <= 500
    assert all(len(item) <= 500 for item in typed.value.errors)
    assert "string" in typed_message
    assert key not in typed_message

    noisy = {"size": "XL", key: 1}
    with pytest.raises(ContractError) as args_error:
        validate_args(_paper()["affordances"][1], noisy)
    args_message = str(args_error.value)
    assert len(args_message) <= 500
    assert key not in args_message


def test_contract_shape_error_caps_a_long_key(tmp_path: Path) -> None:
    key = "k" * 100_000
    doc = _paper()
    doc[key] = float("nan")
    with pytest.raises(ContractError) as doc_error:
        validate_doc(doc)
    doc_message = str(doc_error.value)
    assert "number must be finite" in doc_message
    assert len(doc_message) <= 500
    assert key not in doc_message

    affordance = {
        "id": "go",
        "enabled": True,
        "input": {"type": "object", "properties": {"q": {"type": "number"}}},
    }
    with pytest.raises(ContractError) as args_error:
        validate_args(affordance, {key: float("nan")})
    args_message = str(args_error.value)
    assert "number must be finite" in args_message
    assert len(args_message) <= 500
    assert key not in args_message

    surrogate = _paper()
    surrogate[key] = "a\ud800b"
    result = _cli_validate(surrogate, tmp_path)
    assert result.exit_code == 1
    assert key not in result.stderr
    assert len(result.stderr) <= 500
    assert "lone surrogate" in result.stderr


def test_contract_pattern_path_caps_a_long_property_name() -> None:
    key = "k" * 100_000
    doc = _paper()
    doc["affordances"][1]["input"]["properties"][key] = {"type": "string", "pattern": "("}
    with pytest.raises(ContractError) as doc_error:
        validate_doc(doc)
    message = str(doc_error.value)
    assert "pattern" in message
    assert len(message) <= 500
    assert key not in message
    affordance = doc["affordances"][1]
    with pytest.raises(ContractError) as args_error:
        validate_args(affordance, {key: "v"})
    args_message = str(args_error.value)
    assert len(args_message) <= 500
    assert key not in args_message


def test_contract_cli_caps_how_many_errors_it_prints(tmp_path: Path) -> None:
    doc = _paper()
    blob = "e" * 300
    doc["affordances"] = [
        {
            "id": f"a{index}",
            "enabled": blob,
            "input": {"type": "object", "properties": {}},
        }
        for index in range(50)
    ]
    result = _cli_validate(doc, tmp_path)
    assert result.exit_code == 1
    assert "omitted" in result.stderr
    assert len(result.stderr) <= 4500
    assert blob not in result.stderr
    assert len(result.stderr.splitlines()) <= 21


def test_contract_overlong_pattern_is_rejected_before_compile() -> None:
    pattern = "a" * (5 * 1024 * 1024)
    doc = _paper()
    doc["affordances"][1]["input"]["properties"]["size"]["pattern"] = pattern
    affordance = doc["affordances"][1]
    started = time.perf_counter()
    with _deadline(2):
        with pytest.raises(ContractError) as doc_error:
            validate_doc(doc)
        with pytest.raises(ValidationError) as model_error:
            ViewDoc.model_validate(doc)
        with pytest.raises(ContractError) as args_error:
            validate_args(affordance, {"size": "a"})
    elapsed = time.perf_counter() - started
    assert elapsed < 1.0
    for message in (str(doc_error.value), str(model_error.value), str(args_error.value)):
        assert "too long" in message
        assert len(message) <= 500
        assert "a" * 81 not in message


def test_contract_overlong_subject_is_not_matched() -> None:
    subject = "a" * 5000
    affordance = _pattern_affordance(r"^a+$")
    started = time.perf_counter()
    with _deadline(1), pytest.raises(ContractError) as exc:
        validate_args(affordance, {"q": subject})
    elapsed = time.perf_counter() - started
    message = str(exc.value)
    assert "string is too long to match" in message
    assert "does not match" not in message
    assert subject not in message
    assert elapsed < 0.25
    validate_args(affordance, {"q": "a" * 4096})
