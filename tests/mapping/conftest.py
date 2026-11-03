"""Load a fixture page and map it."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from playwright.sync_api import Page

from interface_compiler.browser.facts import PageFacts, collect_facts
from interface_compiler.mapping import MapContext, MapResult, map_facts


@pytest.fixture
def map_page(facts_page: Page, fixture_base_url: str) -> Callable[..., tuple[MapResult, PageFacts]]:
    def load(name: str, **kwargs: object) -> tuple[MapResult, PageFacts]:
        facts_page.goto(f"{fixture_base_url}/{name}", wait_until="domcontentloaded", timeout=15_000)
        facts = collect_facts(facts_page)
        context = MapContext(page_url=facts.url, **kwargs)  # type: ignore[arg-type]
        return map_facts(facts, context), facts

    return load
