"""Validate compiled view documents, act responses, and affordance arguments."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
from pydantic import BaseModel
from referencing import Registry, Resource

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
# jsonschema follows items/$ref recursively and overflows the stack on a
# chain a few hundred levels deep. Stop before that walk.
_MAX_SCHEMA_DEPTH = 32
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
    schema = _input_schema(affordance)
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
    depth_errors = _document_nesting_errors(instance)
    if depth_errors:
        raise ContractError(depth_errors[0], errors=depth_errors)
    _raise_if_invalid(_validator(name), instance)
    errors = [
        *_exact_id_errors(instance),
        *_duplicate_id_errors(instance),
        *_affordance_constraint_errors(instance),
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
    location = "/".join(str(part) for part in error.absolute_path)
    where = location or "<root>"
    return f"{where}: {error.message}"


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
        errors.append(f"{prefix}view: {view!r} does not match '^[a-z][a-z0-9_]*$'")
    affordances = instance.get("affordances")
    if isinstance(affordances, list):
        for index, item in enumerate(affordances):
            if not isinstance(item, Mapping):
                continue
            ident = item.get("id")
            if isinstance(ident, str) and _EXACT_ID.fullmatch(ident) is None:
                where = f"{prefix}affordances/{index}/id"
                errors.append(f"{where}: {ident!r} does not match '^[a-z][a-z0-9_]*$'")
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
            errors.append(f"{where}: duplicate id {ident!r} (also at {also})")
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
                errors.append(f"{where}/required/{index}: {name!r} is not a property")
    if isinstance(properties, Mapping):
        for key, prop in properties.items():
            errors.extend(_prop_errors(prop, f"{where}/properties/{key}"))
    return errors


def _compile_pattern(pattern: str) -> ContractError | None:
    """Return a contract error when Python cannot compile ``pattern``."""
    try:
        re.compile(pattern)
    except _PATTERN_COMPILE_ERRORS as exc:
        message = f"{_echo_pattern(pattern)} is not a valid regular expression ({exc})"
        return ContractError(message, errors=[message])
    return None


def _echo_pattern(pattern: str) -> str:
    if len(pattern) <= _PATTERN_ECHO_LIMIT:
        return repr(pattern)
    return repr(f"{pattern[:_PATTERN_ECHO_LIMIT]}...")


def nesting_too_deep(where: str) -> str:
    """Contract message for an items or properties chain past the nesting limit."""
    return f"{where}: nesting exceeds {_MAX_SCHEMA_DEPTH} (max {_MAX_SCHEMA_DEPTH})"


def _schema_nesting_errors(node: object, where: str, *, depth: int = 0) -> list[str]:
    """Reject a schema node more than ``_MAX_SCHEMA_DEPTH`` edges below its property.

    ``depth`` is the number of ``items`` or nested ``properties`` edges followed
    to reach ``node``. Depth 32 is allowed. Depth 33 is not. The input object's
    own ``properties`` map is not an edge; callers pass each property at depth 0.
    """
    if depth > _MAX_SCHEMA_DEPTH:
        return [nesting_too_deep(where)]
    if not isinstance(node, Mapping):
        return []
    errors: list[str] = []
    properties = node.get("properties")
    if isinstance(properties, Mapping):
        for key, child in properties.items():
            child_where = f"{where}/properties/{key}"
            errors.extend(_schema_nesting_errors(child, child_where, depth=depth + 1))
    items = node.get("items")
    if isinstance(items, Mapping):
        errors.extend(_schema_nesting_errors(items, f"{where}/items", depth=depth + 1))
    return errors


def _input_nesting_errors(schema: object, where: str) -> list[str]:
    if not isinstance(schema, Mapping):
        return []
    errors: list[str] = []
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        for key, child in properties.items():
            child_where = f"{where}/properties/{key}"
            errors.extend(_schema_nesting_errors(child, child_where, depth=0))
    return errors


def _document_nesting_errors(instance: object, *, prefix: str = "") -> list[str]:
    if not isinstance(instance, Mapping):
        return []
    errors: list[str] = []
    affordances = instance.get("affordances")
    if isinstance(affordances, list):
        for index, item in enumerate(affordances):
            if not isinstance(item, Mapping):
                continue
            where = f"{prefix}affordances/{index}/input"
            errors.extend(_input_nesting_errors(item.get("input"), where))
    doc = instance.get("doc")
    if isinstance(doc, Mapping):
        errors.extend(_document_nesting_errors(doc, prefix=f"{prefix}doc/"))
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


def _prop_errors(prop: object, where: str, depth: int = 0) -> list[str]:
    if depth > _MAX_SCHEMA_DEPTH:
        return [nesting_too_deep(where)]
    if not isinstance(prop, Mapping):
        return []
    errors: list[str] = []
    pattern = prop.get("pattern")
    if isinstance(pattern, str):
        failure = _compile_pattern(pattern)
        if failure is not None:
            errors.append(f"{where}/pattern: {failure}")
    items = prop.get("items")
    if isinstance(items, Mapping):
        errors.extend(_prop_errors(items, f"{where}/items", depth + 1))
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
