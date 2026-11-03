from __future__ import annotations

import pytest

from interface_compiler.mapping.combobox import match_option
from tests.mapping._find import one, props


def _by_html_id(result, html_id: str):
    found = []
    for item in result.affordances:
        locator = item.x.locator if item.x else None
        extra = locator.model_extra if locator else None
        if extra and extra.get("html_id") == html_id:
            found.append(item)
    assert len(found) == 1, html_id
    return found[0]


def test_r3_closed_menu_is_free_text(map_page) -> None:
    result, _facts = map_page("menu_options.html")
    closed = _by_html_id(result, "sort")
    opened = _by_html_id(result, "sort-open")
    assert props(closed)["sort_by"] == {"type": "string"}
    assert props(opened)["sort_by"]["enum"] == ["Newest", "Price"]
    native = one(result, "set_size")
    assert "enum" in props(native)["size"]


@pytest.mark.parametrize(
    ("value", "status", "code", "matched"),
    [
        ("nope", "invalid_args", "no_such_option", None),
        ("pri", "ok", None, "Price"),
        ("PRICE", "ok", None, "Price"),
    ],
)
def test_r3_option_match(value: str, status: str, code: str | None, matched: str | None) -> None:
    found = match_option(value, ["Newest", "Price"])
    assert found.status == status
    assert found.code == code
    assert found.value == matched
