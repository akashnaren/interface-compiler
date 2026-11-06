from __future__ import annotations

from interface_compiler.mapping import MapContext, map_webmcp_tool
from tests.mapping._find import one


def test_webmcp() -> None:
    tool = {
        "name": "run_tool",
        "description": "Run the sample tool",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": False},
    }
    mapped = map_webmcp_tool(tool, MapContext(page_url="http://127.0.0.1/tool"))
    action = one(mapped, "run_tool")
    assert action.x is not None
    assert action.x.tag == "mutating"
    assert action.x.grain == "declared"
    assert action.input.model_dump(exclude_none=True) == {"type": "object", "properties": {}}
