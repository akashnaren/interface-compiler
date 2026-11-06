from __future__ import annotations

from tests.mapping._find import one, props


def test_checkbox(map_page) -> None:
    result, _facts = map_page("checkbox.html")
    gift = one(result, "set_gift_wrap")
    assert props(gift)["gift_wrap"] == {"type": "boolean"}
    assert result.state["gift_wrap"] is False
    alerts = one(result, "set_alerts")
    assert props(alerts)["alerts"] == {"type": "boolean"}
    assert result.state["alerts"] is True
