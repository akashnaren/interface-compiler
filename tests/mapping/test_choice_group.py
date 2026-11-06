from __future__ import annotations

from tests.mapping._find import one, props


def test_choice_group(map_page) -> None:
    result, _facts = map_page("choice_group.html")
    size = one(result, "set_size")
    assert props(size)["size"]["enum"] == ["S", "M", "L"]
    assert result.state["selected_size"] == "M"
    color = one(result, "set_color")
    assert props(color)["color"]["enum"] == ["Red", "Blue"]
    assert result.state["selected_color"] == "Red"
