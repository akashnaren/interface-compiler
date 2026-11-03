from __future__ import annotations

from tests.mapping._find import one


def test_dialog(map_page) -> None:
    result, _facts = map_page("dialog.html")
    outside = one(result, "do_outside")
    close = one(result, "close_dialog")
    assert outside.enabled is False
    assert outside.x is not None and outside.x.reason == "blocked by dialog"
    assert close.enabled is True
    assert result.state["dialog_open"] == "confirm"
