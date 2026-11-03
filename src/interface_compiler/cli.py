"""Command-line interface for interface-compiler."""

import typer

from interface_compiler import __version__

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
