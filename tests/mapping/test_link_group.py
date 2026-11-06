from __future__ import annotations

from tests.mapping._find import one, props


def test_link_group(map_page) -> None:
    result, _facts = map_page("link_group.html")
    opened = one(result, "open_product")
    assert opened.enabled is True
    assert props(opened) == {"product_id": {"type": "string"}}
    assert opened.input.required == ["product_id"]
    assert opened.x is not None and opened.x.grain == "collapsed"
    ids = [row["id"] for row in result.entities["products"]]
    assert ids == [
        "tee-navy",
        "tee-white",
        "hoodie-grey",
        "cap-black",
        "scarf-wool",
        "tote-canvas",
        "belt-leather",
        "tie-silk",
    ]


def test_link_group_shuffled_keeps_the_signature(map_page) -> None:
    original, _facts = map_page("link_group.html")
    shuffled, _other = map_page("link_group_shuffled.html")
    left = one(original, "open_product")
    right = one(shuffled, "open_product")
    assert left.id == right.id
    assert left.x is not None and right.x is not None
    assert left.x.signature == right.x.signature
    assert {row["id"] for row in original.catalog["products"]} == {
        row["id"] for row in shuffled.catalog["products"]
    }
