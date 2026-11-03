from __future__ import annotations

from interface_compiler.mapping.form import fill_missing
from tests.mapping._find import one, props


def test_form_product(map_page) -> None:
    result, _facts = map_page("form_product.html")
    size = one(result, "set_size")
    assert props(size)["size"]["enum"] == ["S", "M", "L"]
    assert size.x is not None and size.x.grain == "field"
    added = one(result, "add_to_cart")
    assert added.input.model_dump(exclude_none=True) == {"type": "object", "properties": {}}
    assert added.enabled is False
    assert added.x is not None and added.x.reason == "missing: size"
    filled = fill_missing(result, {"size"})
    assert one(filled, "add_to_cart").enabled is True
