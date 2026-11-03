from __future__ import annotations

import pytest

from tests.mapping._find import one


@pytest.mark.parametrize(
    ("html_id", "affordance_id", "enabled", "reason"),
    [
        ("cart", "go_cart", True, None),
        ("catalog", "go_catalog", True, None),
        ("section", "go_details", True, None),
        ("secret", "go_secret", False, "not visible"),
    ],
)
def test_link(
    map_page, html_id: str, affordance_id: str, enabled: bool, reason: str | None
) -> None:
    result, facts = map_page("link.html")
    element = next(item for item in facts.elements if item.html_id == html_id)
    mapped = one(result, affordance_id)
    assert mapped.enabled is enabled
    assert (mapped.x.reason if mapped.x else None) == reason
    assert mapped.input.model_dump(exclude_none=True) == {"type": "object", "properties": {}}
    assert element.html_id == html_id
