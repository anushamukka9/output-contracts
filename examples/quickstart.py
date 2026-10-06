"""30-second demo: declare a contract, guard a tool, see redaction happen.

Run: python examples/quickstart.py
"""

from output_contracts import Contract, ContractViolation, enforce_contract

contract = Contract(
    {
        "type": "object",
        "properties": {
            "user": {
                "type": "object",
                "properties": {
                    "email": {"type": "string", "format": "email", "secret": True},
                    "name": {"type": "string", "min_length": 1},
                    "age": {"type": "integer", "minimum": 0, "maximum": 130},
                },
                "required": ["email", "name"],
                "additional_properties": False,
            },
            "session_token": {"type": "string", "secret": True},
        },
        "required": ["user"],
    }
)


@enforce_contract(contract)
def get_user(user_id: str) -> dict:
    # Imagine this calls a real backend. Note the token and the email
    # that the schema did not expect to leak.
    return {
        "user": {"email": "jane.doe@example.com", "name": "Jane Doe", "age": 34},
        "session_token": "sess_9f2c4a1e7b5d4f6a8c3e1d2b4a6f8e0d",
        "debug_note": "reached via sk-test-NOT-A-REAL-KEY-0123456789ab",
    }


def main() -> None:
    print("--- valid tool, output gets redacted ---")
    print(get_user("u-123"))

    print("\n--- broken tool, violation raised before the model sees it ---")
    try:
        get_user_with_bug("u-123")
    except ContractViolation as exc:
        for error in exc.report.errors:
            print(f"{error['path']}: {error['message']}")


@enforce_contract(contract)
def get_user_with_bug(user_id: str) -> dict:
    return {"user": {"email": "not-an-email", "age": "thirty-four"}}  # two violations


if __name__ == "__main__":
    main()
