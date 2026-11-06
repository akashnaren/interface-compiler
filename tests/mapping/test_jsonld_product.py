from __future__ import annotations

from pathlib import Path

from interface_compiler.mapping.declared import jsonld_nodes, product_from_jsonld

_HTML = Path(__file__).resolve().parents[1] / "fixtures" / "html" / "jsonld_product.html"


def test_jsonld_product() -> None:
    node = jsonld_nodes(_HTML.read_text(encoding="utf-8"))[0]
    mapped = product_from_jsonld(node)
    assert mapped.view == "product"
    assert mapped.entities["product"]["id"] == "tee-navy"
    assert mapped.entities["product"]["name"] == "Navy Crew Tee"
    assert mapped.entities["product"]["price"] == 28
