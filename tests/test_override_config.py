"""Tests for override config models."""

import pytest
from pydantic import ValidationError

from openai_batch_proxy.override_proxy.config import (
    OverrideField,
    OverridesConfig,
    RouteConfig,
)


class TestOverrideField:
    """Tests for OverrideField model."""

    def test_defaults_to_force_mode(self) -> None:
        """OverrideField should default to force mode."""
        field = OverrideField(value="test")
        assert field.mode == "force"

    def test_explicit_force_mode(self) -> None:
        """OverrideField should accept explicit force mode."""
        field = OverrideField(value="test", mode="force")
        assert field.mode == "force"

    def test_default_mode(self) -> None:
        """OverrideField should accept default mode."""
        field = OverrideField(value="test", mode="default")
        assert field.mode == "default"

    def test_invalid_mode_rejected(self) -> None:
        """OverrideField should reject invalid mode values."""
        with pytest.raises(ValidationError):
            OverrideField(value="test", mode="invalid")  # type: ignore[arg-type]

    def test_supports_various_value_types(self) -> None:
        """OverrideField should support various value types."""
        assert OverrideField(value="string").value == "string"
        assert OverrideField(value=42).value == 42
        assert OverrideField(value=3.14).value == 3.14
        assert OverrideField(value=True).value is True
        assert OverrideField(value=None).value is None
        assert OverrideField(value=["list"]).value == ["list"]
        assert OverrideField(value={"dict": "value"}).value == {"dict": "value"}


class TestOverridesConfig:
    """Tests for OverridesConfig model."""

    def test_defaults_to_empty_dicts(self) -> None:
        """OverridesConfig should default to empty dicts."""
        config = OverridesConfig()
        assert config.body == {}
        assert config.headers == {}
        assert config.query == {}

    def test_accepts_body_overrides(self) -> None:
        """OverridesConfig should accept body overrides."""
        config = OverridesConfig(
            body={"model": OverrideField(value="gpt-4")}
        )
        assert "model" in config.body
        assert config.body["model"].value == "gpt-4"

    def test_accepts_header_overrides(self) -> None:
        """OverridesConfig should accept header overrides."""
        config = OverridesConfig(
            headers={"x-custom": OverrideField(value="value")}
        )
        assert "x-custom" in config.headers

    def test_accepts_query_overrides(self) -> None:
        """OverridesConfig should accept query overrides."""
        config = OverridesConfig(
            query={"param": OverrideField(value="value")}
        )
        assert "param" in config.query


class TestRouteConfig:
    """Tests for RouteConfig model."""

    def test_defaults_to_passthrough_mode(self) -> None:
        """RouteConfig should default to passthrough mode."""
        config = RouteConfig()
        assert config.mode == "passthrough"

    def test_with_mode_only(self) -> None:
        """RouteConfig should accept mode only."""
        config = RouteConfig(mode="batch_proxy")
        assert config.mode == "batch_proxy"
        assert config.overrides.body == {}

    def test_with_overrides_only(self) -> None:
        """RouteConfig with only overrides should default to passthrough mode."""
        config = RouteConfig(
            overrides=OverridesConfig(
                body={"model": OverrideField(value="gpt-4")}
            )
        )
        assert config.mode == "passthrough"
        assert "model" in config.overrides.body

    def test_with_mode_and_overrides(self) -> None:
        """RouteConfig should accept both mode and overrides."""
        config = RouteConfig(
            mode="batch_proxy",
            overrides=OverridesConfig(
                body={"model": OverrideField(value="custom-model")}
            ),
        )
        assert config.mode == "batch_proxy"
        assert config.overrides.body["model"].value == "custom-model"

    def test_valid_modes(self) -> None:
        """RouteConfig should accept all valid mode values."""
        assert RouteConfig(mode="passthrough").mode == "passthrough"
        assert RouteConfig(mode="batch_proxy").mode == "batch_proxy"

    def test_invalid_mode_rejected(self) -> None:
        """RouteConfig should reject invalid mode values."""
        with pytest.raises(ValidationError):
            RouteConfig(mode="invalid_mode")  # type: ignore[arg-type]
