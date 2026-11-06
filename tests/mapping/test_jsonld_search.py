from __future__ import annotations

from pathlib import Path

from interface_compiler.mapping.declared import jsonld_nodes, map_schema_org_action, prefer_declared
from interface_compiler.mapping.types import MapContext
from tests.mapping._find import one, props

_HTML = Path(__file__).resolve().parents[1] / "fixtures" / "html" / "jsonld_search.html"


def test_jsonld_search(map_page) -> None:
    result, facts = map_page("jsonld_search.html")
    node = jsonld_nodes(_HTML.read_text(encoding="utf-8"))[0]
    action = node["potentialAction"]
    assert isinstance(action, dict)
    declared = map_schema_org_action(action, MapContext(page_url=facts.url))
    merged = prefer_declared(result, [declared])
    search = one(merged, "search")
    assert search.x is not None and search.x.grain == "declared"
    assert props(search)["query"] == {"type": "string"}
    assert search.input.required == ["query"]
    assert [item.id for item in merged.affordances].count("search") == 1
