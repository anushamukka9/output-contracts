"""Tests for schema build-time checking."""

import json

import pytest

from output_contracts import Contract
from output_contracts.schema import ContractBuildError, normalize_schema


def test_unknown_type_raises():
    with pytest.raises(ContractBuildError, match="unknown type"):
        Contract({"type": "strnig"})


def test_unknown_type_nested_raises():
    schema = {
        "type": "object",
        "properties": {
            "x": {"type": "object", "properties": {"y": {"type": "wat"}}},
        },
    }
    with pytest.raises(ContractBuildError, match="unknown type"):
        Contract(schema)


def test_unknown_format_raises():
    with pytest.raises(ContractBuildError, match="unknown format"):
        Contract({"type": "string", "format": "ip-address"})


def test_bad_pattern_raises():
    with pytest.raises(ContractBuildError, match="not a valid regex"):
        Contract({"type": "string", "pattern": "([unclosed"})


def test_unknown_key_raises():
    with pytest.raises(ContractBuildError, match="unknown key"):
        Contract({"type": "string", "minlen": 3})


def test_schema_must_be_dict():
    with pytest.raises(ContractBuildError, match="must be a dict"):
        normalize_schema(["type", "string"])


def test_missing_type_raises():
    with pytest.raises(ContractBuildError, match="unknown type"):
        Contract({})


def test_secret_must_be_bool():
    with pytest.raises(ContractBuildError, match="'secret'"):
        Contract({"type": "string", "secret": "yes"})


def test_required_must_be_list_of_str():
    with pytest.raises(ContractBuildError):
        Contract({"type": "object", "required": "name"})


def test_enum_must_be_list_of_str():
    with pytest.raises(ContractBuildError):
        Contract({"type": "string", "enum": "abc"})


def test_min_max_length_order():
    with pytest.raises(ContractBuildError, match="cannot exceed"):
        Contract({"type": "string", "min_length": 10, "max_length": 5})


def test_min_max_items_order():
    with pytest.raises(ContractBuildError, match="cannot exceed"):
        Contract({"type": "array", "min_items": 5, "max_items": 2})


def test_any_of_must_be_nonempty_list():
    with pytest.raises(ContractBuildError):
        Contract({"type": "any_of", "any_of": []})


def test_negative_min_items_raises():
    with pytest.raises(ContractBuildError):
        Contract({"type": "array", "min_items": -1})


def test_from_json_text():
    contract = Contract.from_json_text(json.dumps({"type": "integer", "minimum": 1}))
    report = contract.validate(5)
    assert report.valid


def test_from_json_file(tmp_path):
    path = tmp_path / "contract.json"
    path.write_text(json.dumps({"type": "string", "min_length": 2}))
    contract = Contract.from_json_file(str(path))
    assert not contract.validate("a").valid
    assert contract.validate("ab").valid


def test_description_passthrough():
    contract = Contract({"type": "string", "description": "a name"})
    assert contract.schema["description"] == "a name"
