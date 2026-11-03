"""Test configuration: a loopback fixture server and one browser per session."""

from __future__ import annotations

from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from playwright.sync_api import Page

from interface_compiler.browser.engine import Engine

_FIXTURES = Path(__file__).parent / "fixtures" / "html"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture(scope="session")
def fixture_base_url() -> Iterator[str]:
    handler = partial(_QuietHandler, directory=str(_FIXTURES))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.fixture(scope="session")
def browser_engine() -> Iterator[Engine]:
    engine = Engine()
    engine.start()
    try:
        yield engine
    finally:
        engine.close()


@pytest.fixture
def facts_page(browser_engine: Engine) -> Iterator[Page]:
    page = browser_engine.new_page()
    try:
        yield page
    finally:
        page.context.close()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run tests marked live against real public pages.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--live"):
        return
    skip_live = pytest.mark.skip(reason="live tests run only with --live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
