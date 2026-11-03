"""Unit tests for the frozen v1 compiled view document contract."""

import json
import re
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


def test_contract_fixture_matches_paper_requirements() -> None:
    expected = _fenced_json(
        ROOT / "docs" / "PAPER-REQUIREMENTS.md",
        "## 2. The paper's printed example",
    )
    assert _paper() == expected


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
    assert "nesting exceeds 32 (max 32)" in str(doc_error.value)

    with pytest.raises(ValidationError) as model_error:
        ViewDoc.model_validate(doc)
    assert "nesting exceeds 32 (max 32)" in str(model_error.value)

    with pytest.raises(ContractError) as args_error:
        validate_args(doc["affordances"][1], {"size": []})
    assert "nesting exceeds 32 (max 32)" in str(args_error.value)

    result = _cli_validate(doc, tmp_path)
    assert result.exit_code != 0
    assert isinstance(result.exception, SystemExit)
    captured = f"{result.stdout}\n{result.stderr}\n{result.output}"
    assert "Traceback" not in captured
    assert "nesting exceeds 32 (max 32)" in result.stderr


def test_contract_items_nesting_boundary() -> None:
    allowed = _paper()
    allowed["affordances"][1]["input"]["properties"]["size"] = _items_chain(32)
    validate_doc(allowed)
    ViewDoc.model_validate(allowed)

    rejected = _paper()
    rejected["affordances"][1]["input"]["properties"]["size"] = _items_chain(33)
    with pytest.raises(ContractError) as exc:
        validate_doc(rejected)
    assert "nesting exceeds 32 (max 32)" in str(exc.value)
    with pytest.raises(ValidationError) as model_error:
        ViewDoc.model_validate(rejected)
    assert "nesting exceeds 32 (max 32)" in str(model_error.value)


def _deep_object(depth: int) -> dict:
    node: dict = {"leaf": True}
    for _ in range(depth):
        node = {"n": node}
    return node


def _assert_deep_object(value: object, depth: int) -> None:
    node = value
    for _ in range(depth):
        assert isinstance(node, dict)
        node = node["n"]
    assert node == {"leaf": True}


def test_contract_model_validate_deep_values_are_not_recursion_errors() -> None:
    items = _paper()
    items["affordances"][1]["input"]["properties"]["size"] = _items_chain(3000)
    with pytest.raises(ValidationError) as view_items:
        ViewDoc.model_validate(items)
    assert "nesting exceeds 32 (max 32)" in str(view_items.value)

    act = _act_result()
    act["doc"]["affordances"][1]["input"]["properties"]["size"] = _items_chain(3000)
    with pytest.raises(ValidationError) as act_items:
        ActResult.model_validate(act)
    assert "nesting exceeds 32 (max 32)" in str(act_items.value)

    located = _paper()
    located["affordances"][0]["x"] = {"locator": {"kind": "ax", "extra": _deep_object(3000)}}
    parsed = ViewDoc.model_validate(located)
    affordance_x = parsed.affordances[0].x
    assert affordance_x is not None and affordance_x.locator is not None
    extras = affordance_x.locator.model_extra or {}
    _assert_deep_object(extras["extra"], 3000)

    detailed = _act_result()
    detailed["effect"]["predicted"]["detail"] = _deep_object(3000)
    parsed_act = ActResult.model_validate(detailed)
    assert parsed_act.effect is not None
    _assert_deep_object(parsed_act.effect.predicted.detail, 3000)


def test_contract_validate_args_lets_memory_error_propagate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise MemoryError("nope")

    monkeypatch.setattr("interface_compiler.contract.validate.Draft202012Validator", _boom)
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
