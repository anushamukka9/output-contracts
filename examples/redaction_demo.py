"""Redaction demo: every detector on one payload, both styles.

Run: python examples/redaction_demo.py
"""

import json

from output_contracts import scan_and_redact

PAYLOAD = {
    "support_ticket": {
        "customer": "jane.doe@example.com",
        "phone": "call me back at (555) 123-4567",
        "ssn": "last four of 078-05-1120 on file",
        "card": "charged 4111 1111 1111 1111",
        "api_key": "rotate sk-test-NOT-A-REAL-KEY-0123456789ab today",
        "aws": "old key AKIAIOSFODNN7EXAMPLE is disabled",
        "auth": "Authorization: Bearer test-bearer-token-abc123XYZ",
        "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.dummy-signature-part",
        "server": "deployed to 10.0.4.15",
        "note": "nothing sensitive in this sentence at all",
    }
}


def show(style: str) -> None:
    redacted, redactions = scan_and_redact(PAYLOAD, style=style)
    print(f"=== style: {style} ===")
    print(json.dumps(redacted, indent=2))
    print("redactions:")
    for r in redactions:
        print(f"  {r['path']}: {r['kind']}")


def main() -> None:
    show("full")
    print()
    show("partial")


if __name__ == "__main__":
    main()
