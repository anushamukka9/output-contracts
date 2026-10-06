"""CI smoke benchmark: validates and redacts synthetic payloads.

Run with: python -m output_contracts.benchmark
"""

from __future__ import annotations

import time

from output_contracts.validate import Contract

_CONTRACT = Contract(
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
                        "note": {"type": "string", "max_length": 200},
                    },
                    "required": ["sku", "price"],
                },
            },
        },
        "required": ["user", "items"],
    }
)

_PAYLOAD = {
    "user": {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "email": "jane.doe@example.com",
        "name": "Jane Doe",
        "age": 34,
    },
    "items": [
        {
            "sku": "AB-1234",
            "price": 19.99,
            "note": "contact ops at ops@example.com or call (555) 123-4567",
        },
        {"sku": "CD-5678", "price": 4.5, "note": "token sk-test-NOT-A-REAL-KEY-0123456789ab"},
    ],
}


def bench_validate(iterations: int = 20000) -> float:
    start = time.perf_counter()
    for _ in range(iterations):
        report = _CONTRACT.validate(_PAYLOAD)
        assert report.valid
    elapsed = time.perf_counter() - start
    return iterations / elapsed


def bench_redact(iterations: int = 20000) -> float:
    from output_contracts.redact import scan_and_redact

    start = time.perf_counter()
    for _ in range(iterations):
        scan_and_redact(_PAYLOAD)
    elapsed = time.perf_counter() - start
    return iterations / elapsed


def main() -> None:
    validate_ops = bench_validate()
    redact_ops = bench_redact()
    print(f"validate+redact throughput: {validate_ops:,.0f} ops/sec")
    print(f"scan_and_redact throughput: {redact_ops:,.0f} ops/sec")
    print("benchmark smoke test passed")


if __name__ == "__main__":
    main()
