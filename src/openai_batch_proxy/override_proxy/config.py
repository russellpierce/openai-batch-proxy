from typing import Any, Literal

from pydantic import BaseModel, Field


class OverrideField(BaseModel):
    """A single field override."""

    value: Any
    mode: Literal["force", "default"] = "force"


class OverridesConfig(BaseModel):
    """Override maps for body, headers, and query."""

    body: dict[str, OverrideField] = Field(default_factory=dict)
    headers: dict[str, OverrideField] = Field(default_factory=dict)
    query: dict[str, OverrideField] = Field(default_factory=dict)


class RouteConfig(BaseModel):
    """Per-path route configuration."""

    mode: Literal["passthrough", "batch_proxy"] = "passthrough"
    overrides: OverridesConfig = Field(default_factory=OverridesConfig)
