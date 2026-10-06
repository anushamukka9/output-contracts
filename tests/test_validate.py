"""Tests for Contract.validate / Contract.check."""

import pytest

from output_contracts import Contract, ContractViolation

OBJECT = {
    "type": "object",
    "properties": {
        "user": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "format": "email"},
                "age": {"type": "integer", "minimum": 0},
            },
            "required": ["email"],
        },
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["user"],
}


def test_valid_object():
    report = Contract(OBJECT).validate({"user": {"email": "a@b.com", "age": 3}, "tags": ["x"]})
    assert report.valid
    assert report.errors == []


def test_missing_required_field():
    report = Contract(OBJECT).validate({"user": {"age": 3}})
    assert not report.valid
    assert report.errors[0]["path"] == "user.email"
    assert "missing required" in report.errors[0]["message"]


def test_missing_top_level_required():
    report = Contract(OBJECT).validate({})
    assert not report.valid
    assert report.errors[0]["path"] == "user"


def test_wrong_type():
    report = Contract(OBJECT).validate({"user": {"email": "a@b.com", "age": "old"}})
    assert not report.valid
    error = report.errors[0]
    assert error["path"] == "user.age"
    assert error["expected"] == "integer"
    assert error["actual"] == "string (length 3)"


def test_error_never_shows_string_value():
    report = Contract({"type": "string", "min_length": 50}).validate("short-secret-value")
    assert "short-secret-value" not in str(report.errors)


def test_additional_properties_false():
    contract = Contract(
        {"type": "object", "properties": {"a": {"type": "string"}}, "additional_properties": False}
    )
    report = contract.validate({"a": "x", "b": "y"})
    assert not report.valid
    assert report.errors[0]["path"] == "b"


def test_additional_properties_default_true():
    report = Contract({"type": "object", "properties": {"a": {"type": "string"}}}).validate(
        {"a": "x", "b": "y"}
    )
    assert report.valid


def test_nested_path():
    contract = Contract(
        {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"token": {"type": "string"}},
                        "required": ["token"],
                    },
                }
            },
        }
    )
    report = contract.validate({"items": [{}, {"token": "x"}, {"token": 5}]})
    paths = [e["path"] for e in report.errors]
    assert "items[0].token" in paths
    assert "items[2].token" in paths


def test_array_min_max_items():
    contract = Contract({"type": "array", "min_items": 2, "max_items": 3})
    assert not Contract({"type": "array", "min_items": 2}).validate([1]).valid
    assert not Contract({"type": "array", "max_items": 1}).validate([1, 2]).valid
    assert contract.validate([1, 2]).valid


def test_unique_items():
    contract = Contract({"type": "array", "unique_items": True, "items": {"type": "integer"}})
    assert not contract.validate([1, 2, 1]).valid
    assert contract.validate([1, 2, 3]).valid


def test_string_lengths():
    contract = Contract({"type": "string", "min_length": 2, "max_length": 4})
    assert not contract.validate("a").valid
    assert not contract.validate("abcde").valid
    assert contract.validate("abc").valid


def test_string_pattern():
    contract = Contract({"type": "string", "pattern": r"^[a-z]+$"})
    assert contract.validate("abc").valid
    assert not contract.validate("ABC").valid


def test_string_enum():
    contract = Contract({"type": "string", "enum": ["red", "green"]})
    assert contract.validate("red").valid
    assert not contract.validate("blue").valid


@pytest.mark.parametrize(
    "fmt,value,valid",
    [
        ("email", "a@b.com", True),
        ("email", "not-an-email", False),
        ("uuid", "123e4567-e89b-12d3-a456-426614174000", True),
        ("uuid", "nope", False),
        ("date", "2026-10-06", True),
        ("date", "2026-13-40", False),
        ("datetime", "2026-10-06T18:47:00", True),
        ("datetime", "2026-10-06T18:47:00Z", True),
        ("datetime", "yesterday", False),
        ("uri", "https://example.com/x", True),
        ("uri", "not a uri", False),
    ],
)
def test_string_formats(fmt, value, valid):
    report = Contract({"type": "string", "format": fmt}).validate(value)
    assert report.valid == valid, f"{fmt} {value!r}"


def test_integer_bounds():
    contract = Contract({"type": "integer", "minimum": 0, "maximum": 10})
    assert contract.validate(5).valid
    assert not contract.validate(-1).valid
    assert not contract.validate(11).valid


def test_exclusive_bounds():
    contract = Contract({"type": "integer", "exclusive_minimum": 0, "exclusive_maximum": 10})
    assert not contract.validate(0).valid
    assert not contract.validate(10).valid
    assert contract.validate(5).valid


def test_bool_is_not_integer():
    assert not Contract({"type": "integer"}).validate(True).valid
    assert not Contract({"type": "number"}).validate(False).valid


def test_number_accepts_int_and_float():
    contract = Contract({"type": "number", "minimum": 0.5})
    assert contract.validate(1).valid
    assert contract.validate(0.75).valid
    assert not contract.validate(0.25).valid


def test_boolean():
    assert Contract({"type": "boolean"}).validate(True).valid
    assert not Contract({"type": "boolean"}).validate("true").valid
    assert not Contract({"type": "boolean"}).validate(1).valid


def test_null():
    assert Contract({"type": "null"}).validate(None).valid
    assert not Contract({"type": "null"}).validate(0).valid


def test_any_of():
    contract = Contract({"type": "any_of", "any_of": [{"type": "string"}, {"type": "null"}]})
    assert contract.validate("x").valid
    assert contract.validate(None).valid
    report = contract.validate(5)
    assert not report.valid
    assert "any_of" in report.errors[0]["expected"]


def test_check_returns_redacted_clean_copy():
    contract = Contract(
        {
            "type": "object",
            "properties": {
                "email": {"type": "string", "secret": True},
                "name": {"type": "string"},
            },
        }
    )
    data = {"email": "a@b.com", "name": "Ann"}
    clean = contract.check(data)
    assert clean["email"] == "[REDACTED:declared_secret]"
    assert clean["name"] == "Ann"
    assert data["email"] == "a@b.com"  # original untouched


def test_check_raises_carrying_report():
    contract = Contract({"type": "string", "min_length": 10})
    with pytest.raises(ContractViolation) as exc_info:
        contract.check("short")
    assert isinstance(exc_info.value, ValueError)
    assert exc_info.value.report is not None
    assert not exc_info.value.report.valid
    assert "violation" in str(exc_info.value)


def test_validate_always_redacts_even_when_invalid():
    contract = Contract(
        {
            "type": "object",
            "properties": {
                "email": {"type": "string", "secret": True},
                "n": {"type": "integer"},
            },
        }
    )
    report = contract.validate({"email": "a@b.com", "n": "not-an-int"})
    assert not report.valid
    assert report.clean["email"] == "[REDACTED:declared_secret]"
    assert any(r["kind"] == "declared_secret" for r in report.redactions)


def test_root_wrong_type_path():
    report = Contract({"type": "object"}).validate([1, 2])
    assert not report.valid
    assert report.errors[0]["path"] == "$"


def test_report_to_dict():
    report = Contract({"type": "string"}).validate("x")
    d = report.to_dict()
    assert d["valid"] is True
    assert d["errors"] == []
    assert d["clean"] == "x"
