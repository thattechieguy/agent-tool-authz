"""CLI entrypoint."""

import typer

app = typer.Typer(help="agent-authz-bench CLI")


if __name__ == "__main__":
    app()
