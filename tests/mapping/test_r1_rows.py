from __future__ import annotations

import pytest

from tests.mapping._find import one


@pytest.mark.parametrize("include", [(), ("story.comments",)])
def test_r1_secondary_links(map_page, include: tuple[str, ...]) -> None:
    result, _facts = map_page("link_group_rows.html", include_secondary=include)
    one(result, "open_story")
    comments = [item for item in result.affordances if item.id == "open_story_comments"]
    assert bool(comments) is bool(include)
    if comments:
        assert comments[0].input.required == ["story_id"]


def test_r1_carousels_merge(map_page) -> None:
    result, _facts = map_page("link_group_rows.html")
    rows = result.catalog["items"]
    ids = [row["id"] for row in rows]
    assert "featured-1" in ids
    assert "latest-3" in ids
    assert len([item for item in result.affordances if item.id == "open_item"]) == 1
    assert "open_story_comments" not in {item.id for item in result.affordances}
