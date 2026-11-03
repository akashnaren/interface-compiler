"""Lexicon, enabled, and schema rows. One table per rule."""

from __future__ import annotations

import pytest

from interface_compiler.browser.facts import Box, Constraints, ElementFact
from interface_compiler.extract.lexicon import Lexicon
from interface_compiler.extract.naming import field_name, slug
from interface_compiler.mapping.enabled import element_enabled
from interface_compiler.mapping.input_schema import property_for

_LEXICON = Lexicon()


def _element(**overrides: object) -> ElementFact:
    base: dict[str, object] = {
        "tag": "button",
        "role": "button",
        "name": "Go",
        "html_id": None,
        "field_name": None,
        "input_type": None,
        "href": None,
        "form_index": None,
        "form_method": None,
        "form_action": None,
        "disabled": False,
        "readonly": False,
        "aria_disabled": False,
        "inert": False,
        "hidden": False,
        "aria_hidden": False,
        "value": None,
        "checked": None,
        "selected": None,
        "options": (),
        "aria_expanded": None,
        "aria_selected": None,
        "aria_checked": None,
        "aria_pressed": None,
        "aria_current": None,
        "aria_valuemin": None,
        "aria_valuemax": None,
        "aria_valuenow": None,
        "aria_haspopup": None,
        "aria_controls": None,
        "box": Box(0, 0, 10, 10),
        "visible": True,
        "covered": False,
        "in_viewport": True,
        "validation_message": "",
        "landmark": "",
        "css": "button",
        "skeleton_path": "button|button",
        "label_text": "",
        "group_key": None,
        "constraints": Constraints(False, None, None, None, None, None, None),
        "name_source": "html",
        "in_dialog": False,
    }
    base.update(overrides)
    return ElementFact(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("label", "verb"),
    [
        ("Pay", "pay"),
        ("Place order", "place_order"),
        ("Delete", "delete"),
        ("Send", "send"),
        ("Add to bag", "add_to_cart"),
        ("Sign in", "sign_in"),
        ("Show more", "show_more"),
        ("Next", "next_page"),
        ("Previous", "prev_page"),
        ("Close", "close_dialog"),
        ("Search", "search"),
        ("Subscribe", "subscribe"),
        ("Filter", "filter"),
        ("Back", "go_back"),
        ("Download", "download"),
    ],
)
def test_lexicon_verbs(label: str, verb: str) -> None:
    assert _LEXICON.verb(label) == verb


@pytest.mark.parametrize(
    ("flag", "reason"),
    [
        ({"visible": False}, "not visible"),
        ({"disabled": True}, "disabled"),
        ({"aria_disabled": True}, "aria-disabled"),
        ({"inert": True}, "inert"),
        ({"covered": True}, "covered"),
        ({"readonly": True}, "read-only"),
    ],
)
def test_enabled_reasons(flag: dict[str, bool], reason: str) -> None:
    enabled, found = element_enabled(_element(**flag))
    assert enabled is False
    assert found == reason


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Catalog", "catalog"),
        ("Gift wrap", "gift_wrap"),
        ("9lives", "lives"),
        ("E-mail", "e_mail"),
    ],
)
def test_slug(text: str, expected: str) -> None:
    assert slug(text) == expected


@pytest.mark.parametrize(
    ("overrides", "prop"),
    [
        (
            {"tag": "input", "role": "textbox", "input_type": "email"},
            {"type": "string", "format": "email"},
        ),
        (
            {"tag": "input", "role": "textbox", "input_type": "url"},
            {"type": "string", "format": "uri"},
        ),
        (
            {
                "tag": "input",
                "role": "spinbutton",
                "input_type": "number",
                "constraints": Constraints(False, None, "1", "9", "1", None, None),
            },
            {"type": "integer", "minimum": 1, "maximum": 9, "multipleOf": 1},
        ),
        (
            {"tag": "input", "role": "textbox", "input_type": "date"},
            {"type": "string", "format": "date"},
        ),
        (
            {
                "tag": "input",
                "role": "textbox",
                "input_type": "text",
                "constraints": Constraints(False, "[A-Z]{3}", None, None, None, 3, 3),
            },
            {"type": "string", "pattern": "^(?:[A-Z]{3})$", "minLength": 3, "maxLength": 3},
        ),
    ],
)
def test_property_for(overrides: dict[str, object], prop: dict[str, object]) -> None:
    assert property_for(_element(**overrides)) == prop


def test_field_name_prefers_the_label() -> None:
    element = _element(label_text="Query", field_name="q")
    assert field_name(element) == "query"
