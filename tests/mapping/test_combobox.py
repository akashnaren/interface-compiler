from __future__ import annotations

from tests.mapping._find import one, props


def test_combobox(map_page) -> None:
    result, _facts = map_page("combobox.html")
    city = one(result, "set_city")
    note = one(result, "set_note")
    assert props(city)["city"] == {"type": "string", "enum": ["Paris", "Rome"]}
    assert props(note)["note"] == {"type": "string"}
