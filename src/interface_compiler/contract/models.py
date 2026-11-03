"""Pydantic models for the frozen v1 compiled view document and act response."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextvars import ContextVar
from typing import Any, Literal, NoReturn, Self

import pydantic_core
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    StrictBool,
    StrictInt,
    field_validator,
    model_serializer,
    model_validator,
)
from pydantic_core import PydanticSerializationError

from interface_compiler.checker.verified import probed_ok_refusal, verified_errors
from interface_compiler.contract.validate import (
    ContractError,
    _compile_pattern,
    _echo_value,
    _guard_json_document,
    _json_copy,
    _schema_nesting_errors,
    nesting_too_deep,
    validate_doc,
    validate_effect,
)

_ID = r"^[a-z][a-z0-9_]*$"
_NULLABLE_FIELDS = frozenset({"match", "main_status", "blocked", "total", "next"})
_VERIFIED_STATES = (
    "unverified",
    "probed_ok",
    "probed_failed",
    "stopped_before_commit",
)
# Set only while a view document is being validated, so a loopback page may
# still construct a mutating probed_ok affordance. Direct construction has none.
_affordance_page_url: ContextVar[object] = ContextVar("affordance_page_url", default=None)
# The wrap serializer raises ContractError, and pydantic-core wraps that in
# PydanticSerializationError before model_dump, model_dump_json, or to_json
# returns. The original error is stashed here so those callers still see it.
_pending_probe: ContextVar[ContractError | None] = ContextVar("pending_probe", default=None)


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
    # Direct assignment has no page URL, so probed_ok is refused unless the
    # tag is safe. set_verified passes its own page-URL check. Once a view
    # document owns this row, that document's x.url wins over the argument.
    _verified_locked: bool = PrivateAttr(default=False)
    _page_bound: bool = PrivateAttr(default=False)
    _bound_page_url: object = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _lock_verified(self) -> Self:
        _refuse_unscoped_probe(self.tag, self.verified)
        self._verified_locked = True
        return self

    def __setattr__(self, name: str, value: object) -> None:
        if name in {"verified", "tag"} and getattr(self, "_verified_locked", False):
            self._assign_guarded(name, value)
            return
        super().__setattr__(name, value)

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        if update and ("tag" in update or "verified" in update):
            tag = update.get("tag", self.tag)
            verified = update.get("verified", self.verified)
            _refuse_unscoped_probe(tag, verified)
        copied = super().model_copy(update=update, deep=deep)
        copied._verified_locked = True
        return copied

    def set_verified(self, status: str, *, page_url: str | None) -> None:
        """Record a probe outcome for this affordance.

        ``probed_ok`` is refused when the tag is missing or ``mutating`` and
        the page is not a loopback fixture host. On a row owned by a view
        document, ``page_url`` has to be that document's ``x.url``; a different
        argument is not trusted. The field is left unchanged when the outcome
        is refused. Assigning ``verified`` directly has the same refusal, with
        no page URL, so a loopback outcome has to go through this method.
        """
        if status not in _VERIFIED_STATES:
            message = f"verified {_echo_value(status)} is not a probe outcome"
            raise ContractError(message, errors=[message])
        check_url: object = page_url
        document_url = getattr(self, "_bound_page_url", None)
        if getattr(self, "_page_bound", False) and page_url != document_url:
            check_url = document_url
            message = probed_ok_refusal(self.tag, status, page_url=check_url)
            if message is None:
                message = "page_url does not match x.url"
            raise ContractError(message, errors=[message])
        message = probed_ok_refusal(self.tag, status, page_url=check_url)
        if message is not None:
            raise ContractError(message, errors=[message])
        self._assign_verified(status)

    def _assign_guarded(self, name: str, value: object) -> None:
        if name == "verified" and value is not None and value not in _VERIFIED_STATES:
            message = f"verified {_echo_value(value)} is not a probe outcome"
            raise ContractError(message, errors=[message])
        tag = value if name == "tag" else self.tag
        verified = value if name == "verified" else self.verified
        _refuse_unscoped_probe(tag, verified)
        self._assign_verified(value if name == "verified" else self.verified, tag=tag, name=name)

    def _assign_verified(
        self,
        value: object,
        *,
        tag: object | None = None,
        name: str = "verified",
    ) -> None:
        self._verified_locked = False
        try:
            if name == "tag":
                super().__setattr__("tag", tag)
            else:
                super().__setattr__("verified", value)
        finally:
            self._verified_locked = True


class Affordance(BaseModel):
    """One action: ``id``, ``enabled``, and an ``input`` schema."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_ID)
    enabled: StrictBool
    input: InputSchema
    x: AffordanceX | None = None

    def __setattr__(self, name: str, value: object) -> None:
        # Replacing x used to drop the document binding, so set_verified would
        # trust a loopback page_url on a public document.
        if name == "x" and isinstance(value, AffordanceX):
            previous = self.__dict__.get("x")
            if isinstance(previous, AffordanceX) and previous is not value:
                value._page_bound = bool(getattr(previous, "_page_bound", False))
                value._bound_page_url = getattr(previous, "_bound_page_url", None)
        super().__setattr__(name, value)

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

    # Set by the owning view after a legal document is built. Assigning url
    # then checks that document's probed_ok rows.
    _guard_url: Callable[[object], None] | None = PrivateAttr(default=None)

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

    def __setattr__(self, name: str, value: object) -> None:
        if name == "url":
            guard = getattr(self, "_guard_url", None)
            if guard is not None:
                guard(value)
        super().__setattr__(name, value)


class ViewDoc(BaseModel):
    """A compiled view document: ``view``, ``state``, ``entities``, ``affordances``, optional ``x``."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    view: str = Field(pattern=_ID)
    state: dict[str, Any]
    entities: dict[str, Any]
    affordances: list[Affordance]
    x: DocX | None = None
    _url_locked: bool = PrivateAttr(default=False)

    def __setattr__(self, name: str, value: object) -> None:
        if name == "x" and getattr(self, "_url_locked", False):
            self._refuse_url(value.url if isinstance(value, DocX) else None)
        super().__setattr__(name, value)
        if name == "x" and getattr(self, "_url_locked", False):
            self._arm_url_guard()

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        copied = super().model_copy(update=update, deep=deep)
        _refuse_dumped_probe(copied)
        if copied.x is None or not (deep or copied.x is not self.x):
            return copied
        # A shallow copy shares affordance rows. Rebinding those rows would
        # point the original document's probes at this copy's URL.
        copied._url_locked = True
        copied.x._guard_url = copied._refuse_url
        if deep or copied.affordances is not self.affordances:
            copied._bind_probe_url(copied.x.url)
        return copied

    @model_serializer(mode="wrap")
    def _serialize_model(self, handler: Any) -> Any:
        return _checked_serialize(self, handler)

    def model_dump(self, **kwargs: Any) -> Any:
        return _dump_refusing_probe(lambda: BaseModel.model_dump(self, **kwargs))

    def model_dump_json(self, **kwargs: Any) -> Any:
        return _dump_refusing_probe(lambda: BaseModel.model_dump_json(self, **kwargs))

    @model_validator(mode="wrap")
    @classmethod
    def _scope_page_url(cls, value: Any, handler: Any) -> Self:
        token = _affordance_page_url.set(_raw_page_url(value))
        try:
            return handler(value)
        finally:
            _affordance_page_url.reset(token)

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
        self._arm_url_guard()
        return self

    def _arm_url_guard(self) -> None:
        self._url_locked = True
        extra = self.x
        if extra is not None:
            extra._guard_url = self._refuse_url
        self._bind_probe_url(extra.url if extra is not None else None)

    def _bind_probe_url(self, url: object) -> None:
        for item in self.affordances:
            extra = item.x
            if extra is None:
                continue
            extra._page_bound = True
            extra._bound_page_url = url

    def _refuse_url(self, url: object) -> None:
        for index, item in enumerate(self.affordances):
            extra = item.x
            if extra is None:
                continue
            message = probed_ok_refusal(extra.tag, extra.verified, page_url=url)
            if message is None:
                continue
            text = f"affordances/{index}/x/verified: {message}"
            raise ContractError(text, errors=[text])
        self._bind_probe_url(url)


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

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

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

    @model_serializer(mode="wrap")
    def _serialize_model(self, handler: Any) -> Any:
        return _checked_serialize(self, handler)

    def model_dump(self, **kwargs: Any) -> Any:
        return _dump_refusing_probe(lambda: BaseModel.model_dump(self, **kwargs))

    def model_dump_json(self, **kwargs: Any) -> Any:
        return _dump_refusing_probe(lambda: BaseModel.model_dump_json(self, **kwargs))


def dump_view_doc(doc: ViewDoc) -> dict[str, Any]:
    """Serialize a compiled view document, omitting unset optional fields.

    A mutating ``probed_ok`` affordance on a public ``x.url`` is not serialized,
    including when the outcome was recorded against a different page URL.
    """
    dumped = _dump_model(doc)
    _refuse_dumped_probe(dumped)
    return dumped


def _checked_serialize(model: BaseModel, handler: Any) -> Any:
    """Run the probe refusal for ``model_dump``, ``model_dump_json``, and ``to_json``."""
    dumped = handler(model)
    if isinstance(dumped, dict):
        try:
            _refuse_dumped_probe(dumped)
        except ContractError as exc:
            _pending_probe.set(exc)
            raise
    return dumped


def _dump_refusing_probe(dump: Callable[[], Any]) -> Any:
    try:
        return dump()
    except PydanticSerializationError as exc:
        _reraise_probe(exc)


def _reraise_probe(exc: PydanticSerializationError) -> NoReturn:
    pending = _pending_probe.get()
    _pending_probe.set(None)
    if isinstance(pending, ContractError):
        raise pending from None
    cause = exc.__cause__
    while cause is not None:
        if isinstance(cause, ContractError):
            raise cause from None
        cause = cause.__cause__
    raise exc


def _to_json_refusing_probe(value: object, *args: object, **kwargs: object) -> Any:
    try:
        return _PYDANTIC_TO_JSON(value, *args, **kwargs)
    except PydanticSerializationError as exc:
        _reraise_probe(exc)


_PYDANTIC_TO_JSON = pydantic_core.to_json
pydantic_core.to_json = _to_json_refusing_probe


def _refuse_dumped_probe(doc: ViewDoc | dict[str, Any]) -> None:
    payload = doc if isinstance(doc, dict) else _dump_model(doc)
    errors = verified_errors(payload)
    if errors:
        raise ContractError(errors[0], errors=errors)


def dump_act_result(result: ActResult, *, echo_errors: bool = True) -> dict[str, Any]:
    """Serialize an act response.

    ``echo_errors`` defaults to true. When it is false, the ``error`` key is
    omitted, which is the paper-replication loop. Counters stay. A mutating
    ``probed_ok`` affordance on a public page URL is not serialized.
    """
    dumped = _dump_model(result)
    if not echo_errors:
        dumped.pop("error", None)
    _refuse_dumped_probe(dumped)
    return dumped


def _raw_page_url(value: object) -> object:
    if not isinstance(value, Mapping):
        return None
    extra = value.get("x")
    if not isinstance(extra, Mapping):
        return None
    return extra.get("url")


def _refuse_unscoped_probe(tag: object, verified: object) -> None:
    message = probed_ok_refusal(tag, verified, page_url=_affordance_page_url.get())
    if message is not None:
        raise ContractError(message, errors=[message])


def _reject_explicit_null(value: object, key: str) -> None:
    """JSON Schema rejects null for these optional fields; omission is allowed."""
    if isinstance(value, Mapping) and key in value and value[key] is None:
        raise ValueError(f"{key} must be omitted rather than null")


def _validate_raw(value: object, validate: Callable[[Mapping[str, Any]], None]) -> None:
    """Check JSON input against the schema before pydantic can coerce it."""
    if not isinstance(value, dict):
        return
    try:
        _guard_json_document(value)
        validate(value)
    except ContractError as exc:
        raise ValueError(str(exc)) from exc
    except RecursionError as exc:
        raise ValueError(nesting_too_deep("<root>")) from exc


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
    """Return a JSON-ready copy of ``value``.

    Nested models are dumped directly. A pure JSON container is copied with
    ``_json_copy``, which does not walk shared structure or unbounded depth.
    """
    if isinstance(value, BaseModel):
        return _dump_model(value)
    if isinstance(value, dict):
        if any(isinstance(item, BaseModel) for item in value.values()):
            return {key: _dump_value(item) for key, item in value.items()}
        return _json_copy(value)
    if isinstance(value, list):
        if any(isinstance(item, BaseModel) for item in value):
            return [_dump_value(item) for item in value]
        return _json_copy(value)
    return value
