"""Tests for the decorator and wrap_output helper."""

import pytest

from output_contracts import Contract, ContractViolation, enforce_contract, wrap_output

CONTRACT_DICT = {
    "type": "object",
    "properties": {
        "email": {"type": "string", "format": "email", "secret": True},
        "name": {"type": "string"},
    },
    "required": ["email"],
}


def test_decorator_returns_redacted_output():
    @enforce_contract(CONTRACT_DICT)
    def tool():
        return {"email": "jane@example.com", "name": "Jane"}

    result = tool()
    assert result == {"email": "[REDACTED:declared_secret]", "name": "Jane"}


def test_decorator_accepts_contract_instance():
    @enforce_contract(Contract(CONTRACT_DICT))
    def tool():
        return {"email": "jane@example.com"}

    assert tool()["email"] == "[REDACTED:declared_secret]"


def test_decorator_raises_on_violation():
    @enforce_contract(CONTRACT_DICT)
    def tool():
        return {"email": "not-an-email"}

    with pytest.raises(ContractViolation) as exc_info:
        tool()
    assert exc_info.value.report.errors[0]["path"] == "email"


def test_decorator_preserves_function_name():
    @enforce_contract(CONTRACT_DICT)
    def my_tool():
        return {"email": "a@b.com"}

    assert my_tool.__name__ == "my_tool"


def test_decorator_passes_args():
    @enforce_contract(CONTRACT_DICT)
    def tool(email, name="x"):
        return {"email": email, "name": name}

    assert tool("a@b.com", name="Ann")["name"] == "Ann"


def test_wrap_output_valid():
    clean = wrap_output(CONTRACT_DICT, {"email": "a@b.com", "name": "n"})
    assert clean["email"] == "[REDACTED:declared_secret]"


def test_wrap_output_invalid_raises():
    with pytest.raises(ContractViolation):
        wrap_output(CONTRACT_DICT, {"name": "missing email"})
