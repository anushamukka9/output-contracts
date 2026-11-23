"""Tests for contract diffing."""

import json

from output_contracts import Contract, diff_contracts

BASE = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "min_length": 1, "max_length": 100},
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "tags": {"type": "array", "items": {"type": "string"}},
        "status": {"type": "string", "enum": ["ok", "warn", "fail"]},
    },
    "required": ["name"],
}


def kinds(diff):
    return {(c["path"], c["kind"]) for c in diff.changes}


def test_identical_contracts_have_no_changes():
    diff = diff_contracts(BASE, BASE)
    assert diff.changes == []
    assert diff.has_breaking is False
    assert diff.summary() == "No changes."


def test_removed_field_is_breaking():
    new = json.loads(json.dumps(BASE))
    del new["properties"]["score"]
    diff = diff_contracts(BASE, new)
    assert ("score", "field_removed") in kinds(diff)
    assert diff.has_breaking is True


def test_added_optional_field_is_safe():
    new = json.loads(json.dumps(BASE))
    new["properties"]["note"] = {"type": "string"}
    diff = diff_contracts(BASE, new)
    assert ("note", "field_added") in kinds(diff)
    assert diff.has_breaking is False


def test_new_required_field_is_breaking():
    new = json.loads(json.dumps(BASE))
    new["required"] = ["name", "score"]
    diff = diff_contracts(BASE, new)
    assert ("score", "required_added") in kinds(diff)
    assert diff.has_breaking is True


def test_required_removed_is_safe():
    diff = diff_contracts(BASE, {**BASE, "required": []})
    assert ("name", "required_removed") in kinds(diff)
    assert diff.has_breaking is False


def test_type_change_is_breaking_but_integer_to_number_widens():
    new = json.loads(json.dumps(BASE))
    new["properties"]["name"] = {"type": "integer"}
    assert diff_contracts(BASE, new).has_breaking is True

    widened = json.loads(json.dumps(BASE))
    widened["properties"]["score"] = {"type": "number", "minimum": 0, "maximum": 100}
    diff = diff_contracts(BASE, widened)
    type_changes = [c for c in diff.changes if c["kind"] == "type_changed"]
    assert type_changes and type_changes[0]["breaking"] is False
    assert diff.has_breaking is False


def test_tightened_string_bounds_break_and_loosened_do_not():
    new = json.loads(json.dumps(BASE))
    new["properties"]["name"]["min_length"] = 3
    new["properties"]["name"]["max_length"] = 50
    diff = diff_contracts(BASE, new)
    assert ("name", "constraint_tightened") in kinds(diff)
    assert diff.has_breaking is True

    loose = json.loads(json.dumps(BASE))
    loose["properties"]["name"]["max_length"] = 200
    diff = diff_contracts(BASE, loose)
    assert ("name", "constraint_loosened") in kinds(diff)
    assert diff.has_breaking is False


def test_numeric_bound_added_is_breaking_removed_is_safe():
    old = {"type": "object", "properties": {"n": {"type": "number"}}}
    new = {"type": "object", "properties": {"n": {"type": "number", "maximum": 5}}}
    assert diff_contracts(old, new).has_breaking is True
    assert diff_contracts(new, old).has_breaking is False


def test_enum_values_removed_break_added_do_not():
    new = json.loads(json.dumps(BASE))
    new["properties"]["status"]["enum"] = ["ok", "warn"]
    diff = diff_contracts(BASE, new)
    assert ("status", "enum_values_removed") in kinds(diff)
    assert diff.has_breaking is True

    wider = json.loads(json.dumps(BASE))
    wider["properties"]["status"]["enum"] = ["ok", "warn", "fail", "unknown"]
    diff = diff_contracts(BASE, wider)
    assert ("status", "enum_values_added") in kinds(diff)
    assert diff.has_breaking is False


def test_pattern_added_is_breaking():
    new = json.loads(json.dumps(BASE))
    new["properties"]["name"]["pattern"] = "^[a-z]+$"
    diff = diff_contracts(BASE, new)
    assert ("name", "constraint_tightened") in kinds(diff)
    assert diff.has_breaking is True


def test_nested_and_array_item_changes_carry_paths():
    new = json.loads(json.dumps(BASE))
    new["properties"]["tags"]["items"] = {"type": "integer"}
    diff = diff_contracts(BASE, new)
    assert ("tags[]", "type_changed") in kinds(diff)
    assert diff.has_breaking is True


def test_additional_properties_closed_is_breaking():
    new = json.loads(json.dumps(BASE))
    new["additional_properties"] = False
    diff = diff_contracts(BASE, new)
    assert ("$", "additional_properties_closed") in kinds(diff)
    assert diff.has_breaking is True


def test_secret_added_is_breaking_secret_removed_is_not():
    old = {"type": "object", "properties": {"token": {"type": "string"}}}
    new = {"type": "object", "properties": {"token": {"type": "string", "secret": True}}}
    diff = diff_contracts(old, new)
    assert ("token", "secret_added") in kinds(diff)
    assert diff.has_breaking is True
    assert diff_contracts(new, old).has_breaking is False


def test_any_of_option_removed_is_breaking_added_is_safe():
    old = {"type": "any_of", "any_of": [{"type": "string"}, {"type": "null"}]}
    new = {"type": "any_of", "any_of": [{"type": "string"}]}
    assert diff_contracts(old, new).has_breaking is True
    wider = {
        "type": "any_of",
        "any_of": [{"type": "string"}, {"type": "null"}, {"type": "integer"}],
    }
    assert diff_contracts(old, wider).has_breaking is False


def test_accepts_contract_objects_and_dict_output():
    diff = diff_contracts(Contract(BASE), Contract(BASE))
    assert diff.to_dict() == {"breaking": False, "breaking_count": 0, "changes": []}
    changed = diff_contracts(BASE, {**BASE, "required": ["name", "tags"]})
    payload = changed.to_dict()
    assert payload["breaking"] is True
    assert payload["breaking_count"] == 1
    assert "BREAKING" in changed.summary()


def test_cli_diff_breaking_exits_1_and_safe_exits_0(tmp_path, capsys):
    from output_contracts.cli import main

    old = tmp_path / "old.json"
    new = tmp_path / "new.json"
    old.write_text(json.dumps(BASE))
    changed = json.loads(json.dumps(BASE))
    del changed["properties"]["score"]
    new.write_text(json.dumps(changed))
    assert main(["diff", "--old", str(old), "--new", str(new)]) == 1
    assert "BREAKING" in capsys.readouterr().out

    new.write_text(json.dumps(BASE))
    assert main(["diff", "--old", str(old), "--new", str(new), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"breaking": False, "breaking_count": 0, "changes": []}
