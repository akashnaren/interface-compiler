"""Form grain versus field grain."""

from __future__ import annotations

from typing import NamedTuple

from interface_compiler.browser.facts import ElementFact, FormFact
from interface_compiler.contract.models import Locator
from interface_compiler.extract.lexicon import Lexicon
from interface_compiler.extract.naming import field_name, slug
from interface_compiler.mapping.choice import map_choice_group
from interface_compiler.mapping.enabled import element_enabled
from interface_compiler.mapping.input_schema import named_property
from interface_compiler.mapping.range import map_range
from interface_compiler.mapping.select import map_select
from interface_compiler.mapping.toggle import map_checkbox
from interface_compiler.mapping.types import (
    _BEFORE_HARD,
    MapContext,
    MapResult,
    affordance,
    apply_hard_block,
    ax_locator,
    input_schema,
    merge_results,
    note_sources,
    stable_signature,
)

_FREE = frozenset(
    {"text", "search", "password", "tel", "email", "url", "date", "time", "datetime-local"}
)


class _Submit(NamedTuple):
    element: ElementFact
    verb: str | None
    method: str
    action: str


def map_form(form: FormFact, fields: list[ElementFact], ctx: MapContext) -> MapResult:
    controls = [element for element in fields if _is_control(element)]
    submits = [_submit_choice(element, form, ctx) for element in fields if _is_submit(element)]
    if submits and all(item.verb for item in submits) and _field_grain(controls, submits[0].verb):
        return _field_grain_result(form, controls, submits, ctx)
    return _form_grain_result(form, controls, submits, ctx)


def _submit_choice(submit: ElementFact, form: FormFact, ctx: MapContext) -> _Submit:
    """One submitter: its formmethod and formaction, else the form's own."""
    method = (submit.form_method or form.method or "get").lower()
    action = submit.form_action or form.action
    verb = ctx.lexicon.verb(submit.name) if submit.name else None
    view = ctx.view_hint or ctx.lexicon.view_for_href(ctx.page_url)
    if view == "checkout" and method != "get" and not ctx.lexicon.hard_block(verb):
        verb = "checkout_submit"
    return _Submit(submit, verb, method, action)


def fill_missing(
    result: MapResult,
    filled: set[str],
    submit: ElementFact | None = None,
    *,
    form_disabled: bool = False,
) -> MapResult:
    """Re-run the full submit check once every missing field is filled."""
    lexicon = Lexicon()
    updated: list = []
    for item in result.affordances:
        extra = item.x
        reason = extra.reason if extra else None
        if extra is None or not (reason and reason.startswith("missing: ")):
            updated.append(item)
            continue
        names = {
            part.strip() for part in reason.removeprefix("missing: ").split(",") if part.strip()
        }
        if submit is None or not names <= filled:
            updated.append(item)
            continue
        enabled, new_reason = element_enabled(submit)
        verb = item.id
        if lexicon.hard_block(verb) is None:
            named = lexicon.verb(extra.label or "")
            if named:
                verb = named
        enabled, new_reason = gate_submit(
            enabled,
            new_reason,
            verb=verb,
            lexicon=lexicon,
            form_disabled=form_disabled or submit.disabled,
        )
        updated.append(
            item.model_copy(
                update={
                    "enabled": enabled,
                    "x": extra.model_copy(update={"reason": new_reason}),
                }
            )
        )
    result.affordances = updated
    return result


def gate_submit(
    enabled: bool,
    reason: str | None,
    *,
    verb: str | None,
    lexicon: Lexicon,
    form_disabled: bool = False,
    missing: tuple[str, ...] = (),
    upload: bool = False,
) -> tuple[bool, str | None]:
    """Hard-block beats a missing field. ``form.disabled`` sticks either way."""
    if upload:
        return False, "hard-blocked in v1: upload"
    enabled, reason = apply_hard_block(enabled, reason, verb, lexicon)
    if reason and (reason.startswith("hard-blocked") or reason in _BEFORE_HARD):
        return False, reason
    if not enabled:
        return False, reason
    if form_disabled:
        return False, "disabled"
    if missing:
        return False, "missing: " + ", ".join(missing)
    return True, None


def _field_grain_result(
    form: FormFact,
    controls: list[ElementFact],
    submits: list[_Submit],
    ctx: MapContext,
) -> MapResult:
    parts: list[MapResult] = []
    missing = _missing(form, controls)
    radios: dict[str, list[ElementFact]] = {}
    for element in controls:
        if element.role == "radio":
            radios.setdefault(element.group_key or element.name or "choice", []).append(element)
        elif _numeric(element):
            parts.append(map_range(element, ctx))
        elif element.tag == "select" or element.role in {"combobox", "listbox"}:
            parts.append(map_select(element, ctx))
        elif element.role in {"checkbox", "switch"}:
            parts.append(map_checkbox(element, ctx))
    for group in radios.values():
        parts.append(map_choice_group(group, ctx))
    upload = any(element.input_type == "file" for element in controls)
    for item in submits:
        if not item.verb:
            continue
        enabled, reason = element_enabled(item.element)
        enabled, reason = gate_submit(
            enabled,
            reason,
            verb=item.verb,
            lexicon=ctx.lexicon,
            form_disabled=form.disabled,
            missing=tuple(missing),
            upload=upload,
        )
        locator = ax_locator(item.element, kind="form", method=item.method)
        if item.action and item.action != form.action:
            note_sources(locator, urls=(item.action,))
        parts.append(
            MapResult(
                affordances=[
                    affordance(
                        item.verb,
                        enabled=enabled,
                        label=item.element.name,
                        locator=locator,
                        grain="field",
                        tag=ctx.lexicon.tag(item.verb, method=item.method),
                        reason=reason,
                        signature=stable_signature("form-field", item.verb, item.element.landmark),
                    )
                ]
            )
        )
    merged = merge_results(parts)
    for item in merged.affordances:
        if item.x is not None:
            item.x.grain = "field"
    return merged


def _form_grain_result(
    form: FormFact,
    controls: list[ElementFact],
    submits: list[_Submit],
    ctx: MapContext,
) -> MapResult:
    properties: dict[str, dict[str, object]] = {}
    required: list[str] = []
    state: dict[str, object] = {}
    state_from: dict[str, str] = {}
    for element in controls:
        named = named_property(element)
        if named is None:
            continue
        name, prop = named
        if element.value is not None and element.role not in {"button"}:
            state[name] = "<redacted>" if element.input_type == "password" else element.value
            state_from[name] = "control"
        if element.disabled or element.aria_disabled:
            continue
        properties[name] = prop
        if element.constraints.required:
            required.append(name)
    search = _is_search(form, controls, properties)
    upload = any(element.input_type == "file" for element in controls)
    entries: list[_Submit | None] = list(submits) or [None]
    single = len(entries) == 1
    affordances = []
    for item in entries:
        verb = item.verb if item else None
        method = item.method if item else form.method
        action = item.action if item else form.action
        submit = item.element if item else None
        if single and search and not ctx.lexicon.hard_block(verb):
            affordance_id = "search"
            verb = "search"
        elif verb:
            affordance_id = verb
        else:
            affordance_id = "submit_" + (_form_slug(form, controls) or "form")
        label = submit.name if submit else affordance_id
        if submit is not None:
            enabled, reason = element_enabled(submit)
        else:
            enabled, reason = _form_enabled(form, controls)
        enabled, reason = gate_submit(
            enabled,
            reason,
            verb=verb,
            lexicon=ctx.lexicon,
            form_disabled=form.disabled,
            upload=upload,
        )
        if upload:
            verb = "upload"
        # A POST search still mutates. Only a GET search is safe.
        if search and method == "get":
            tag = "safe"
        else:
            tag = ctx.lexicon.tag(verb, method=method)
        locator = (
            ax_locator(
                submit or controls[0],
                kind="form",
                method=method,
                fields={name: name for name in properties},
            )
            if submit or controls
            else ax_locator_fallback(form)
        )
        if action and action != form.action:
            note_sources(locator, urls=(action,))
        affordances.append(
            affordance(
                affordance_id,
                enabled=enabled,
                schema=input_schema(properties, required or None),
                label=label,
                locator=locator,
                grain="form",
                tag=tag,
                reason=reason,
                signature=stable_signature("form", affordance_id, form.action),
            )
        )
    return MapResult(affordances=affordances, state=state, state_from=state_from)


def ax_locator_fallback(form: FormFact) -> Locator:
    return Locator.model_validate(
        {"kind": "form", "method": form.method, "named_by": "rule", "html_id": form.html_id}
    )


def _field_grain(controls: list[ElementFact], verb: str | None) -> bool:
    if verb is None:
        return False
    return not any(_free_text(element) for element in controls)


def _numeric(element: ElementFact) -> bool:
    return element.input_type in {"range", "number"} or element.role in {"slider", "spinbutton"}


def _free_text(element: ElementFact) -> bool:
    if _numeric(element):
        return False
    if element.tag == "textarea":
        return True
    return element.input_type in _FREE or element.role in {"textbox", "searchbox"}


def _missing(form: FormFact, controls: list[ElementFact]) -> list[str]:
    if form.valid:
        return []
    missing: list[str] = []
    for element in controls:
        if element.validation_message:
            missing.append(field_name(element))
    return missing


def _is_control(element: ElementFact) -> bool:
    if element.tag == "option" or element.role == "option":
        return False
    if _is_submit(element):
        return False
    return element.tag in {"input", "select", "textarea"} or element.role in {
        "textbox",
        "searchbox",
        "combobox",
        "listbox",
        "checkbox",
        "radio",
        "switch",
        "slider",
        "spinbutton",
    }


def _form_enabled(form: FormFact, controls: list[ElementFact]) -> tuple[bool, str | None]:
    """No real submitter: the form, or every field, has to be usable."""
    if form.hidden or not form.visible:
        return False, "not visible"
    if form.inert or any(element.inert for element in controls):
        return False, "inert"
    fields = [element for element in controls if element.input_type not in {"reset", "button"}]
    if form.covered or (fields and all(element.covered for element in fields)):
        return False, "covered"
    if form.disabled:
        return False, "disabled"
    blocked = _unusable_fields(fields)
    if blocked:
        return False, blocked
    return True, None


def _unusable_fields(fields: list[ElementFact]) -> str | None:
    """No submitter: every hidden, disabled, or aria-disabled field blocks the form."""
    if not fields:
        return None
    first: str | None = None
    for element in fields:
        enabled, reason = element_enabled(element)
        if enabled:
            return None
        if first is None:
            first = reason or "disabled"
    return first


def _is_submit(element: ElementFact) -> bool:
    """Anything except type=button and type=reset submits, including an unknown type."""
    if element.tag == "button":
        return (element.input_type or "submit") not in {"button", "reset"}
    return element.input_type in {"submit", "image"}


def _is_search(
    form: FormFact, controls: list[ElementFact], properties: dict[str, dict[str, object]]
) -> bool:
    if any(element.role == "searchbox" or element.input_type == "search" for element in controls):
        return True
    return "query" in properties and form.method == "get"


def _form_slug(form: FormFact, controls: list[ElementFact]) -> str:
    if form.html_id:
        return slug(form.html_id)
    if controls:
        return slug(controls[0].landmark) or "form"
    return "form"
