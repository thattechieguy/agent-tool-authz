"""Catalog data models."""

from pydantic import BaseModel, ConfigDict, Field


class CatalogService(BaseModel):
    """Metadata for a catalog service."""

    model_config = ConfigDict(extra="forbid")
    name: str
    description: str | None = None


class CatalogOperation(BaseModel):
    """HTTP operation bound to a tool."""

    model_config = ConfigDict(extra="forbid")
    method: str
    path: str


class CatalogSideEffects(BaseModel):
    """Describes state, hidden and external side effects."""

    model_config = ConfigDict(extra="forbid")
    state_change: bool
    hidden: list[str] = Field(default_factory=list)
    external: list[str] = Field(default_factory=list)


class CatalogRateLimit(BaseModel):
    """Rate-limit policy for a tool."""

    model_config = ConfigDict(extra="forbid")
    calls: int
    period_seconds: int
    key: str = "run"


class CatalogTool(BaseModel):
    """A single tool entry in the risk catalog."""

    model_config = ConfigDict(extra="forbid")
    id: str
    description: str | None = None
    operation: CatalogOperation
    risk_tier: int
    side_effects: CatalogSideEffects
    reversibility: str
    idempotent: bool | None = None
    required_scope: str
    required_user_roles: list[str]
    backend_identity: str
    approval: str
    rate_limit: CatalogRateLimit | None = None
    data_classes: list[str] = Field(default_factory=list)
    notes: str | None = None


class ToolCatalog(BaseModel):
    """Root catalog object."""

    model_config = ConfigDict(extra="forbid")
    catalog_version: str
    service: CatalogService
    tools: list[CatalogTool]
