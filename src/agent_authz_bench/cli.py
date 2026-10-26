"""CLI entrypoint."""

import shutil
from pathlib import Path

import typer

from agent_authz_bench.catalog.lint import lint_catalog_cli
from agent_authz_bench.config.env import load_user_input_config
from agent_authz_bench.runner.executor import execute_suite
from agent_authz_bench.runner.providers import EnvTokenProvider
from agent_authz_bench.runner.report import generate_report

app = typer.Typer(help="agent-authz-bench CLI")
catalog_app = typer.Typer(help="Catalog commands")
env_app = typer.Typer(help="Environment commands")
app.add_typer(catalog_app, name="catalog")
app.add_typer(env_app, name="env")


@catalog_app.command("lint")
def catalog_lint(file: Path) -> None:
    """Lint a catalog file."""
    schema_path = Path("schema/catalog.schema.json")
    raise typer.Exit(code=lint_catalog_cli(file, schema_path))


@env_app.command("init")
def env_init(out: Path = Path(".env")) -> None:
    """Create a .env file from .env.example if one does not exist."""
    if out.exists():
        print(f"{out} already exists.")  # noqa: T201
        return
    shutil.copyfile(".env.example", out)
    print(f"Created {out} from .env.example")  # noqa: T201


@app.command("run")
def run_scenarios(
    target: str | None = None,
    backend: str | None = None,
    admin_key: str = "test-admin-key",
    scenarios: Path = Path("scenarios"),
    label: str = "reference",
    out: Path = Path("reports/reference.json"),
    only: str = "",
) -> None:
    """Run authorization scenarios against a target gateway."""
    config = load_user_input_config()
    selected = {item.strip() for item in only.split(",") if item.strip()} or None
    execute_suite(
        target=target or config.target_gateway_url,
        backend=backend or config.backend_url,
        admin_key=admin_key,
        scenarios_dir=scenarios,
        label=label,
        out=out,
        only=selected,
        token_provider=EnvTokenProvider(config),
    )


@app.command("report")
def report(
    weak: Path = Path("reports/weak.json"),
    reference: Path = Path("reports/reference.json"),
    out: Path = Path("reports/matrix.md"),
    scenarios: Path = Path("scenarios"),
) -> None:
    """Generate scenario matrix report from weak/reference runs."""
    print(generate_report(weak, reference, out, scenarios_dir=scenarios))  # noqa: T201


if __name__ == "__main__":
    app()
