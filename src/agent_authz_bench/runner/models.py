"""Scenario and result models."""

from pydantic import BaseModel, ConfigDict


class StepResult(BaseModel):
    """Per-step observed result."""

    model_config = ConfigDict(extra="forbid")
    id: str
    expected: dict
    observed: dict
    ok: bool


class StateAssertionResult(BaseModel):
    """State assertion result."""

    model_config = ConfigDict(extra="forbid")
    path: str
    op: str
    value: object | None = None
    ok: bool


class ScenarioResult(BaseModel):
    """Scenario outcome entry."""

    model_config = ConfigDict(extra="forbid")
    id: str
    outcome: str
    steps: list[StepResult]
    state_assertions: list[StateAssertionResult]


class RunResult(BaseModel):
    """Full runner output."""

    model_config = ConfigDict(extra="forbid")
    tool_version: str
    label: str
    timestamp: str
    environment: dict
    scenarios: list[ScenarioResult]
    summary: dict | None = None
