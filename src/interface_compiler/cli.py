"""Command-line interface for interface-compiler."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from interface_compiler import __version__
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
    if not isinstance(data, dict):
        typer.echo("document must be a JSON object", err=True)
        raise typer.Exit(1)
    try:
        validate_doc(data)
    except ContractError as exc:
        for line in exc.errors:
            typer.echo(line, err=True)
        raise typer.Exit(1) from exc
    except RecursionError as exc:
        typer.echo(nesting_too_deep("document"), err=True)
        raise typer.Exit(1) from exc
    typer.echo("valid")
