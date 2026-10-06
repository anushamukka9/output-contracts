"""Schema DSL for output-contracts.

Schemas are plain dicts, so they live happily in code or in JSON files.
The tree is checked once, when the Contract is built; unknown type names
and malformed declarations are errors at build time, never at validate
time.
"""

from __future__ import annotations

import re
from typing import Any

SCHEMA_TYPES = (
    "object",
    "array",
    "string",
    "integer",
    "number",
    "boolean",
    "null",
    "any_of",
)

STRING_FORMATS = ("email", "uuid", "date", "datetime", "uri")

# Keys allowed on every schema node.
_COMMON_KEYS = {"type", "secret", "description"}


class ContractBuildError(ValueError):
    """Raised when a schema declaration is invalid."""


def _fail(path: str, message: str) -> None:
    raise ContractBuildError(f"{path}: {message}")


def _require_dict(schema: Any, path: str) -> dict[str, Any]:
    if not isinstance(schema, dict):
        _fail(path, f"schema must be a dict, got {type(schema).__name__}")
    return schema


def _check_keys(schema: dict[str, Any], allowed: set[str], path: str) -> None:
    for key in schema:
        if key not in allowed:
            _fail(path, f"unknown key {key!r} for type {schema.get('type')!r}")


def _check_secret(schema: dict[str, Any], path: str) -> None:
    if "secret" in schema and not isinstance(schema["secret"], bool):
        _fail(path, "'secret' must be true or false")


def normalize_schema(schema: dict[str, Any], path: str = "$") -> dict[str, Any]:
    """Validate and normalize a schema tree. Raises ContractBuildError."""
    schema = _require_dict(schema, path)
    stype = schema.get("type")
    if stype not in SCHEMA_TYPES:
        _fail(path, f"unknown type {stype!r}; expected one of {list(SCHEMA_TYPES)}")
    _check_secret(schema, path)

    normalized: dict[str, Any] = {"type": stype}
    if "secret" in schema:
        normalized["secret"] = schema["secret"]
    if "description" in schema:
        if not isinstance(schema["description"], str):
            _fail(path, "'description' must be a string")
        normalized["description"] = schema["description"]

    if stype == "object":
        allowed = _COMMON_KEYS | {"properties", "required", "additional_properties"}
        _check_keys(schema, allowed, path)
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            _fail(path, "'properties' must be a dict of name to schema")
        normalized["properties"] = {
            name: normalize_schema(sub, f"{path}.{name}") for name, sub in properties.items()
        }
        required = schema.get("required", [])
        if not isinstance(required, list) or not all(isinstance(r, str) for r in required):
            _fail(path, "'required' must be a list of strings")
        normalized["required"] = list(required)
        additional = schema.get("additional_properties", True)
        if not isinstance(additional, bool):
            _fail(path, "'additional_properties' must be true or false")
        normalized["additional_properties"] = additional

    elif stype == "array":
        allowed = _COMMON_KEYS | {"items", "min_items", "max_items", "unique_items"}
        _check_keys(schema, allowed, path)
        if "items" in schema:
            normalized["items"] = normalize_schema(schema["items"], f"{path}[]")
        for key in ("min_items", "max_items"):
            if key in schema:
                value = schema[key]
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    _fail(path, f"'{key}' must be a non-negative integer")
                normalized[key] = value
        if "min_items" in normalized and "max_items" in normalized:
            if normalized["min_items"] > normalized["max_items"]:
                _fail(path, "'min_items' cannot exceed 'max_items'")
        unique = schema.get("unique_items", False)
        if not isinstance(unique, bool):
            _fail(path, "'unique_items' must be true or false")
        normalized["unique_items"] = unique

    elif stype == "string":
        allowed = _COMMON_KEYS | {"min_length", "max_length", "pattern", "enum", "format"}
        _check_keys(schema, allowed, path)
        for key in ("min_length", "max_length"):
            if key in schema:
                value = schema[key]
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    _fail(path, f"'{key}' must be a non-negative integer")
                normalized[key] = value
        if "min_length" in normalized and "max_length" in normalized:
            if normalized["min_length"] > normalized["max_length"]:
                _fail(path, "'min_length' cannot exceed 'max_length'")
        if "pattern" in schema:
            pattern = schema["pattern"]
            if not isinstance(pattern, str):
                _fail(path, "'pattern' must be a string")
            try:
                re.compile(pattern)
            except re.error as exc:
                _fail(path, f"'pattern' is not a valid regex: {exc}")
            normalized["pattern"] = pattern
        if "enum" in schema:
            enum = schema["enum"]
            if not isinstance(enum, list) or not all(isinstance(e, str) for e in enum):
                _fail(path, "'enum' must be a list of strings")
            normalized["enum"] = list(enum)
        if "format" in schema:
            fmt = schema["format"]
            if fmt not in STRING_FORMATS:
                _fail(path, f"unknown format {fmt!r}; expected one of {list(STRING_FORMATS)}")
            normalized["format"] = fmt

    elif stype in ("integer", "number"):
        allowed = _COMMON_KEYS | {"minimum", "maximum", "exclusive_minimum", "exclusive_maximum"}
        _check_keys(schema, allowed, path)
        for key in ("minimum", "maximum", "exclusive_minimum", "exclusive_maximum"):
            if key in schema:
                value = schema[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    _fail(path, f"'{key}' must be a number")
                if stype == "integer" and isinstance(value, float) and not value.is_integer():
                    _fail(path, f"'{key}' must be an integer for integer type")
                normalized[key] = value

    elif stype == "any_of":
        allowed = _COMMON_KEYS | {"any_of"}
        _check_keys(schema, allowed, path)
        options = schema.get("any_of")
        if not isinstance(options, list) or not options:
            _fail(path, "'any_of' must be a non-empty list of schemas")
        normalized["any_of"] = [
            normalize_schema(sub, f"{path}.any_of[{i}]") for i, sub in enumerate(options)
        ]

    else:  # boolean, null: no extra keys
        _check_keys(schema, _COMMON_KEYS, path)

    return normalized
