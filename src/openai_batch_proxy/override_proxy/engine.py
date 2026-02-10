from typing import Any

from openai_batch_proxy.override_proxy.config import OverrideField, OverridesConfig


def apply_overrides(
    overrides: OverridesConfig,
    body: dict[str, Any],
    headers: dict[str, str],
    query: dict[str, str],
) -> tuple[dict[str, Any], dict[str, str], dict[str, str]]:
    """Apply overrides to request data. Returns modified copies."""
    body = dict(body)
    headers = dict(headers)
    query = dict(query)

    _apply_field_overrides(body, overrides.body, nested=True)
    _apply_field_overrides(headers, overrides.headers, nested=False)
    _apply_field_overrides(query, overrides.query, nested=False)

    return body, headers, query


def _apply_field_overrides(
    target: dict[str, Any],
    overrides: dict[str, OverrideField],
    nested: bool,
) -> None:
    """Apply overrides to target dict in-place."""
    for key, field in overrides.items():
        if nested and "." in key:
            _set_nested(target, key.split("."), field)
        else:
            if field.mode == "force":
                target[key] = field.value
            elif key not in target:
                target[key] = field.value


def _set_nested(
    target: dict[str, Any], parts: list[str], field: OverrideField
) -> None:
    """Traverse/create nested dicts and set the leaf value."""
    for part in parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            if field.mode == "default" and part in target:
                return  # non-dict exists at this path; default mode does nothing
            target[part] = {}
        target = target[part]
    leaf = parts[-1]
    if field.mode == "force":
        target[leaf] = field.value
    elif leaf not in target:
        target[leaf] = field.value
