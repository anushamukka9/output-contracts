"""output-contracts: schema validation plus PII/secret redaction on tool outputs.

Declare the JSON your agent tools must return. Get structured validation
errors and redacted secrets BEFORE the model ever sees the output.
"""

from output_contracts.decorators import enforce_contract, wrap_output
from output_contracts.diff import ContractDiff, diff_contracts
from output_contracts.redact import redact_value, scan_and_redact
from output_contracts.schema import ContractBuildError
from output_contracts.validate import Contract, ContractViolation, ValidationReport

__version__ = "0.3.0"

__all__ = [
    "Contract",
    "ContractBuildError",
    "ContractDiff",
    "ContractViolation",
    "ValidationReport",
    "diff_contracts",
    "enforce_contract",
    "redact_value",
    "scan_and_redact",
    "wrap_output",
]
