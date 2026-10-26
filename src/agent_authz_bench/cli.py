"""CLI entrypoint."""

from pathlib import Path

import typer

from agent_authz_bench.catalog.lint import lint_catalog_cli
from agent_authz_bench.tokens.keys import generate_test_keys

app = typer.Typer(help="agent-authz-bench CLI")
catalog_app = typer.Typer(help="Catalog commands")
keys_app = typer.Typer(help="Key commands")
app.add_typer(catalog_app, name="catalog")
app.add_typer(keys_app, name="keys")


@catalog_app.command("lint")
def catalog_lint(file: Path) -> None:
    """Lint a catalog file."""
    schema_path = Path("schema/catalog.schema.json")
    raise typer.Exit(code=lint_catalog_cli(file, schema_path))


@keys_app.command("generate")
def keys_generate(out: Path = Path(".keys")) -> None:
    """Generate test key material."""
    generate_test_keys(out)


if __name__ == "__main__":
    app()
