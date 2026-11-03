"""Test configuration. The fixture server and browser are added in a later milestone."""

import pytest


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
