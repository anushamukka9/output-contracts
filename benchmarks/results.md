# Benchmark results

Measured 2026-10-06 on the build machine (Linux, Python 3.12, single
process). Numbers come from `benchmarks/bench.py` (median of 5 rounds)
and the CI smoke module `output_contracts.benchmark`.

## Extended benchmarks (`benchmarks/bench.py`)

The realistic payload is a nested tool output: a user object (uuid,
secret email, name, age, 3 tags) plus 3 line items with sku pattern,
price, status enum, and notes containing a phone number and an API
key.

| Benchmark | Result |
|---|---|
| Validate trivial object | 61,617 ops/sec |
| Validate realistic payload (validate + redact) | 3,601 ops/sec |
| scan_and_redact only | 5,386 ops/sec |
| Validate invalid payload (fails with 1 error) | 3,524 ops/sec |

## CI smoke (`python -m output_contracts.benchmark`)

Smaller payload, 20,000 iterations, single timed run:

| Benchmark | Result |
|---|---|
| validate + redact throughput | 4,894 ops/sec |
| scan_and_redact throughput | 7,240 ops/sec |

## What the numbers mean

Validation does a deep copy plus two walks (validate, then redact),
so the realistic-payload number is the honest per-tool-call cost:
about 0.28 ms. That is cheap next to any tool call worth guarding,
and trivially cheap next to an LLM round trip. It is not built for
bulk ETL: megabyte payloads will be dominated by the copy and the
regex scan. See [docs/limitations.md](../docs/limitations.md).
