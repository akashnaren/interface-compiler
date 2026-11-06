from __future__ import annotations

from tests.mapping._find import one, props


def test_pagination(map_page) -> None:
    result, _facts = map_page("pagination.html")
    nxt = one(result, "next_page")
    prev = one(result, "prev_page")
    page = one(result, "go_page")
    assert nxt.enabled is True
    assert prev.enabled is False
    assert prev.x is not None and prev.x.reason == "aria-disabled"
    assert props(page)["page"] == {"type": "integer", "enum": [1, 2]}
    assert result.state["page"] == 1
