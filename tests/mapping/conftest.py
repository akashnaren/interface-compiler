"""Load a fixture page and map it."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from playwright.sync_api import Page

from interface_compiler.browser.engine import Engine
from interface_compiler.browser.facts import PageFacts, collect_facts
from interface_compiler.mapping import MapContext, MapResult, map_facts


def _load(page: Page, base: str, name: str, **kwargs: object) -> tuple[MapResult, PageFacts]:
    page.goto(f"{base}/{name}", wait_until="domcontentloaded", timeout=15_000)
    facts = collect_facts(page)
    context = MapContext(page_url=facts.url, **kwargs)  # type: ignore[arg-type]
    return map_facts(facts, context), facts


@pytest.fixture
def map_page(facts_page: Page, fixture_base_url: str) -> Callable[..., tuple[MapResult, PageFacts]]:
    def load(name: str, **kwargs: object) -> tuple[MapResult, PageFacts]:
        return _load(facts_page, fixture_base_url, name, **kwargs)

    return load


@pytest.fixture(scope="module")
def mapped_once(
    browser_engine: Engine, fixture_base_url: str
) -> Callable[..., tuple[MapResult, PageFacts]]:
    """One browser load per fixture for a whole test module."""
    cache: dict[tuple[object, ...], tuple[MapResult, PageFacts]] = {}

    def load(name: str, **kwargs: object) -> tuple[MapResult, PageFacts]:
        key = (name, tuple(sorted(kwargs.items())))
        if key not in cache:
            page = browser_engine.new_page()
            try:
                cache[key] = _load(page, fixture_base_url, name, **kwargs)
            finally:
                page.context.close()
        return cache[key]

    return load
