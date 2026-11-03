from __future__ import annotations

from interface_compiler.mapping.link import observe_page
from tests.mapping._find import one


def test_r4_fixed_page(map_page) -> None:
    result, _facts = map_page("link_group_long.html")
    one(result, "open_product")
    rows = result.entities["products"]
    assert len(rows) == 10
    assert [row["id"] for row in rows] == [str(index) for index in range(1, 11)]
    page = result.page["products"]
    assert page["offset"] == 0
    assert page["limit"] == 10
    assert page["total"] == 37
    assert page["next"]
    nxt = observe_page(result.catalog["products"], page["next"])
    assert [row["id"] for row in nxt] == [str(index) for index in range(11, 21)]
