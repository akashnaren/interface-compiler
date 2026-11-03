"""Playwright aria snapshot, the raw baseline for one page."""

from __future__ import annotations

from playwright.sync_api import Page

# Fact collection stops at 5s. A large table's aria snapshot needs longer.
# A renderer that is already spinning still ends when this timeout fires.
_RAW_TIMEOUT_MS = 30_000


def raw_snapshot(page: Page) -> str:
    """Return the YAML aria snapshot of the page body."""
    return page.locator("body").aria_snapshot(timeout=_RAW_TIMEOUT_MS)
