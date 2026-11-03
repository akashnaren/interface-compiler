from __future__ import annotations

import pytest

from tests.mapping._find import one


@pytest.mark.parametrize(
    ("html_id", "affordance_id", "enabled", "reason", "tag"),
    [
        ("add", "add_to_cart", True, None, "mutating"),
        ("more", "show_more", True, None, "safe"),
        ("off", "do_unavailable", False, "disabled", "mutating"),
        ("aria", "do_wait", False, "aria-disabled", "mutating"),
        ("under", "do_under", False, "covered", "mutating"),
    ],
)
def test_button(mapped_once, html_id, affordance_id, enabled, reason, tag) -> None:
    result, _facts = mapped_once("button.html")
    mapped = one(result, affordance_id)
    assert mapped.enabled is enabled
    assert (mapped.x.reason if mapped.x else None) == reason
    assert mapped.x is not None and mapped.x.tag == tag


def test_button_pressed_state(mapped_once) -> None:
    result, _facts = mapped_once("button.html")
    mapped = one(result, "filter")
    assert mapped.x is not None and mapped.x.tag == "safe"
    assert result.state["filter"] is True
