from __future__ import annotations

from tests.mapping._find import one, props


def test_form_search(map_page) -> None:
    result, _facts = map_page("form_search.html")
    search = one(result, "search")
    assert props(search) == {"query": {"type": "string"}}
    assert search.x is not None
    assert search.x.grain == "form"
    assert search.x.tag == "safe"
