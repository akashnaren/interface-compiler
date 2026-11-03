from __future__ import annotations

from tests.mapping._find import one, props


def test_slider(map_page) -> None:
    result, _facts = map_page("slider.html")
    volume = one(result, "set_volume")
    zoom = one(result, "set_zoom")
    count = one(result, "set_count")
    assert props(volume)["volume"] == {
        "type": "integer",
        "minimum": 0,
        "maximum": 10,
        "multipleOf": 1,
    }
    assert props(zoom)["zoom"]["minimum"] == 0
    assert props(zoom)["zoom"]["maximum"] == 100
    assert props(count)["count"]["multipleOf"] == 0.5
    assert result.state["volume"] == 3
    assert result.state["zoom"] == 40
    assert result.state["count"] == 1
