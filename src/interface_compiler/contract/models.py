"""Pydantic models for the frozen v1 compiled view document and act response."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from interface_compiler.contract.validate import (
    ContractError,
    _compile_pattern,
    _schema_nesting_errors,
    validate_doc,
    validate_effect,
)

_ID = r"^[a-z][a-z0-9_]*$"
_NULLABLE_FIELDS = frozenset({"match", "main_status", "blocked", "total", "next"})


def _is_scalar(value: object) -> bool:
    if value is None or isinstance(value, str | bool):
        return True
    if isinstance(value, int):
        return True
    return isinstance(value, float)


def _is_record(value: dict[str, Any]) -> bool:
    return all(_is_record_value(item) for item in value.values())


def _is_record_value(value: object) -> bool:
    if _is_scalar(value):
        return True
    return isinstance(value, list) and all(_is_scalar(item) for item in value)


class Prop(BaseModel):
    """One argument property inside an affordance input schema."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["string", "number", "integer", "boolean", "array"]
    enum: list[Any] | None = None
    format: Literal["email", "uri", "date", "time", "date-time", "tel"] | None = None
    pattern: str | None = None
    minLength: int | None = Field(default=None, ge=0)
    maxLength: int | None = Field(default=None, ge=0)
    minimum: int | float | None = None
    maximum: int | float | None = None
    multipleOf: int | float | None = None
    items: Prop | None = None

    @model_validator(mode="before")
    @classmethod
    def _limit_nesting(cls, value: object) -> object:
        if isinstance(value, Mapping):
            errors = _schema_nesting_errors(value, "items")
            if errors:
                raise ValueError(errors[0])
        return value

    @field_validator("pattern")
    @classmethod
    def _pattern_compiles(cls, value: str | None) -> str | None:
        if value is None:
            return None
        failure = _compile_pattern(value)
        if failure is not None:
            raise ValueError(str(failure)) from failure
        return value

    @field_validator("enum")
    @classmethod
    def _enum_non_empty(cls, value: list[Any] | None) -> list[Any] | None:
        if value is not None and len(value) == 0:
            raise ValueError("enum must be omitted when empty")
        return value

    @field_validator("minimum", "maximum", "multipleOf")
    @classmethod
    def _number(cls, value: object) -> object:
        if isinstance(value, bool):
            raise TypeError("must be a number")
        return value

    @field_validator("multipleOf")
    @classmethod
    def _multiple_of_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("multipleOf must be greater than 0")
        return value


class InputSchema(BaseModel):
    """The ``input`` object on an affordance. Empty ``required`` is invalid."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["object"]
    properties: dict[str, Prop]
    required: list[str] | None = None

    @model_validator(mode="before")
    @classmethod
    def _required_not_null(cls, value: object) -> object:
        _reject_explicit_null(value, "required")
        return value

    @field_validator("required")
    @classmethod
    def _required_non_empty(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if len(value) == 0:
            raise ValueError("required must be omitted when empty")
        if len(set(value)) != len(value):
            raise ValueError("required items must be unique")
        return value

    @model_validator(mode="after")
    def _required_names_properties(self) -> Self:
        if self.required is None:
            return self
        missing = [name for name in self.required if name not in self.properties]
        if missing:
            names = ", ".join(missing)
            raise ValueError(f"required entries not in properties: {names}")
        return self


class Locator(BaseModel):
    """How to find an affordance. Extra keys are allowed for an owner recipe."""

    model_config = ConfigDict(extra="allow")

    kind: Literal["ax", "form", "group", "repeat", "jsonld", "webmcp", "registry"]
    role: str | None = None
    name: str | None = None
    landmark: str | None = None
    nth: int | None = Field(default=None, ge=0)
    css: str | None = None
    fields: dict[str, str] | None = None
    options: dict[str, str] | None = None
    repeat: str | None = None
    item_key: str | None = None
    url_template: str | None = None
    method: str | None = None
    tool: str | None = None
    named_by: Literal["rule", "embed", "llm", "declared"] | None = None


class AffordanceX(BaseModel):
    """Extension fields for one affordance. All of them are optional."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = None
    tag: Literal["safe", "mutating"] | None = None
    label: str | None = None
    locator: Locator | None = None
    signature: str | None = None
    grain: Literal["single", "field", "form", "collapsed", "declared"] | None = None
    source: Literal["compiled", "owner"] | None = None
    verified: (
        Literal[
            "unverified",
            "probed_ok",
            "probed_failed",
            "stopped_before_commit",
        ]
        | None
    ) = None
    verified_at: str | None = None


class Affordance(BaseModel):
    """One action: ``id``, ``enabled``, and an ``input`` schema."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_ID)
    enabled: StrictBool
    input: InputSchema
    x: AffordanceX | None = None

    @model_validator(mode="before")
    @classmethod
    def _x_not_null(cls, value: object) -> object:
        _reject_explicit_null(value, "x")
        return value


class PageCursor(BaseModel):
    """Paging cursor for one entity list."""

    model_config = ConfigDict(extra="forbid")

    offset: StrictInt
    limit: StrictInt
    total: StrictInt | None = None
    next: str | None = None


class Signature(BaseModel):
    """Page signature stored on ``x``."""

    model_config = ConfigDict(extra="forbid")

    route: str | None = None
    skeleton_hash: str | None = None
    template: str | None = None


class PrecheckStats(BaseModel):
    """Counts from the static pre-check."""

    model_config = ConfigDict(extra="forbid")

    ok: StrictInt
    failed: StrictInt


class RegistryStats(BaseModel):
    """How many affordances the session registry carried or dropped."""

    model_config = ConfigDict(extra="forbid")

    carried: StrictInt
    dropped: StrictInt


class Blocked(BaseModel):
    """Why a look stopped before compiling actions."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["robots", "bot_wall", "login", "excluded", "captcha"]
    detail: str


class DocX(BaseModel):
    """The only top-level extension object."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] | None = None
    source: Literal["compiled", "owner"] | None = None
    url: str | None = None
    title: str | None = None
    signature: Signature | None = None
    page: dict[str, PageCursor] | None = None
    state_from: dict[str, Literal["control", "aria", "badge", "session", "url"]] | None = None
    entities_from: dict[str, Literal["jsonld", "microdata", "repeat", "webmcp"]] | None = None
    precheck: PrecheckStats | None = None
    registry: RegistryStats | None = None
    blocked: Blocked | None = None


class ViewDoc(BaseModel):
    """A compiled view document: ``view``, ``state``, ``entities``, ``affordances``, optional ``x``."""

    model_config = ConfigDict(extra="forbid")

    view: str = Field(pattern=_ID)
    state: dict[str, Any]
    entities: dict[str, Any]
    affordances: list[Affordance]
    x: DocX | None = None

    @model_validator(mode="before")
    @classmethod
    def _schema_before_parse(cls, value: object) -> object:
        _reject_explicit_null(value, "x")
        _validate_raw(value, validate_doc)
        return value

    @field_validator("state")
    @classmethod
    def _flat_state(cls, value: dict[str, Any]) -> dict[str, Any]:
        for key, item in value.items():
            if not _is_scalar(item):
                raise ValueError(f"state.{key} must be a scalar")
        return value

    @field_validator("entities")
    @classmethod
    def _entity_shape(cls, value: dict[str, Any]) -> dict[str, Any]:
        for name, item in value.items():
            if isinstance(item, list):
                if all(isinstance(row, dict) and _is_record(row) for row in item):
                    continue
                raise ValueError(f"entities.{name} must be a list of flat records")
            if isinstance(item, dict) and _is_record(item):
                continue
            raise ValueError(f"entities.{name} must be a record or a list of records")
        return value

    @model_validator(mode="after")
    def _matches_schema(self) -> Self:
        validate_doc(dump_view_doc(self))
        return self


class Predicted(BaseModel):
    """What an action was expected to change."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "navigate",
        "state_change",
        "aria_change",
        "entities_change",
        "dialog",
        "none",
        "unknown",
    ]
    detail: dict[str, Any]


class Observed(BaseModel):
    """What the page did after an action."""

    model_config = ConfigDict(extra="forbid")

    url_before: str
    url_after: str
    view_before: str
    view_after: str
    state_diff: dict[str, Any]
    entities_diff: dict[str, Any]
    main_status: int | None
    dialogs: list[str]
    console_errors: list[str]


class BlockedRequest(BaseModel):
    """A non-GET request the browser aborted."""

    model_config = ConfigDict(extra="forbid")

    method: str
    url: str
    fields: dict[str, str]
    reason: str


class Demotion(BaseModel):
    """An affordance demoted after a failed effect check."""

    model_config = ConfigDict(extra="forbid")

    affordance_id: str
    reason: str
    expires_at: str
    expires_after_looks: int


class Effect(BaseModel):
    """Predicted versus observed outcome of an executed action."""

    model_config = ConfigDict(extra="forbid")

    predicted: Predicted
    observed: Observed
    match: StrictBool | None
    blocked_requests: list[BlockedRequest]
    demoted: list[Demotion]


class ClientValidation(BaseModel):
    """Browser validation captured before a mutating action is sent."""

    model_config = ConfigDict(extra="forbid")

    valid: StrictBool
    messages: list[str]


class Preview(BaseModel):
    """What a mutating action would send. Returned with ``needs_confirmation``."""

    model_config = ConfigDict(extra="forbid")

    method: str
    url: str
    fields: dict[str, Any]
    client_validation: ClientValidation


class ActErrorBody(BaseModel):
    """Error payload. Omitted from the act response when ``echo_errors`` is false."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any] | None = None


class Counters(BaseModel):
    """Session counters. Always present on an act response."""

    model_config = ConfigDict(extra="forbid")

    illegal: StrictInt
    malformed: StrictInt
    ignored: StrictInt
    stale: StrictInt
    blocked: StrictInt
    acts: StrictInt


class ActResult(BaseModel):
    """The response from ``act``."""

    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "ok",
        "stale",
        "disabled",
        "invalid_args",
        "needs_confirmation",
        "blocked",
        "error",
    ]
    doc_rev: StrictInt
    doc: ViewDoc
    effect: Effect | None = None
    preview: Preview | None = None
    confirm_token: str | None = None
    error: ActErrorBody | None = None
    counters: Counters

    @model_validator(mode="before")
    @classmethod
    def _schema_before_parse(cls, value: object) -> object:
        _validate_raw(value, validate_effect)
        return value

    @model_validator(mode="after")
    def _matches_schema(self) -> Self:
        validate_effect(dump_act_result(self))
        return self


def dump_view_doc(doc: ViewDoc) -> dict[str, Any]:
    """Serialize a compiled view document, omitting unset optional fields."""
    return _dump_model(doc)


def dump_act_result(result: ActResult, *, echo_errors: bool = True) -> dict[str, Any]:
    """Serialize an act response.

    ``echo_errors`` defaults to true. When it is false, the ``error`` key is
    omitted, which is the paper-replication loop. Counters stay.
    """
    dumped = _dump_model(result)
    if not echo_errors:
        dumped.pop("error", None)
    return dumped


def _reject_explicit_null(value: object, key: str) -> None:
    """JSON Schema rejects null for these optional fields; omission is allowed."""
    if isinstance(value, Mapping) and key in value and value[key] is None:
        raise ValueError(f"{key} must be omitted rather than null")


def _validate_raw(value: object, validate: Callable[[Mapping[str, Any]], None]) -> None:
    """Check JSON input against the schema before pydantic can coerce it."""
    if not isinstance(value, Mapping) or not _is_json_value(value):
        return
    try:
        validate(value)
    except ContractError as exc:
        raise ValueError(str(exc)) from exc


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, str | bool | int | float):
        return True
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _is_json_value(item) for key, item in value.items())
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    return False


def _dump_model(model: BaseModel) -> dict[str, Any]:
    dumped: dict[str, Any] = {}
    for name in model.__class__.model_fields:
        value = getattr(model, name)
        if value is None and name not in model.model_fields_set:
            continue
        if value is None and name not in _NULLABLE_FIELDS:
            continue
        dumped[name] = _dump_value(value)
    extras = model.__pydantic_extra__ or {}
    for name, value in extras.items():
        dumped[name] = _dump_value(value)
    return dumped


def _dump_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _dump_model(value)
    if isinstance(value, dict):
        return {key: _dump_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_dump_value(item) for item in value]
    return value
