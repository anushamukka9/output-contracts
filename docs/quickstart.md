# Quickstart

Five minutes from zero to a guarded tool.

## Install

```bash
pip install output-contracts
```

Zero runtime dependencies, stdlib only.

## 1. Write a contract

A contract is a plain dict describing the JSON one of your tools must
return:

```python
from output_contracts import Contract

contract = Contract({
    "type": "object",
    "properties": {
        "user": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "format": "email", "secret": True},
                "name": {"type": "string", "min_length": 1},
            },
            "required": ["email", "name"],
            "additional_properties": False,
        },
        "items": {
            "type": "array",
            "min_items": 1,
            "items": {"type": "string"},
        },
    },
    "required": ["user", "items"],
})
```

Contracts can also live in JSON files and load with
`Contract.from_json_file("contract.json")`. Schema mistakes (unknown
type names, bad keys, bad regexes) raise `ContractBuildError` here, at
build time, so you find out before any data flows.

## 2. Wrap your tool

```python
from output_contracts import enforce_contract

@enforce_contract(contract)
def search_users(query: str) -> dict:
    ...  # whatever the tool actually does
    return {"user": {...}, "items": [...]}
```

Callers get the validated, redacted copy. If the tool's output breaks
the contract, the wrapper raises `ContractViolation` (a `ValueError`
subclass carrying the full `ValidationReport`) and the raw output
never leaves the tool.

## 3. Validate by hand

```python
report = contract.validate(tool_output)
if not report.valid:
    for error in report.errors:
        print(error["path"], error["message"])
    # paths look like "user.email" and "items[2].token"
print(report.clean)      # redacted copy, safe to hand to the model
print(report.redactions) # [{"path": "user.email", "kind": "email"}, ...]
```

`secret: True` on a field forces redaction no matter what the value
looks like. Everything else gets the global scan: emails, phone
numbers, SSNs, credit cards, API keys, JWTs, and private keys are
redacted in any string value, anywhere in the tree.

## CLI

```bash
output-contracts validate --contract contract.json --input output.json
output-contracts redact --input output.json --style partial
output-contracts check --contract contract.json --input output.json  # CI: exit 2 on invalid
```

Next: the full schema reference is in [contracts.md](contracts.md),
detector details in [redaction.md](redaction.md), and the honest list
of what this cannot do in [limitations.md](limitations.md).
