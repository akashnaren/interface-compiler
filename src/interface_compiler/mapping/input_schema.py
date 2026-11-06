"""HTML constraints as one JSON Schema property."""

from __future__ import annotations

import re

from interface_compiler.browser.facts import ElementFact, OptionFact
from interface_compiler.extract.naming import field_name

_SOLD = re.compile(r"sold ?out|out of stock|unavailable|not available", re.IGNORECASE)
_FREE_TEXT = frozenset({"text", "search", "password", "tel", "email", "url", ""})


def _number(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _integral(value: str | None) -> bool:
    number = _number(value)
    if number is None:
        return value in {None, ""}
    return number.is_integer()


def _json_number(value: float) -> int | float:
    if value.is_integer():
        return int(value)
    return value


def enum_values(element: ElementFact) -> list[str]:
    """Enabled option labels. Colliding labels use the value attribute."""
    kept: list[tuple[str, str]] = []
    for index, option in enumerate(element.options):
        if _dropped(option, index == 0):
            continue
        kept.append((option.value, option.label.strip()))
    labels = [label for _value, label in kept]
    if len(labels) != len(set(labels)):
        return [value for value, _label in kept if value]
    return [label or value for value, label in kept]


def _dropped(option: OptionFact, first: bool) -> bool:
    if option.disabled:
        return True
    if first and option.value == "":
        return True
    return _SOLD.search(option.label) is not None


def property_for(element: ElementFact) -> dict[str, object] | None:
    """The schema property for one control, or None when it is not an argument."""
    kind = element.input_type or ""
    role = element.role
    if kind in {"file", "hidden", "submit", "reset", "image", "button"}:
        return None
    if role in {"slider", "spinbutton"} or kind in {"range", "number"}:
        return _numeric(element)
    if role in {"checkbox", "switch"} or kind == "checkbox":
        return {"type": "boolean"}
    if element.tag == "select" or role in {"listbox", "combobox"} and element.options:
        values = enum_values(element)
        if element.input_type == "select-multiple" or _multiple(element):
            return (
                {"type": "array", "items": {"type": "string", "enum": values}}
                if values
                else {
                    "type": "array",
                    "items": {"type": "string"},
                }
            )
        if values:
            return {"type": "string", "enum": values}
        return {"type": "string"}
    prop: dict[str, object] = {"type": "string"}
    if kind == "email":
        prop["format"] = "email"
    elif kind == "url":
        prop["format"] = "uri"
    elif kind == "tel":
        prop["format"] = "tel"
    elif kind == "date":
        prop["format"] = "date"
    elif kind == "time":
        prop["format"] = "time"
    elif kind == "datetime-local":
        prop["format"] = "date-time"
    _text_bounds(element, prop)
    return prop


def _multiple(element: ElementFact) -> bool:
    return element.role == "listbox" and element.tag == "select"


def _numeric(element: ElementFact) -> dict[str, object]:
    minimum = element.constraints.min or element.aria_valuemin
    maximum = element.constraints.max or element.aria_valuemax
    step = element.constraints.step
    integer = _integral(step) and _integral(minimum) and _integral(maximum)
    if step in {None, ""} and element.role == "slider":
        integer = _integral(minimum) and _integral(maximum)
    prop: dict[str, object] = {"type": "integer" if integer else "number"}
    low = _number(minimum)
    high = _number(maximum)
    if low is not None:
        prop["minimum"] = _json_number(low)
    if high is not None:
        prop["maximum"] = _json_number(high)
    stepped = _number(step)
    if stepped is not None and stepped > 0:
        prop["multipleOf"] = _json_number(stepped)
    return prop


def _text_bounds(element: ElementFact, prop: dict[str, object]) -> None:
    if element.constraints.pattern:
        prop["pattern"] = f"^(?:{element.constraints.pattern})$"
    if element.constraints.minlength is not None:
        prop["minLength"] = element.constraints.minlength
    if element.constraints.maxlength is not None:
        prop["maxLength"] = element.constraints.maxlength
    if element.input_type in _FREE_TEXT or element.tag == "textarea":
        return
    low = _number(element.constraints.min)
    high = _number(element.constraints.max)
    if low is not None:
        prop["minimum"] = _json_number(low)
    if high is not None:
        prop["maximum"] = _json_number(high)


def named_property(element: ElementFact) -> tuple[str, dict[str, object]] | None:
    prop = property_for(element)
    if prop is None:
        return None
    return field_name(element), prop
