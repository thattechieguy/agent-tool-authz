"""CLI entrypoint."""

import json
import os
import shutil
from pathlib import Path

import typer

from agent_authz_bench.accelerator.apim import (
    discover_identity,
    drift_check,
    scaffold_from_discovery,
)
from agent_authz_bench.catalog.lint import lint_catalog_cli
from agent_authz_bench.config.env import load_user_input_config
from agent_authz_bench.runner.executor import execute_suite
from agent_authz_bench.runner.providers import load_token_provider
from agent_authz_bench.runner.report import generate_report

app = typer.Typer(help="agent-authz-bench CLI")
catalog_app = typer.Typer(help="Catalog commands")
env_app = typer.Typer(help="Environment commands")
apim_app = typer.Typer(help="APIM accelerator commands")
app.add_typer(catalog_app, name="catalog")
app.add_typer(env_app, name="env")
app.add_typer(apim_app, name="apim")


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


@apim_app.command("discover")
def apim_discover(
    api_app_id: str = "",
    caller_app_id: str = "",
    tenant_id: str = "",
    openapi: Path = Path("examples/apim/loans-backend-openapi.json"),
    out: Path = Path("examples/apim/generated/discovery.json"),
) -> None:
    """Discover app roles/scopes and OpenAPI operations for APIM policy scaffolding."""
    config = load_user_input_config()
    resolved_api_app_id = api_app_id or config.app_registration_client_id
    resolved_caller_app_id = caller_app_id or config.caller_app_registration_client_id
    resolved_tenant_id = tenant_id or config.tenant_id
    if not resolved_api_app_id or not resolved_caller_app_id or not resolved_tenant_id:
        raise typer.BadParameter(
            "api_app_id, caller_app_id, and tenant_id are required (flags or .env values)."
        )
    discovery = discover_identity(
        api_app_id=resolved_api_app_id,
        caller_app_id=resolved_caller_app_id,
        tenant_id=resolved_tenant_id,
        openapi_path=openapi,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(discovery, indent=2), encoding="utf-8")
    print(f"Wrote {out}")  # noqa: T201


@apim_app.command("scaffold")
def apim_scaffold(
    discovery: Path = Path("examples/apim/generated/discovery.json"),
    policy_out: Path = Path("examples/apim/generated/inbound-policy.generated.xml"),
    mapping_out: Path = Path("examples/apim/generated/operation-mapping.generated.yaml"),
) -> None:
    """Generate APIM inbound policy XML and operation mapping from discovery output."""
    scaffold_from_discovery(
        discovery_path=discovery,
        policy_out=policy_out,
        mapping_out=mapping_out,
    )
    print(f"Wrote {policy_out}")  # noqa: T201
    print(f"Wrote {mapping_out}")  # noqa: T201


@apim_app.command("drift-check")
def apim_drift_check(
    discovery: Path = Path("examples/apim/generated/discovery.json"),
    policy: Path = Path("examples/apim/generated/inbound-policy.generated.xml"),
    mapping: Path = Path("examples/apim/generated/operation-mapping.generated.yaml"),
) -> None:
    """Fail if APIM scaffold artifacts drift from discovery metadata."""
    ok, message = drift_check(discovery_path=discovery, policy_path=policy, mapping_path=mapping)
    if ok:
        print(message)  # noqa: T201
        return
    print(message)  # noqa: T201
    raise typer.Exit(code=1)


@app.command("run")
def run_scenarios(
    target: str | None = None,
    backend: str | None = None,
    admin_key: str = "test-admin-key",
    scenarios: Path = Path("scenarios"),
    label: str = "reference",
    out: Path = Path("reports/reference.json"),
    only: str = "",
    token_provider: str = "",
) -> None:
    """Run authorization scenarios against a target gateway."""
    config = load_user_input_config()
    selected = {item.strip() for item in only.split(",") if item.strip()} or None
    provider_spec = token_provider or os.environ.get("AAB_TOKEN_PROVIDER")
    try:
        provider = load_token_provider(provider_spec, config)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--token-provider") from exc
    execute_suite(
        target=target or config.target_gateway_url,
        backend=backend or config.backend_url,
        admin_key=admin_key,
        scenarios_dir=scenarios,
        label=label,
        out=out,
        only=selected,
        token_provider=provider,
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
