"""Compare two versions of a contract and print the verdict.

Run it:  python examples/contract_diff.py

Version 2 of this user lookup contract removes the score field, makes
name required in a stricter way, and adds an optional note field. The
diff shows which of those changes will break existing consumers.
"""

from output_contracts import diff_contracts

V1 = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "min_length": 1},
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": ["name"],
}

V2 = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "min_length": 1},
        "note": {"type": "string"},
    },
    "required": ["name"],
}


def main() -> None:
    diff = diff_contracts(V1, V2)
    print(diff.summary())
    print()
    print("Breaking changes:", len(diff.breaking_changes))
    print("Safe to ship without a migration:", not diff.has_breaking)


if __name__ == "__main__":
    main()
