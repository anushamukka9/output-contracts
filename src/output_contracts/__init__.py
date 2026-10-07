"""output-contracts: schema validation plus PII/secret redaction on tool outputs.

Declare the JSON your agent tools must return. Get structured validation
errors and redacted secrets BEFORE the model ever sees the output.
"""

from output_contracts.decorators import enforce_contract, wrap_output
from output_contracts.redact import redact_value, scan_and_redact
from output_contracts.schema import ContractBuildError
from output_contracts.validate import Contract, ContractViolation, ValidationReport

__version__ = "0.2.0"

__all__ = [
    "Contract",
    "ContractBuildError",
    "ContractViolation",
    "ValidationReport",
    "enforce_contract",
    "redact_value",
    "scan_and_redact",
    "wrap_output",
]
