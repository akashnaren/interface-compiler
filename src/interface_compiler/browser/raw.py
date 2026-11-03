"""Playwright aria snapshot, the raw baseline for one page."""

from __future__ import annotations

from playwright.sync_api import Page


def raw_snapshot(page: Page) -> str:
    """Return the YAML aria snapshot of the page body."""
    return page.locator("body").aria_snapshot()
