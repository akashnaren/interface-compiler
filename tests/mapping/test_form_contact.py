from __future__ import annotations

from tests.mapping._find import one


def test_form_contact(map_page) -> None:
    result, _facts = map_page("form_contact.html")
    send = one(result, "send")
    assert send.input.required == ["email", "message"]
    assert send.x is not None and send.x.tag == "mutating"
    assert send.enabled is False
    assert send.x.reason == "hard-blocked in v1: send"
