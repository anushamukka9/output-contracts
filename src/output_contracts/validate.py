"""Validation engine: the Contract class and its report."""

from __future__ import annotations

import copy
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from output_contracts.redact import redact_value, scan_and_redact
from output_contracts.schema import normalize_schema

URI_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://\S+$")


@dataclass
class ValidationReport:
    """Outcome of validating one payload against a Contract."""

    valid: bool
    errors: list[dict[str, Any]] = field(default_factory=list)
    redactions: list[dict[str, str]] = field(default_factory=list)
    clean: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "redactions": self.redactions,
            "clean": self.clean,
        }


class ContractViolation(ValueError):
    """Raised by Contract.check when data fails validation. Carries the report."""

    def __init__(self, report: ValidationReport) -> None:
        self.report = report
        first = report.errors[0] if report.errors else {}
        message = (
            f"output contract violation: {len(report.errors)} error(s); "
            f"first at {first.get('path', '?')}: {first.get('message', 'invalid data')}"
        )
        super().__init__(message)


def _actual(data: Any) -> str:
    if isinstance(data, str):
        return f"string (length {len(data)})"
    if isinstance(data, bool):
        return "boolean"
    return type(data).__name__


def _error(path: str, message: str, expected: str, data: Any) -> dict[str, Any]:
    return {"path": path or "$", "message": message, "expected": expected, "actual": _actual(data)}


def _check_format(fmt: str, value: str, path: str, errors: list[dict[str, Any]]) -> None:
    ok = True
    if fmt == "email":
        from output_contracts.redact import EMAIL_RE

        ok = EMAIL_RE.fullmatch(value) is not None
    elif fmt == "uuid":
        try:
            uuid.UUID(value)
        except (ValueError, AttributeError, TypeError):
            ok = False
    elif fmt == "date":
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            ok = False
    elif fmt == "datetime":
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            ok = False
    elif fmt == "uri":
        ok = URI_RE.match(value) is not None
    if not ok:
        errors.append(_error(path, f"does not match format {fmt!r}", f"format {fmt}", value))


def _validate(schema: dict[str, Any], data: Any, path: str, errors: list[dict[str, Any]]) -> None:
    stype = schema["type"]
    label = path or "$"

    if stype == "any_of":
        for option in schema["any_of"]:
            sub_errors: list[dict[str, Any]] = []
            _validate(option, data, path, sub_errors)
            if not sub_errors:
                return
        errors.append(
            _error(
                path,
                "does not match any of the allowed schemas",
                f"any_of ({len(schema['any_of'])} options)",
                data,
            )
        )
        return

    if stype == "null":
        if data is not None:
            errors.append(_error(path, f"expected null at {label}", "null", data))
        return

    if stype == "boolean":
        if not isinstance(data, bool):
            errors.append(_error(path, f"expected boolean at {label}", "boolean", data))
        return

    if stype == "integer":
        if isinstance(data, bool) or not isinstance(data, int):
            errors.append(_error(path, f"expected integer at {label}", "integer", data))
            return
        _check_numeric_bounds(schema, data, path, errors, "integer")
        return

    if stype == "number":
        if isinstance(data, bool) or not isinstance(data, (int, float)):
            errors.append(_error(path, f"expected number at {label}", "number", data))
            return
        _check_numeric_bounds(schema, data, path, errors, "number")
        return

    if stype == "string":
        if not isinstance(data, str):
            errors.append(_error(path, f"expected string at {label}", "string", data))
            return
        if "min_length" in schema and len(data) < schema["min_length"]:
            errors.append(
                _error(
                    path,
                    f"string at {label} is too short",
                    f"length >= {schema['min_length']}",
                    data,
                )
            )
        if "max_length" in schema and len(data) > schema["max_length"]:
            errors.append(
                _error(
                    path,
                    f"string at {label} is too long",
                    f"length <= {schema['max_length']}",
                    data,
                )
            )
        if "pattern" in schema and re.search(schema["pattern"], data) is None:
            errors.append(
                _error(
                    path,
                    f"string at {label} does not match pattern",
                    f"pattern {schema['pattern']!r}",
                    data,
                )
            )
        if "enum" in schema and data not in schema["enum"]:
            errors.append(
                _error(
                    path,
                    f"string at {label} is not an allowed value",
                    f"one of {schema['enum']}",
                    data,
                )
            )
        if "format" in schema:
            _check_format(schema["format"], data, path, errors)
        return

    if stype == "array":
        if not isinstance(data, list):
            errors.append(_error(path, f"expected array at {label}", "array", data))
            return
        if "min_items" in schema and len(data) < schema["min_items"]:
            errors.append(
                _error(
                    path,
                    f"array at {label} has too few items",
                    f"at least {schema['min_items']} items",
                    data,
                )
            )
        if "max_items" in schema and len(data) > schema["max_items"]:
            errors.append(
                _error(
                    path,
                    f"array at {label} has too many items",
                    f"at most {schema['max_items']} items",
                    data,
                )
            )
        if schema.get("unique_items"):
            seen: list[str] = []
            for item in data:
                key = json.dumps(item, sort_keys=True, default=str)
                if key in seen:
                    errors.append(
                        _error(path, f"array at {label} has duplicate items", "unique items", data)
                    )
                    break
                seen.append(key)
        if "items" in schema:
            for i, item in enumerate(data):
                _validate(schema["items"], item, f"{label}[{i}]", errors)
        return

    if stype == "object":
        if not isinstance(data, dict):
            errors.append(_error(path, f"expected object at {label}", "object", data))
            return
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in data:
                child = f"{label}.{name}" if label != "$" else name
                errors.append(
                    _error(child, f"missing required field {name!r}", "field present", data)
                )
        for name, value in data.items():
            child = f"{label}.{name}" if label != "$" else name
            if name in properties:
                _validate(properties[name], value, child, errors)
            elif not schema.get("additional_properties", True):
                errors.append(
                    _error(child, f"unexpected field {name!r}", "declared property", data)
                )
        return

    errors.append(_error(path, f"internal error: unhandled type {stype!r}", stype, data))


def _check_numeric_bounds(
    schema: dict[str, Any], data: Any, path: str, errors: list[dict[str, Any]], stype: str
) -> None:
    label = path or "$"
    if "minimum" in schema and data < schema["minimum"]:
        errors.append(
            _error(path, f"{stype} at {label} is below minimum", f">= {schema['minimum']}", data)
        )
    if "maximum" in schema and data > schema["maximum"]:
        errors.append(
            _error(path, f"{stype} at {label} is above maximum", f"<= {schema['maximum']}", data)
        )
    if "exclusive_minimum" in schema and data <= schema["exclusive_minimum"]:
        errors.append(
            _error(
                path,
                f"{stype} at {label} is not above exclusive minimum",
                f"> {schema['exclusive_minimum']}",
                data,
            )
        )
    if "exclusive_maximum" in schema and data >= schema["exclusive_maximum"]:
        errors.append(
            _error(
                path,
                f"{stype} at {label} is not below exclusive maximum",
                f"< {schema['exclusive_maximum']}",
                data,
            )
        )


def _apply_forced_redactions(
    schema: dict[str, Any], data: Any, path: str, style: str, redactions: list[dict[str, str]]
) -> Any:
    """Redact fields declared secret:true, regardless of detection."""
    if schema.get("secret") and isinstance(data, str):
        redactions.append({"path": path or "$", "kind": "declared_secret"})
        return redact_value(data, "declared_secret", style)
    stype = schema["type"]
    if stype == "object" and isinstance(data, dict):
        out = {}
        for name, value in data.items():
            child = f"{path}.{name}" if path else name
            sub = schema.get("properties", {}).get(name)
            out[name] = (
                _apply_forced_redactions(sub, value, child, style, redactions) if sub else value
            )
        return out
    if stype == "array" and isinstance(data, list) and "items" in schema:
        return [
            _apply_forced_redactions(schema["items"], value, f"{path}[{i}]", style, redactions)
            for i, value in enumerate(data)
        ]
    if stype == "any_of":
        # Forced redaction follows the first matching option, so declared
        # secrets stay redacted even under any_of. Best effort, documented.
        for option in schema["any_of"]:
            trial: list[dict[str, Any]] = []
            _validate(option, data, path, trial)
            if not trial:
                return _apply_forced_redactions(option, data, path, style, redactions)
    return data


class Contract:
    """A named, build-time-checked schema for one tool's output."""

    def __init__(self, schema: dict[str, Any]) -> None:
        self.schema = normalize_schema(schema)

    @classmethod
    def from_json_text(cls, text: str) -> Contract:
        return cls(json.loads(text))

    @classmethod
    def from_json_file(cls, path: str) -> Contract:
        with open(path, encoding="utf-8") as fh:
            return cls(json.load(fh))

    def validate(self, data: Any, style: str = "full") -> ValidationReport:
        """Validate data. Always returns a report; always redacts the copy.

        The returned clean data is a deep copy with declared secrets and
        detected secrets redacted, even when validation fails.
        """
        errors: list[dict[str, Any]] = []
        _validate(self.schema, data, "", errors)
        working = copy.deepcopy(data)
        redactions: list[dict[str, str]] = []
        working = _apply_forced_redactions(self.schema, working, "", style, redactions)
        working, scanned = scan_and_redact(working, style)
        redactions.extend(scanned)
        return ValidationReport(
            valid=not errors, errors=errors, redactions=redactions, clean=working
        )

    def check(self, data: Any, style: str = "full") -> Any:
        """Validate and return the redacted clean copy, or raise ContractViolation."""
        report = self.validate(data, style)
        if not report.valid:
            raise ContractViolation(report)
        return report.clean
