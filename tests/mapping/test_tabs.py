from __future__ import annotations

from tests.mapping._find import one, props


def test_tabs(map_page) -> None:
    result, _facts = map_page("tabs.html")
    details = one(result, "open_details_tab")
    shipping = one(result, "open_shipping_tab")
    assert props(details)["tab"]["enum"] == ["Specs", "Reviews"]
    assert props(shipping)["tab"]["enum"] == ["Ground", "Air"]
    assert result.state["selected_details_tab"] == "Specs"
    assert result.state["selected_shipping_tab"] == "Ground"
