"""Contract diff: compare two contract versions and flag breaking changes.

A change is breaking when an output that was valid under the old
contract could be invalid under the new one, or when a field that
consumers could read is gone or will now be redacted. Everything else
is reported too, just marked non-breaking, so a reviewer sees the full
picture in one pass.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from output_contracts.schema import normalize_schema

# Bounds where a higher value means a tighter contract.
_LOWER_BOUNDS = ("min_length", "min_items", "minimum", "exclusive_minimum")
# Bounds where a lower value means a tighter contract.
_UPPER_BOUNDS = ("max_length", "max_items", "maximum", "exclusive_maximum")


@dataclass
class ContractDiff:
    """Outcome of comparing two contracts."""

    changes: list[dict[str, Any]] = field(default_factory=list)

    @property
    def breaking_changes(self) -> list[dict[str, Any]]:
        return [c for c in self.changes if c["breaking"]]

    @property
    def non_breaking_changes(self) -> list[dict[str, Any]]:
        return [c for c in self.changes if not c["breaking"]]

    @property
    def has_breaking(self) -> bool:
        return any(c["breaking"] for c in self.changes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "breaking": self.has_breaking,
            "breaking_count": len(self.breaking_changes),
            "changes": self.changes,
        }

    def summary(self) -> str:
        if not self.changes:
            return "No changes."
        lines = []
        for change in self.changes:
            mark = "BREAKING" if change["breaking"] else "safe    "
            lines.append(f"{mark} {change['path']}: {change['detail']}")
        return "\n".join(lines)


def _schema_of(value: Any) -> dict[str, Any]:
    """Accept a raw schema dict or a Contract and return the normalized schema."""
    schema = getattr(value, "schema", value)
    return normalize_schema(schema)


def _add(
    changes: list[dict[str, Any]],
    path: str,
    kind: str,
    breaking: bool,
    detail: str,
    old: Any = None,
    new: Any = None,
) -> None:
    change: dict[str, Any] = {
        "path": path or "$",
        "kind": kind,
        "breaking": breaking,
        "detail": detail,
    }
    if old is not None:
        change["old"] = old
    if new is not None:
        change["new"] = new
    changes.append(change)


def _diff_bounds(
    old: dict[str, Any], new: dict[str, Any], path: str, changes: list[dict[str, Any]]
) -> None:
    for key in _LOWER_BOUNDS:
        _diff_one_bound(old, new, path, changes, key, higher_is_tighter=True)
    for key in _UPPER_BOUNDS:
        _diff_one_bound(old, new, path, changes, key, higher_is_tighter=False)


def _diff_one_bound(
    old: dict[str, Any],
    new: dict[str, Any],
    path: str,
    changes: list[dict[str, Any]],
    key: str,
    higher_is_tighter: bool,
) -> None:
    in_old, in_new = key in old, key in new
    if not in_old and not in_new:
        return
    if in_old and in_new and old[key] == new[key]:
        return
    if in_new and not in_old:
        _add(
            changes,
            path,
            "constraint_tightened",
            True,
            f"{key} added ({new[key]}); outputs that passed before can now fail",
            new=new[key],
        )
        return
    if in_old and not in_new:
        _add(
            changes,
            path,
            "constraint_loosened",
            False,
            f"{key} removed (was {old[key]})",
            old=old[key],
        )
        return
    tightened = (new[key] > old[key]) if higher_is_tighter else (new[key] < old[key])
    kind = "constraint_tightened" if tightened else "constraint_loosened"
    _add(
        changes,
        path,
        kind,
        tightened,
        f"{key} changed from {old[key]} to {new[key]}",
        old=old[key],
        new=new[key],
    )


def _diff_node(
    old: dict[str, Any], new: dict[str, Any], path: str, changes: list[dict[str, Any]]
) -> None:
    label = path or "$"
    if old.get("secret") != new.get("secret"):
        if new.get("secret"):
            _add(
                changes,
                label,
                "secret_added",
                True,
                "field is now marked secret; consumers will see a redacted value",
            )
        else:
            _add(
                changes,
                label,
                "secret_removed",
                False,
                "field is no longer marked secret; values will pass through unredacted",
            )

    old_type, new_type = old["type"], new["type"]
    if old_type != new_type:
        widening = old_type == "integer" and new_type == "number"
        _add(
            changes,
            label,
            "type_changed",
            not widening,
            f"type changed from {old_type} to {new_type}"
            + (" (widening: every integer is a number)" if widening else ""),
            old=old_type,
            new=new_type,
        )
        return

    _diff_bounds(old, new, label, changes)

    if old_type == "object":
        _diff_object(old, new, label, changes)
    elif old_type == "array":
        _diff_array(old, new, label, changes)
    elif old_type == "string":
        _diff_string(old, new, label, changes)
    elif old_type == "any_of":
        _diff_any_of(old, new, label, changes)


def _diff_object(
    old: dict[str, Any], new: dict[str, Any], path: str, changes: list[dict[str, Any]]
) -> None:
    old_props = old.get("properties", {})
    new_props = new.get("properties", {})
    old_required = set(old.get("required", []))
    new_required = set(new.get("required", []))

    for name in sorted(new_required - old_required):
        _add(
            changes,
            f"{path}.{name}" if path != "$" else name,
            "required_added",
            True,
            f"field {name!r} is now required; older outputs without it will fail",
        )
    for name in sorted(old_required - new_required):
        _add(
            changes,
            f"{path}.{name}" if path != "$" else name,
            "required_removed",
            False,
            f"field {name!r} is no longer required",
        )
    for name in sorted(old_props.keys() - new_props.keys()):
        _add(
            changes,
            f"{path}.{name}" if path != "$" else name,
            "field_removed",
            True,
            f"field {name!r} was removed; consumers reading it will find nothing",
            old=old_props[name].get("type"),
        )
    for name in sorted(new_props.keys() - old_props.keys()):
        _add(
            changes,
            f"{path}.{name}" if path != "$" else name,
            "field_added",
            False,
            f"field {name!r} was added as an optional field",
            new=new_props[name].get("type"),
        )
    for name in sorted(old_props.keys() & new_props.keys()):
        child = f"{path}.{name}" if path != "$" else name
        _diff_node(old_props[name], new_props[name], child, changes)

    if old.get("additional_properties", True) != new.get("additional_properties", True):
        if new.get("additional_properties", True):
            _add(changes, path, "additional_properties_opened", False, "unknown fields now allowed")
        else:
            _add(
                changes,
                path,
                "additional_properties_closed",
                True,
                "unknown fields are now rejected; outputs with extra fields will fail",
            )


def _diff_array(
    old: dict[str, Any], new: dict[str, Any], path: str, changes: list[dict[str, Any]]
) -> None:
    if old.get("unique_items", False) != new.get("unique_items", False):
        if new.get("unique_items"):
            _add(changes, path, "constraint_tightened", True, "items must now be unique", new=True)
        else:
            _add(changes, path, "constraint_loosened", False, "items no longer need to be unique")
    old_items, new_items = old.get("items"), new.get("items")
    if old_items is not None and new_items is not None:
        _diff_node(old_items, new_items, f"{path}[]", changes)
    elif old_items is None and new_items is not None:
        _add(
            changes,
            f"{path}[]",
            "constraint_tightened",
            True,
            "array items are now checked against a schema; some items can now fail",
        )
    elif old_items is not None and new_items is None:
        _add(
            changes, f"{path}[]", "constraint_loosened", False, "array items are no longer checked"
        )


def _diff_string(
    old: dict[str, Any], new: dict[str, Any], path: str, changes: list[dict[str, Any]]
) -> None:
    for key in ("pattern", "format"):
        if old.get(key) != new.get(key):
            if key in new:
                _add(
                    changes,
                    path,
                    "constraint_tightened",
                    True,
                    f"{key} {'added' if key not in old else 'changed'}; "
                    "strings that passed before can now fail",
                    old=old.get(key),
                    new=new.get(key),
                )
            else:
                _add(
                    changes,
                    path,
                    "constraint_loosened",
                    False,
                    f"{key} removed",
                    old=old.get(key),
                )
    old_enum = set(old.get("enum", []))
    new_enum = set(new.get("enum", []))
    if "enum" in old or "enum" in new:
        removed = sorted(old_enum - new_enum)
        added = sorted(new_enum - old_enum)
        if removed:
            _add(
                changes,
                path,
                "enum_values_removed",
                True,
                f"allowed values removed: {removed}",
                old=removed,
            )
        if added:
            _add(
                changes,
                path,
                "enum_values_added",
                False,
                f"allowed values added: {added}",
                new=added,
            )


def _signature(schema: dict[str, Any]) -> str:
    return json.dumps(schema, sort_keys=True)


def _diff_any_of(
    old: dict[str, Any], new: dict[str, Any], path: str, changes: list[dict[str, Any]]
) -> None:
    old_sigs = {_signature(option) for option in old.get("any_of", [])}
    new_sigs = {_signature(option) for option in new.get("any_of", [])}
    if old_sigs == new_sigs:
        return
    removed = old_sigs - new_sigs
    added = new_sigs - old_sigs
    # An option that was edited shows up as one removal plus one addition.
    # That is a tightening in practice, so report it as a change, breaking.
    if removed and added:
        _add(
            changes,
            path,
            "any_of_options_changed",
            True,
            "any_of options changed; outputs matching only the old options can now fail",
        )
    elif removed:
        _add(
            changes,
            path,
            "any_of_options_removed",
            True,
            f"{len(removed)} any_of option(s) removed",
        )
    elif added:
        _add(
            changes,
            path,
            "any_of_options_added",
            False,
            f"{len(added)} any_of option(s) added",
        )


def diff_contracts(old: Any, new: Any) -> ContractDiff:
    """Compare two contracts (raw schema dicts or Contract objects).

    Returns a ContractDiff. ``has_breaking`` is True when any change
    could reject an output the old contract accepted, remove a field,
    or start redacting one.
    """
    changes: list[dict[str, Any]] = []
    _diff_node(_schema_of(old), _schema_of(new), "", changes)
    return ContractDiff(changes=changes)
