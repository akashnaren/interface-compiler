from __future__ import annotations

from tests.mapping._find import one, props


def test_select(map_page) -> None:
    result, _facts = map_page("select.html")
    size = one(result, "set_size")
    assert props(size)["size"] == {"type": "string", "enum": ["S", "M", "L"]}
    tags = one(result, "set_tags")
    assert props(tags)["tags"]["type"] == "array"
    assert props(tags)["tags"]["items"] == {"type": "string", "enum": ["Red"]}
