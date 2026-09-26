"""Tiny JSON-Schema subset validator (no third-party dependency).

M0 deliberately avoids requiring ``jsonschema``. This validator implements
the subset used by ``datasets/manifests/schema.json``: top-level object
shape, ``required``, ``additionalProperties``, ``type`` (including
type unions with ``null``), ``enum``, numeric bounds, and basic
array/object nesting. M1 may replace it with ``jsonschema`` without
changing call sites.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_TYPE_MAP: dict[str, tuple[type[Any], ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
    "null": (type(None),),
}


class ValidationError(ValueError):
    """Raised when an asset manifest violates the schema."""


def load_schema(path: str | Path) -> dict[str, Any]:
    """Load and return the JSON schema document."""
    with open(path, encoding="utf-8") as handle:
        schema = json.load(handle)
    if not isinstance(schema, dict):
        raise ValidationError("Schema root must be an object")
    return schema


def _matches_type(value: Any, json_type: str) -> bool:
    # bool is a subclass of int in Python; keep booleans out of number types.
    if json_type in {"integer", "number"} and isinstance(value, bool):
        return False
    return isinstance(value, _TYPE_MAP[json_type])


def _type_ok(value: Any, type_spec: str | list[str]) -> bool:
    allowed = type_spec if isinstance(type_spec, list) else [type_spec]
    return any(_matches_type(value, candidate) for candidate in allowed)


def _validate_node(value: Any, spec: dict[str, Any], path: str, errors: list[str]) -> None:
    if "type" in spec and not _type_ok(value, spec["type"]):
        errors.append(f"{path}: expected type {spec['type']}, got {type(value).__name__}")
        return
    if "enum" in spec and value not in spec["enum"]:
        errors.append(f"{path}: value {value!r} not in enum {spec['enum']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in spec and value < spec["minimum"]:
            errors.append(f"{path}: {value} below minimum {spec['minimum']}")
        if "maximum" in spec and value > spec["maximum"]:
            errors.append(f"{path}: {value} above maximum {spec['maximum']}")
    if isinstance(value, list) and spec.get("type") == "array":
        item_spec = spec.get("items")
        if isinstance(item_spec, dict):
            for idx, item in enumerate(value):
                _validate_node(item, item_spec, f"{path}[{idx}]", errors)
        if "minItems" in spec and len(value) < spec["minItems"]:
            errors.append(f"{path}: fewer than {spec['minItems']} items")
        if "maxItems" in spec and len(value) > spec["maxItems"]:
            errors.append(f"{path}: more than {spec['maxItems']} items")
    if isinstance(value, dict) and spec.get("type") == "object":
        properties = spec.get("properties", {})
        if spec.get("additionalProperties") is False:
            extras = set(value) - set(properties)
            if extras:
                errors.append(f"{path}: unexpected properties {sorted(extras)}")
        for required_name in spec.get("required", []):
            if required_name not in value:
                errors.append(f"{path}: missing required property {required_name!r}")
        for name, child in value.items():
            if name in properties:
                _validate_node(child, properties[name], f"{path}.{name}", errors)


def _find_default_schema() -> Path:
    """Walk upward from this file to locate ``datasets/manifests/schema.json``."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "datasets" / "manifests" / "schema.json"
        if candidate.is_file():
            return candidate
    raise ValidationError("Could not locate datasets/manifests/schema.json")


def validate_asset(asset: dict[str, Any], schema: dict[str, Any] | None = None) -> None:
    """Validate one asset record against the schema.

    Raises:
        ValidationError: aggregated human-readable list of violations.
    """
    if schema is None:
        schema = load_schema(_find_default_schema())
    errors: list[str] = []
    _validate_node(asset, schema, "$", errors)
    if errors:
        raise ValidationError("Manifest validation failed:\n  - " + "\n  - ".join(errors))


__all__ = ["ValidationError", "load_schema", "validate_asset"]
