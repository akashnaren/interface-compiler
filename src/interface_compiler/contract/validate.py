"""Validate compiled view documents, act responses, and affordance arguments."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
from pydantic import BaseModel
from referencing import Registry, Resource

from interface_compiler.checker.verified import verified_errors
from interface_compiler.contract.patterns import backtracking_risk

_SCHEMA_FILES = {
    "view-doc": "view-doc.v1.json",
    "effect": "effect.v1.json",
}
# The frozen pattern uses `$`. Python's `$` succeeds before a final newline, so
# jsonschema accepts "pay\n". `\Z` is the end of the string.
_EXACT_ID = re.compile(r"\A[a-z][a-z0-9_]*\Z")
# re.compile raises re.error for a bad pattern, and also OverflowError
# (a{4294967296}) and RecursionError (thousands of nested groups).
_PATTERN_COMPILE_ERRORS = (re.error, OverflowError, RecursionError)
_PATTERN_ECHO_LIMIT = 80
# Contract errors quote the failing value. A long quote is cut to about this.
_VALUE_ECHO_LIMIT = 200
# Key names and path segments are untrusted. One long key must not become the
# whole ContractError. The final message is capped again after that.
_SEGMENT_LIMIT = 80
_MESSAGE_LIMIT = 400
# jsonschema follows items/$ref recursively and overflows the stack on a
# chain a few hundred levels deep. Stop before that walk.
_MAX_SCHEMA_DEPTH = 32
# Every JSON value, not only items and properties. Depth 64 is allowed.
_MAX_JSON_DEPTH = 64
# Re-walking a shared container is allowed. Every value counts, scalars
# included. A realistic page is about 99k values; this stops a shared list
# of lists before it walks hundreds of millions of scalars.
_MAX_JSON_VISITS = 4_000_000
# JavaScript's Number cannot represent integers outside this range.
_MAX_SAFE_INT = 2**53 - 1
_RFC3339 = re.compile(
    r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})"
    r"T(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
    r"(?:\.\d+)?"
    r"(?:Z|[+-](?P<off_hour>\d{2}):(?P<off_minute>\d{2}))$"
)


class ContractError(Exception):
    """A document, act response, or argument failed the frozen contract."""

    def __init__(self, message: str, *, errors: list[str] | None = None) -> None:
        self.errors = errors if errors is not None else [message]
        super().__init__(message)


class UnknownSchemaError(ContractError):
    """The caller asked for a schema other than view-doc or effect."""


def schema_dir() -> Path:
    return Path(__file__).resolve().parent / "schemas"


def schema_text(name: str) -> str:
    """Return the raw JSON Schema text for ``view-doc`` or ``effect``."""
    filename = _SCHEMA_FILES.get(name)
    if filename is None:
        raise UnknownSchemaError(f"unknown schema {name!r}; expected view-doc or effect")
    return (schema_dir() / filename).read_text(encoding="utf-8")


def load_schema(name: str) -> dict[str, Any]:
    """Return a frozen JSON Schema object."""
    return json.loads(schema_text(name))


def validate_doc(doc: Mapping[str, Any]) -> None:
    """Raise ``ContractError`` when ``doc`` is not a compiled view document."""
    _validate("view-doc", doc)


def validate_effect(result: Mapping[str, Any]) -> None:
    """Raise ``ContractError`` when ``result`` is not an act response."""
    _validate("effect", result)


def validate_args(affordance: object, args: object) -> None:
    """Raise ``ContractError`` when ``args`` fail the affordance input schema."""
    if not isinstance(args, dict):
        message = "<root>: args must be a JSON object"
        raise ContractError(message, errors=[message])
    _check_json_shape(args)
    schema = _input_schema(affordance)
    depth_errors = _input_nesting_errors(schema, "input")
    if depth_errors:
        raise ContractError(depth_errors[0], errors=depth_errors)
    if isinstance(affordance, dict):
        _check_json_shape(affordance)
    _ensure_input_schema(schema, "input")
    try:
        validator = Draft202012Validator(schema, format_checker=_format_checker())
        _raise_if_invalid(validator, args)
    except ContractError:
        raise
    except SchemaError as exc:
        message = f"input: {exc.message}"
        raise ContractError(message, errors=[message]) from exc
    except _PATTERN_COMPILE_ERRORS as exc:
        errors = _input_object_errors(schema, "input")
        if not errors:
            message = f"input: invalid regular expression ({exc})"
            errors = [message]
        raise ContractError(errors[0], errors=errors) from exc
    except MemoryError:
        raise
    except Exception as exc:
        message = f"input: {type(exc).__name__}: {exc}"
        raise ContractError(message, errors=[message]) from exc


def _input_schema(affordance: object) -> dict[str, Any]:
    if isinstance(affordance, BaseModel):
        raw = affordance.model_dump(mode="json", exclude_none=True)
    elif isinstance(affordance, Mapping):
        raw = affordance
    else:
        message = "<root>: affordance must be an object"
        raise ContractError(message, errors=[message])
    schema = raw.get("input") if isinstance(raw, Mapping) else None
    if not isinstance(schema, dict):
        message = "input: affordance has no input schema"
        raise ContractError(message, errors=[message])
    return schema


def _validate(name: str, instance: object) -> None:
    _guard_json_document(instance)
    _raise_if_invalid(_validator(name), instance)
    errors = [
        *_exact_id_errors(instance),
        *_duplicate_id_errors(instance),
        *_affordance_constraint_errors(instance),
        # Mutating actions on a real site cannot be probed_ok. Enforced here so
        # a later look cannot validate a document that skipped the checker.
        *verified_errors(instance),
    ]
    if errors:
        raise ContractError(errors[0], errors=errors)


def _raise_if_invalid(validator: Draft202012Validator, instance: object) -> None:
    errors = sorted(
        validator.iter_errors(instance),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    if not errors:
        return
    messages = [_error_message(error) for error in errors]
    raise ContractError(messages[0], errors=messages)


def _error_message(error: ValidationError) -> str:
    parts = [_cap_text(str(part), _SEGMENT_LIMIT) for part in error.absolute_path]
    where = "/".join(parts) if parts else "<root>"
    detail = error.message
    if len(detail) > _VALUE_ECHO_LIMIT:
        rendered = repr(error.instance)
        if len(rendered) > _VALUE_ECHO_LIMIT and rendered in detail:
            detail = detail.replace(rendered, _truncate_repr(rendered), 1)
    if len(detail) > _SEGMENT_LIMIT:
        detail = _cap_quoted(detail, _SEGMENT_LIMIT)
    return _cap_text(f"{where}: {detail}", _MESSAGE_LIMIT)


@lru_cache(maxsize=1)
def _registry() -> Registry[Any]:
    pairs = []
    for name in _SCHEMA_FILES:
        schema = load_schema(name)
        pairs.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(pairs)


def _exact_id_errors(instance: object, *, prefix: str = "") -> list[str]:
    """Reject view and affordance ids that only matched because of `$`."""
    if not isinstance(instance, Mapping):
        return []
    errors: list[str] = []
    view = instance.get("view")
    if isinstance(view, str) and _EXACT_ID.fullmatch(view) is None:
        errors.append(f"{prefix}view: {_echo_value(view)} does not match '^[a-z][a-z0-9_]*$'")
    affordances = instance.get("affordances")
    if isinstance(affordances, list):
        for index, item in enumerate(affordances):
            if not isinstance(item, Mapping):
                continue
            ident = item.get("id")
            if isinstance(ident, str) and _EXACT_ID.fullmatch(ident) is None:
                where = f"{prefix}affordances/{index}/id"
                errors.append(f"{where}: {_echo_value(ident)} does not match '^[a-z][a-z0-9_]*$'")
    doc = instance.get("doc")
    if isinstance(doc, Mapping):
        errors.extend(_exact_id_errors(doc, prefix=f"{prefix}doc/"))
    return errors


def _duplicate_id_errors(instance: object, *, prefix: str = "") -> list[str]:
    """Reject a second affordance that reuses an id already present."""
    if not isinstance(instance, Mapping):
        return []
    errors: list[str] = []
    affordances = instance.get("affordances")
    if isinstance(affordances, list):
        seen: dict[str, int] = {}
        for index, item in enumerate(affordances):
            if not isinstance(item, Mapping):
                continue
            ident = item.get("id")
            if not isinstance(ident, str):
                continue
            previous = seen.get(ident)
            if previous is None:
                seen[ident] = index
                continue
            where = f"{prefix}affordances/{index}/id"
            also = f"{prefix}affordances/{previous}/id"
            errors.append(f"{where}: duplicate id {_echo_value(ident)} (also at {also})")
    doc = instance.get("doc")
    if isinstance(doc, Mapping):
        errors.extend(_duplicate_id_errors(doc, prefix=f"{prefix}doc/"))
    return errors


def _affordance_constraint_errors(instance: object, *, prefix: str = "") -> list[str]:
    """Reject input schemas whose patterns or required names cannot be applied."""
    if not isinstance(instance, Mapping):
        return []
    errors: list[str] = []
    affordances = instance.get("affordances")
    if isinstance(affordances, list):
        for index, item in enumerate(affordances):
            if not isinstance(item, Mapping):
                continue
            where = f"{prefix}affordances/{index}/input"
            errors.extend(_input_object_errors(item.get("input"), where))
    doc = instance.get("doc")
    if isinstance(doc, Mapping):
        errors.extend(_affordance_constraint_errors(doc, prefix=f"{prefix}doc/"))
    return errors


def _input_object_errors(schema: object, where: str) -> list[str]:
    if not isinstance(schema, Mapping):
        return []
    errors: list[str] = []
    properties = schema.get("properties")
    known = properties if isinstance(properties, Mapping) else {}
    required = schema.get("required")
    if isinstance(required, list):
        for index, name in enumerate(required):
            if isinstance(name, str) and name not in known:
                errors.append(f"{where}/required/{index}: {_echo_value(name)} is not a property")
    if isinstance(properties, Mapping):
        for key, prop in properties.items():
            errors.extend(_prop_errors(prop, f"{where}/properties/{key}"))
    return errors


def _compile_pattern(pattern: str) -> ContractError | None:
    """Return a contract error when ``pattern`` cannot be compiled or matched safely."""
    try:
        re.compile(pattern)
    except _PATTERN_COMPILE_ERRORS as exc:
        message = f"{_echo_pattern(pattern)} is not a valid regular expression ({exc})"
        return ContractError(message, errors=[message])
    reason = backtracking_risk(pattern)
    if reason is not None:
        message = f"{_echo_pattern(pattern)} is rejected ({reason})"
        return ContractError(message, errors=[message])
    return None


def _cap_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return f"{text[: limit - 3]}..."


def _cap_quoted(text: str, limit: int) -> str:
    """Cut a quoted key or value so the surrounding sentence stays intact."""
    parts: list[str] = []
    index = 0
    size = len(text)
    while index < size:
        quote = text[index]
        if quote not in {"'", '"'}:
            parts.append(quote)
            index += 1
            continue
        cursor = index + 1
        while cursor < size:
            if text[cursor] == "\\":
                cursor += 2
                continue
            if text[cursor] == quote:
                cursor += 1
                break
            cursor += 1
        parts.append(_cap_text(text[index:cursor], limit))
        index = min(cursor, size)
    return "".join(parts)


def _echo_pattern(pattern: str) -> str:
    if len(pattern) <= _PATTERN_ECHO_LIMIT:
        return repr(pattern)
    return repr(f"{pattern[:_PATTERN_ECHO_LIMIT]}...")


def _echo_value(value: object) -> str:
    """Repr of a failing value, cut so one large value cannot dominate the message."""
    return _truncate_repr(repr(value))


def _truncate_repr(rendered: str) -> str:
    if len(rendered) <= _VALUE_ECHO_LIMIT:
        return rendered
    quote = rendered[0] if rendered else ""
    if quote in {"'", '"'} and rendered[-1] == quote:
        # Keep the closer. An open quote would swallow the rest of the sentence
        # when a later pass caps quoted keys.
        keep = max(_VALUE_ECHO_LIMIT - 4, 1)
        return f"{quote}{rendered[1:keep]}...{quote}"
    return f"{rendered[:_VALUE_ECHO_LIMIT]}..."


def nesting_too_deep(where: str) -> str:
    """Contract message for an items or properties chain past the nesting limit."""
    return f"{where}: nesting exceeds max {_MAX_SCHEMA_DEPTH}"


def _guard_json_document(instance: object) -> None:
    """Schema-nesting guard, then the JSON shape gate.

    Items and properties chains report the schema limit of 32. The shape gate
    then rejects every other value that is not a JSON tree of depth at most 64.
    """
    depth_errors = _document_nesting_errors(instance)
    if depth_errors:
        raise ContractError(depth_errors[0], errors=depth_errors)
    _check_json_shape(instance)


class _JsonLeave(NamedTuple):
    identity: int


_JsonFrame = tuple[object, int, tuple[str, ...]]
_ShapeStack = list[_JsonFrame | _JsonLeave]


def _check_json_shape(value: object) -> None:
    """Reject a value that JSON cannot express.

    Walks with an explicit stack. A container id on the current ancestor path
    is a cycle. The same container reached by another path is ordinary Python
    reuse and is allowed. Every value counts toward ``_MAX_JSON_VISITS``,
    scalars included, so a shared list of lists still fails fast. Depth counts
    container edges from ``value``: 64 is allowed and 65 is not. Scalars are
    ``str``, ``bool``, ``int`` inside ±(2**53 - 1), finite ``float``, and
    ``None``. Object keys are strings. Lone surrogates are rejected so this
    matches ``model_validate_json``.
    """
    stack: _ShapeStack = [(value, 0, ())]
    ancestors: set[int] = set()
    visits = [0]
    while stack:
        frame = stack.pop()
        if isinstance(frame, _JsonLeave):
            ancestors.remove(frame.identity)
            continue
        current, depth, path = frame
        if isinstance(current, dict):
            _push_json_object(current, depth, path, ancestors, visits, stack)
            continue
        if isinstance(current, list):
            _push_json_list(current, depth, path, ancestors, visits, stack)
            continue
        if _charge_visit(visits):
            _too_many_visits(path)
        if _is_json_scalar(current):
            _reject_bad_scalar(current, path)
            continue
        _reject_json_type(current, path)


def _json_copy(value: object) -> Any:
    """Deep-copy a value that already passed ``_check_json_shape``.

    ``json.dumps`` recurses. Nesting is capped at 64, and a shared structure
    that would explode is rejected by the visit budget first. Sharing that
    fits in the budget is duplicated, which is how JSON encodes it.
    """
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return json.loads(text)


def _is_json_scalar(value: object) -> bool:
    if value is None or isinstance(value, str | bool):
        return True
    if isinstance(value, int):
        return True
    return isinstance(value, float)


def _reject_bad_scalar(value: object, path: tuple[str, ...]) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        _reject_lone_surrogate(value, path)
        return
    if isinstance(value, int):
        if value > _MAX_SAFE_INT or value < -_MAX_SAFE_INT:
            _json_shape_error(path, "integer must be within ±(2**53 - 1)")
        return
    if isinstance(value, float) and not math.isfinite(value):
        _json_shape_error(path, "number must be finite")


def _reject_lone_surrogate(text: str, path: tuple[str, ...]) -> None:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        _json_shape_error(path, "lone surrogate in string")


def _push_json_object(
    current: dict[object, object],
    depth: int,
    path: tuple[str, ...],
    ancestors: set[int],
    visits: list[int],
    stack: _ShapeStack,
) -> None:
    identity = _enter_json_container(current, depth, path, ancestors, visits)
    pending: list[_JsonFrame] = []
    for key, item in current.items():
        if not isinstance(key, str):
            _json_shape_error(path, f"object key {_echo_value(key)} is not a string")
        _reject_lone_surrogate(key, path)
        _enqueue_or_count(item, depth + 1, path, key, visits, pending)
    stack.append(_JsonLeave(identity))
    stack.extend(reversed(pending))


def _push_json_list(
    current: list[object],
    depth: int,
    path: tuple[str, ...],
    ancestors: set[int],
    visits: list[int],
    stack: _ShapeStack,
) -> None:
    identity = _enter_json_container(current, depth, path, ancestors, visits)
    pending: list[_JsonFrame] = []
    for index, item in enumerate(current):
        # str(index) is built only when the child needs a path. The wide-list
        # case is millions of small ints, and the index text is unused until
        # a visit actually fails.
        if _is_budget_scalar(item):
            if _charge_visit(visits):
                _too_many_visits((*path, str(index)))
            continue
        _enqueue_or_count(item, depth + 1, path, str(index), visits, pending)
    stack.append(_JsonLeave(identity))
    stack.extend(reversed(pending))


def _enqueue_or_count(
    item: object,
    depth: int,
    path: tuple[str, ...],
    key: str,
    visits: list[int],
    pending: list[_JsonFrame],
) -> None:
    if isinstance(item, dict | list):
        pending.append((item, depth, (*path, key)))
        return
    if _is_budget_scalar(item):
        if _charge_visit(visits):
            _too_many_visits((*path, key))
        return
    child = (*path, key)
    if _charge_visit(visits):
        _too_many_visits(child)
    if _is_json_scalar(item):
        _reject_bad_scalar(item, child)
        return
    _reject_json_type(item, child)


def _enter_json_container(
    current: object,
    depth: int,
    path: tuple[str, ...],
    ancestors: set[int],
    visits: list[int],
) -> int:
    if depth > _MAX_JSON_DEPTH:
        _json_shape_error(path, f"nesting exceeds max {_MAX_JSON_DEPTH}")
    identity = id(current)
    if identity in ancestors:
        _json_shape_error(path, "cyclic container")
    if _charge_visit(visits):
        _too_many_visits(path)
    ancestors.add(identity)
    return identity


def _is_budget_scalar(value: object) -> bool:
    """True for None, bool, and an int inside the JavaScript safe range.

    ``bool`` is a subclass of ``int``. ``True`` and ``False`` fall inside the
    safe range, so they need no further scalar check.
    """
    if value is None:
        return True
    return isinstance(value, int) and -_MAX_SAFE_INT <= value <= _MAX_SAFE_INT


def _charge_visit(visits: list[int]) -> bool:
    visits[0] += 1
    return visits[0] > _MAX_JSON_VISITS


def _too_many_visits(path: tuple[str, ...]) -> None:
    _json_shape_error(path, f"node visits exceed max {_MAX_JSON_VISITS}")


def _reject_json_type(value: object, path: tuple[str, ...]) -> None:
    _json_shape_error(path, f"{type(value).__name__} is not a JSON value")


def _json_shape_error(path: tuple[str, ...], detail: str) -> None:
    where = "/".join(path) if path else "<root>"
    message = f"{where}: {detail}"
    raise ContractError(message, errors=[message])


def _schema_nesting_errors(
    node: object,
    where: str,
    *,
    depth: int = 0,
    seen: set[int] | None = None,
) -> list[str]:
    """Reject a schema node more than ``_MAX_SCHEMA_DEPTH`` edges below its property.

    ``depth`` is the number of ``items`` or nested ``properties`` edges followed
    to reach ``node``. Depth 32 is allowed. Depth 33 is not. The input object's
    own ``properties`` map is not an edge; callers pass each property at depth 0.
    A container already seen on this walk is skipped so shared schema nodes stay
    linear. Cycles and visit blowups are left to ``_check_json_shape``.
    """
    if seen is None:
        seen = set()
    if depth > _MAX_SCHEMA_DEPTH:
        return [nesting_too_deep(where)]
    if not isinstance(node, Mapping):
        return []
    identity = id(node)
    if identity in seen:
        return []
    seen.add(identity)
    errors: list[str] = []
    properties = node.get("properties")
    if isinstance(properties, Mapping):
        for key, child in properties.items():
            child_where = f"{where}/properties/{key}"
            errors.extend(_schema_nesting_errors(child, child_where, depth=depth + 1, seen=seen))
    items = node.get("items")
    if isinstance(items, Mapping):
        errors.extend(_schema_nesting_errors(items, f"{where}/items", depth=depth + 1, seen=seen))
    return errors


def _input_nesting_errors(schema: object, where: str) -> list[str]:
    if not isinstance(schema, Mapping):
        return []
    errors: list[str] = []
    seen: set[int] = set()
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        for key, child in properties.items():
            child_where = f"{where}/properties/{key}"
            errors.extend(_schema_nesting_errors(child, child_where, depth=0, seen=seen))
    return errors


def _document_nesting_errors(instance: object, *, prefix: str = "") -> list[str]:
    errors: list[str] = []
    stack: list[tuple[object, str]] = [(instance, prefix)]
    seen: set[int] = set()
    while stack:
        current, current_prefix = stack.pop()
        if not isinstance(current, Mapping):
            continue
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        affordances = current.get("affordances")
        if isinstance(affordances, list):
            for index, item in enumerate(affordances):
                if not isinstance(item, Mapping):
                    continue
                where = f"{current_prefix}affordances/{index}/input"
                errors.extend(_input_nesting_errors(item.get("input"), where))
        doc = current.get("doc")
        if isinstance(doc, Mapping):
            stack.append((doc, f"{current_prefix}doc/"))
    return errors


def _ensure_input_schema(schema: object, where: str) -> None:
    """Reject an affordance input that the frozen input schema would reject."""
    depth_errors = _input_nesting_errors(schema, where)
    if depth_errors:
        raise ContractError(depth_errors[0], errors=depth_errors)
    if not isinstance(schema, Mapping):
        message = f"{where}: input schema must be an object"
        raise ContractError(message, errors=[message])
    try:
        _raise_if_invalid(_input_schema_validator(), schema)
    except ContractError as exc:
        raise _prefix_contract_error(exc, where) from exc
    errors = _input_object_errors(schema, where)
    if errors:
        raise ContractError(errors[0], errors=errors)


def _prefix_contract_error(exc: ContractError, where: str) -> ContractError:
    errors: list[str] = []
    for message in exc.errors:
        location, separator, detail = message.partition(": ")
        if separator and location == "<root>":
            errors.append(f"{where}: {detail}")
        elif separator:
            errors.append(f"{where}/{location}: {detail}")
        else:
            errors.append(f"{where}: {message}")
    return ContractError(errors[0], errors=errors)


@lru_cache(maxsize=1)
def _input_schema_validator() -> Draft202012Validator:
    full = load_schema("view-doc")
    schema = {"$defs": full["$defs"], "$ref": "#/$defs/input"}
    return Draft202012Validator(schema, format_checker=_format_checker())


def _prop_errors(
    prop: object,
    where: str,
    depth: int = 0,
    seen: set[int] | None = None,
) -> list[str]:
    if seen is None:
        seen = set()
    if depth > _MAX_SCHEMA_DEPTH:
        return [nesting_too_deep(where)]
    if not isinstance(prop, Mapping):
        return []
    identity = id(prop)
    if identity in seen:
        return []
    seen.add(identity)
    errors: list[str] = []
    pattern = prop.get("pattern")
    if isinstance(pattern, str):
        failure = _compile_pattern(pattern)
        if failure is not None:
            errors.append(f"{where}/pattern: {failure}")
    items = prop.get("items")
    if isinstance(items, Mapping):
        errors.extend(_prop_errors(items, f"{where}/items", depth + 1, seen))
    return errors


@lru_cache(maxsize=len(_SCHEMA_FILES))
def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(
        load_schema(name),
        registry=_registry(),
        format_checker=_format_checker(),
    )


@lru_cache(maxsize=1)
def _format_checker() -> FormatChecker:
    base = Draft202012Validator.FORMAT_CHECKER
    checker = FormatChecker(base.checkers)
    # date-time is an annotation unless this checker is installed. The frozen
    # schema uses it for verified_at (RFC 3339), and the pinned deps do not
    # include rfc3339-validator.
    checker.checkers["date-time"] = (_is_rfc3339, ())
    return checker


def _is_rfc3339(instance: object) -> bool:
    if not isinstance(instance, str):
        return True
    match = _RFC3339.fullmatch(instance)
    if match is None:
        return False
    try:
        datetime(int(match["year"]), int(match["month"]), int(match["day"]))
    except ValueError:
        return False
    hour = int(match["hour"])
    minute = int(match["minute"])
    second = int(match["second"])
    if hour > 23 or minute > 59 or second > 60:
        return False
    offset_hour = match["off_hour"]
    offset_minute = match["off_minute"]
    if offset_hour is None or offset_minute is None:
        return offset_hour is None and offset_minute is None
    return int(offset_hour) <= 23 and int(offset_minute) <= 59
