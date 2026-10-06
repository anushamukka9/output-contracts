"""Extended benchmarks for output-contracts. Prints measured numbers.

Run: python benchmarks/bench.py
Record the output in benchmarks/results.md.
"""

from __future__ import annotations

import statistics
import time

from output_contracts import scan_and_redact
from output_contracts.validate import Contract

CONTRACT = Contract(
    {
        "type": "object",
        "properties": {
            "user": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "format": "uuid"},
                    "email": {"type": "string", "format": "email", "secret": True},
                    "name": {"type": "string", "min_length": 1, "max_length": 80},
                    "age": {"type": "integer", "minimum": 0, "maximum": 130},
                    "tags": {
                        "type": "array",
                        "max_items": 20,
                        "unique_items": True,
                        "items": {"type": "string", "max_length": 40},
                    },
                },
                "required": ["id", "email", "name"],
                "additional_properties": False,
            },
            "items": {
                "type": "array",
                "min_items": 1,
                "max_items": 10,
                "items": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string", "pattern": r"^[A-Z]{2}-\d{4}$"},
                        "price": {"type": "number", "minimum": 0},
                        "status": {"type": "string", "enum": ["new", "used", "refurb"]},
                        "note": {"type": "string", "max_length": 200},
                    },
                    "required": ["sku", "price", "status"],
                },
            },
        },
        "required": ["user", "items"],
    }
)

PAYLOAD = {
    "user": {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "email": "jane.doe@example.com",
        "name": "Jane Doe",
        "age": 34,
        "tags": ["vip", "beta", "newsletter"],
    },
    "items": [
        {"sku": "AB-1234", "price": 19.99, "status": "new", "note": "call (555) 123-4567"},
        {"sku": "CD-5678", "price": 4.5, "status": "used", "note": "plain note"},
        {"sku": "EF-9012", "price": 99.0, "status": "refurb", "note": "sk-test-NOT-A-REAL-KEY"},
    ],
}

SMALL = {"ok": True, "message": "hello"}


def _time(fn, iterations: int, rounds: int = 5) -> float:
    samples = []
    for _ in range(rounds):
        start = time.perf_counter()
        for _ in range(iterations):
            fn()
        samples.append(iterations / (time.perf_counter() - start))
    return statistics.median(samples)


def main() -> None:
    validate_small = _time(lambda: Contract({"type": "object"}).validate(SMALL), 50000)
    validate_payload = _time(lambda: CONTRACT.validate(PAYLOAD), 20000)
    redact_only = _time(lambda: scan_and_redact(PAYLOAD), 20000)
    invalid = dict(PAYLOAD)
    invalid["user"] = dict(PAYLOAD["user"])
    invalid["user"]["age"] = "thirty-four"

    def _invalid() -> None:
        report = CONTRACT.validate(invalid)
        assert not report.valid

    validate_invalid = _time(_invalid, 20000)

    print(f"validate trivial object:      {validate_small:>12,.0f} ops/sec")
    print(f"validate realistic payload:   {validate_payload:>12,.0f} ops/sec")
    print(f"scan_and_redact (redact only):{redact_only:>12,.0f} ops/sec")
    print(f"validate invalid payload:     {validate_invalid:>12,.0f} ops/sec")
    print("done")


if __name__ == "__main__":
    main()
