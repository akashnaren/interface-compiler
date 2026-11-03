"""Command-line interface for interface-compiler."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from playwright.sync_api import Error as PlaywrightError

from interface_compiler import __version__
from interface_compiler.browser.engine import Engine
from interface_compiler.browser.raw import raw_snapshot
from interface_compiler.contract.validate import (
    ContractError,
    UnknownSchemaError,
    nesting_too_deep,
    schema_text,
    validate_doc,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Compile any website into an agent-usable interface with typed, checked actions.",
)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"interface-compiler {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_print_version,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Compile any website into an agent-usable interface with typed, checked actions."""


@app.command("schema")
def schema_command(
    name: Annotated[str, typer.Argument(help="Schema to print: view-doc or effect.")] = "view-doc",
) -> None:
    """Print a frozen JSON Schema."""
    try:
        text = schema_text(name)
    except UnknownSchemaError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    sys.stdout.write(text if text.endswith("\n") else f"{text}\n")


@app.command("validate")
def validate_command(
    path: Annotated[Path, typer.Argument(help="Compiled view document JSON file.")],
) -> None:
    """Validate a compiled view document. Prints ``valid`` and exits 0 on success."""
    if not path.is_file():
        typer.echo(f"file not found: {path}", err=True)
        raise typer.Exit(2)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        typer.echo(f"invalid JSON: {exc}", err=True)
        raise typer.Exit(1) from exc
    except ValueError as exc:
        # json.loads raises ValueError, not JSONDecodeError, when an integer
        # has more than 4300 digits.
        typer.echo(f"document: {exc}", err=True)
        raise typer.Exit(1) from exc
    if not isinstance(data, dict):
        typer.echo("document must be a JSON object", err=True)
        raise typer.Exit(1)
    try:
        validate_doc(data)
    except ContractError as exc:
        _echo_contract_errors(exc.errors)
        raise typer.Exit(1) from exc
    except RecursionError as exc:
        typer.echo(nesting_too_deep("document"), err=True)
        raise typer.Exit(1) from exc
    typer.echo("valid")


_MAX_CLI_ERRORS = 20
_MAX_CLI_ERROR_CHARS = 4000


def _echo_contract_errors(errors: list[str]) -> None:
    """Print contract errors, stopping after a bounded number and size."""
    shown = 0
    used = 0
    for line in errors:
        if shown >= _MAX_CLI_ERRORS or used + len(line) > _MAX_CLI_ERROR_CHARS:
            break
        typer.echo(line, err=True)
        shown += 1
        used += len(line) + 1
    remaining = len(errors) - shown
    if remaining:
        typer.echo(f"{remaining} more errors omitted", err=True)


def _raw_url_allowed(url: str, *, local_fixture: bool) -> bool:
    """http and https only, plus file when the local-fixture flag is set."""
    if url == "" or _forbidden_raw_char(url):
        return False
    scheme, separator, _rest = url.partition("://")
    if separator != "://":
        return False
    lowered = scheme.lower()
    if lowered in {"http", "https"}:
        return True
    return local_fixture and lowered == "file"


def _forbidden_raw_char(url: str) -> bool:
    for char in url:
        if char == "\\" or char.isspace() or ord(char) < 32 or ord(char) == 127:
            return True
    return False


def _short_playwright_error(exc: PlaywrightError) -> str:
    text = str(exc).splitlines()[0] if str(exc) else "page load failed"
    if len(text) > 200:
        return f"{text[:199]}…"
    return text


@app.command("raw")
def raw_command(
    url: Annotated[str, typer.Argument(help="Page to snapshot.")],
    local_fixture: Annotated[
        bool,
        typer.Option(
            "--local-fixture",
            help="Allow a file URL for a local fixture page.",
        ),
    ] = False,
) -> None:
    """Print the Playwright aria snapshot for a URL.

    The browser is closed before this process exits. Leaving Chromium running
    would keep the command from finishing. Only http and https URLs are
    fetched. ``--local-fixture`` also allows a file URL.
    """
    if not _raw_url_allowed(url, local_fixture=local_fixture):
        if local_fixture:
            typer.echo("raw accepts only an http, https, or file URL", err=True)
        else:
            typer.echo("raw accepts only an http or https URL", err=True)
        raise typer.Exit(2)
    engine = Engine()
    page = None
    try:
        engine.start()
        page = engine.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        text = raw_snapshot(page)
    except PlaywrightError as exc:
        typer.echo(_short_playwright_error(exc), err=True)
        raise typer.Exit(1) from exc
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    finally:
        try:
            if page is not None:
                page.context.close()
        finally:
            engine.close()
    sys.stdout.write(text if text.endswith("\n") else f"{text}\n")
