from __future__ import annotations

from tests.mapping._find import one, props


def test_text_inputs(map_page) -> None:
    result, _facts = map_page("text_inputs.html")
    form = one(result, "submit_fields")
    assert form.x is not None and form.x.grain == "form"
    assert props(form) == {
        "email": {"type": "string", "format": "email"},
        "site": {"type": "string", "format": "uri"},
        "qty": {"type": "integer", "minimum": 1, "maximum": 9, "multipleOf": 1},
        "when": {"type": "string", "format": "date"},
        "phone": {"type": "string", "format": "tel"},
        "code": {"type": "string", "pattern": "^(?:[A-Z]{3})$", "minLength": 3, "maxLength": 3},
        "note": {"type": "string"},
        "lock": {"type": "string"},
    }
