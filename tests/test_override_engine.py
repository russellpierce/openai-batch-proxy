"""Tests for the override engine."""

import pytest

from openai_batch_proxy.override_proxy.config import OverrideField, OverridesConfig
from openai_batch_proxy.override_proxy.engine import apply_overrides


class TestForceOverrides:
    """Tests for force mode overrides."""

    def test_force_overrides_existing_value(self) -> None:
        """Force mode should override existing values."""
        overrides = OverridesConfig(
            body={"model": OverrideField(value="gpt-4", mode="force")}
        )
        body = {"model": "gpt-3.5", "messages": []}

        new_body, _, _ = apply_overrides(overrides, body, {}, {})

        assert new_body["model"] == "gpt-4"
        assert new_body["messages"] == []  # other keys preserved


class TestDefaultOverrides:
    """Tests for default mode overrides."""

    def test_default_preserves_existing_value(self) -> None:
        """Default mode should not override existing values."""
        overrides = OverridesConfig(
            body={"model": OverrideField(value="gpt-4", mode="default")}
        )
        body = {"model": "gpt-3.5"}

        new_body, _, _ = apply_overrides(overrides, body, {}, {})

        assert new_body["model"] == "gpt-3.5"

    def test_default_sets_missing_value(self) -> None:
        """Default mode should set missing values."""
        overrides = OverridesConfig(
            body={"temperature": OverrideField(value=0.7, mode="default")}
        )
        body = {"model": "gpt-4"}

        new_body, _, _ = apply_overrides(overrides, body, {}, {})

        assert new_body["temperature"] == 0.7
        assert new_body["model"] == "gpt-4"


class TestDotNotation:
    """Tests for dot-notation nested overrides."""

    def test_dot_notation_creates_nested_dicts(self) -> None:
        """Dot notation should create intermediate dicts."""
        overrides = OverridesConfig(
            body={"reasoning.effort": OverrideField(value="low", mode="force")}
        )
        body = {"model": "gpt-4"}

        new_body, _, _ = apply_overrides(overrides, body, {}, {})

        assert new_body["reasoning"]["effort"] == "low"
        assert new_body["model"] == "gpt-4"

    def test_dot_notation_existing_parent(self) -> None:
        """Dot notation should work with existing parent dicts."""
        overrides = OverridesConfig(
            body={"reasoning.effort": OverrideField(value="high", mode="force")}
        )
        body = {"reasoning": {"summary": "test"}}

        new_body, _, _ = apply_overrides(overrides, body, {}, {})

        assert new_body["reasoning"]["effort"] == "high"
        assert new_body["reasoning"]["summary"] == "test"

    def test_dot_notation_default_with_existing_nondict(self) -> None:
        """Default mode should skip when intermediate path exists but is not a dict."""
        overrides = OverridesConfig(
            body={"reasoning.effort": OverrideField(value="low", mode="default")}
        )
        body = {"reasoning": "not-a-dict"}

        new_body, _, _ = apply_overrides(overrides, body, {}, {})

        # Should not modify because reasoning exists and isn't a dict
        assert new_body["reasoning"] == "not-a-dict"

    def test_dot_notation_deeply_nested(self) -> None:
        """Dot notation should work with deeply nested paths."""
        overrides = OverridesConfig(
            body={"a.b.c.d": OverrideField(value="deep", mode="force")}
        )
        body = {}

        new_body, _, _ = apply_overrides(overrides, body, {}, {})

        assert new_body["a"]["b"]["c"]["d"] == "deep"


class TestHeaderOverrides:
    """Tests for header overrides."""

    def test_header_overrides(self) -> None:
        """Headers should be overridden correctly."""
        overrides = OverridesConfig(
            headers={"x-custom-header": OverrideField(value="custom-value", mode="force")}
        )
        headers = {"content-type": "application/json"}

        _, new_headers, _ = apply_overrides(overrides, {}, headers, {})

        assert new_headers["x-custom-header"] == "custom-value"
        assert new_headers["content-type"] == "application/json"


class TestQueryOverrides:
    """Tests for query parameter overrides."""

    def test_query_overrides(self) -> None:
        """Query parameters should be overridden correctly."""
        overrides = OverridesConfig(
            query={"api_version": OverrideField(value="2024-01", mode="force")}
        )
        query = {"existing": "param"}

        _, _, new_query = apply_overrides(overrides, {}, {}, query)

        assert new_query["api_version"] == "2024-01"
        assert new_query["existing"] == "param"


class TestCopySemantics:
    """Tests that apply_overrides returns copies."""

    def test_empty_overrides_returns_copies(self) -> None:
        """Empty overrides should return new dict copies."""
        overrides = OverridesConfig()
        body = {"model": "gpt-4"}
        headers = {"content-type": "application/json"}
        query = {"param": "value"}

        new_body, new_headers, new_query = apply_overrides(overrides, body, headers, query)

        # Should be equal but not the same object
        assert new_body == body
        assert new_body is not body
        assert new_headers == headers
        assert new_headers is not headers
        assert new_query == query
        assert new_query is not query

    def test_original_not_mutated(self) -> None:
        """Original dicts should not be mutated."""
        overrides = OverridesConfig(
            body={"new_key": OverrideField(value="new_value", mode="force")}
        )
        body = {"model": "gpt-4"}
        original_body = dict(body)

        apply_overrides(overrides, body, {}, {})

        assert body == original_body
        assert "new_key" not in body
