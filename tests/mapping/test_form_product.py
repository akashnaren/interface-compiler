from __future__ import annotations

from dataclasses import replace

from interface_compiler.mapping.form import fill_missing
from tests.mapping._find import one, props


def test_form_product(map_page) -> None:
    result, facts = map_page("form_product.html")
    size = one(result, "set_size")
    assert props(size)["size"]["enum"] == ["S", "M", "L"]
    assert size.x is not None and size.x.grain == "field"
    added = one(result, "add_to_cart")
    assert added.input.model_dump(exclude_none=True) == {"type": "object", "properties": {}}
    assert added.enabled is False
    assert added.x is not None and added.x.reason == "missing: size"
    submit = next(element for element in facts.elements if element.html_id == "add")
    filled = fill_missing(result, {"size"}, submit)
    assert one(filled, "add_to_cart").enabled is True
    again = one(filled, "add_to_cart")
    again.enabled = False
    if again.x is not None:
        again.x.reason = "missing: size"
    fill_missing(filled, {"size"}, replace(submit, disabled=True))
    checked = one(filled, "add_to_cart")
    assert checked.enabled is False
    assert checked.x is not None and checked.x.reason == "disabled"
