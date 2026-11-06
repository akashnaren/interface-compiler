from __future__ import annotations

from tests.mapping._find import one


def test_disclosure(map_page) -> None:
    result, _facts = map_page("disclosure.html")
    description = one(result, "toggle_description")
    fabric = one(result, "toggle_fabric")
    assert description.enabled is True
    assert result.state["description_expanded"] is False
    assert result.state["fabric_expanded"] is False
    assert fabric.x is not None and fabric.x.grain == "single"
