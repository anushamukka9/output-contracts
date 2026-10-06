"""Decorator and helper for enforcing contracts on tool functions."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from output_contracts.validate import Contract


def _as_contract(contract: Contract | dict[str, Any]) -> Contract:
    if isinstance(contract, Contract):
        return contract
    return Contract(contract)


def enforce_contract(contract: Contract | dict[str, Any]) -> Callable:
    """Decorate a tool function so its output is validated and redacted.

    On success the caller gets the redacted clean copy, never the raw
    output. On validation failure a ContractViolation is raised and the
    raw output never leaves the tool.
    """

    def decorator(fn: Callable) -> Callable:
        checked = _as_contract(contract)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return checked.check(fn(*args, **kwargs))

        return wrapper

    return decorator


def wrap_output(contract: Contract | dict[str, Any], data: Any) -> Any:
    """Validate one payload and return the redacted clean copy.

    Raises ContractViolation when the payload is invalid.
    """
    return _as_contract(contract).check(data)
