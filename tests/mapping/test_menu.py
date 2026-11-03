from __future__ import annotations

from tests.mapping._find import one


def test_menu(map_page) -> None:
    result, _facts = map_page("menu.html")
    sort_menu = one(result, "open_sort_menu")
    account = one(result, "open_account_menu")
    assert sort_menu.enabled is True
    assert account.enabled is True
    price = one(result, "do_price")
    name = one(result, "do_name")
    assert price.enabled is False and price.x is not None and price.x.reason == "menu closed"
    assert name.enabled is False and name.x is not None and name.x.reason == "menu closed"
    assert result.state["sort_menu_open"] is False
