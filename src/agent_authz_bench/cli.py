"""CLI entrypoint."""

from pathlib import Path

import typer

from agent_authz_bench.catalog.lint import lint_catalog_cli
from agent_authz_bench.runner.executor import execute_suite
from agent_authz_bench.runner.providers import DefaultTokenProvider
from agent_authz_bench.runner.report import generate_report
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


@app.command("run")
def run_scenarios(
    target: str = "http://127.0.0.1:8080",
    backend: str = "http://127.0.0.1:9000",
    admin_key: str = "test-admin-key",
    scenarios: Path = Path("scenarios"),
    label: str = "reference",
    out: Path = Path("reports/reference.json"),
    only: str = "",
) -> None:
    """Run authorization scenarios against a target gateway."""
    selected = {item.strip() for item in only.split(",") if item.strip()} or None
    execute_suite(
        target=target,
        backend=backend,
        admin_key=admin_key,
        scenarios_dir=scenarios,
        label=label,
        out=out,
        only=selected,
        token_provider=DefaultTokenProvider(),
    )


@app.command("report")
def report(
    weak: Path = Path("reports/weak.json"),
    reference: Path = Path("reports/reference.json"),
    out: Path = Path("reports/matrix.md"),
) -> None:
    """Generate scenario matrix report from weak/reference runs."""
    print(generate_report(weak, reference, out))  # noqa: T201


if __name__ == "__main__":
    app()
