# output-contracts

Declare the JSON your agent tools must return. Get structured
validation errors and redacted secrets BEFORE the model ever sees the
output. Zero runtime dependencies.

## Why this exists

I built llm-sentinel to guard what goes INTO the model: prompts get
scanned for injection, secrets, and PII before anything is sent. That
covered half the problem. The other half is what comes OUT of tools.

Every agent I run calls tools that return structured JSON: user
lookups, search results, ticket details. And every one of those
payloads is a chance for two things to go wrong. The tool returns
something malformed and the agent hallucinates around the gap, or the
tool returns something real and sensitive - an API key in a debug
field, a customer's SSN in a support ticket - and it lands in the
model's context window, then in the next tool call, then who knows
where.

Nobody was guarding the tool outputs. So I built the other half.

## Quickstart

```bash
pip install output-contracts
```

```python
from output_contracts import Contract, enforce_contract

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
    },
    "required": ["user"],
})

@enforce_contract(contract)
def get_user(user_id: str) -> dict:
    ...  # whatever the tool does

user = get_user("u-123")
# user["user"]["email"] is now "[REDACTED:declared_secret]"
```

Thirty seconds, start to finish. The wrapper validates the output,
redacts secrets, and hands you the clean copy. If the output breaks
the contract, it raises `ContractViolation` and the raw output never
leaves the tool. See [docs/quickstart.md](docs/quickstart.md) and
[examples/quickstart.py](examples/quickstart.py).

## What it does

**Schema validation.** Plain-dict schemas: objects, arrays, strings
(with length, pattern, enum, and email/uuid/date/datetime/uri
formats), integers, numbers, booleans, null, and `any_of`. Errors come
back structured with paths like `user.email` and `items[2].token`.
Schema mistakes (unknown type names, bad keys) fail at contract build
time, not at validate time.

**Redaction.** Two layers. Fields marked `"secret": true` are always
redacted, no matter what they look like. Everything else gets a global
scan: emails, US and international phone numbers, SSNs, credit cards
(Luhn-checked), API keys (`sk-`, `ghp_`, `xoxb-`, `AKIA`, 40-char
hex, Bearer tokens, JWTs, private keys), IPv4 addresses, and
high-entropy opaque tokens. Two styles: full (`[REDACTED:email]`) or
partial (everything but the last 4 characters masked).

## FastAPI middleware

If your tools sit behind a FastAPI backend, one middleware guards
every response: JSON endpoints get validated and redacted before they
leave the server, and SSE streams get validated frame by frame.

```bash
pip install "output-contracts[http]"
```

```python
from output_contracts.middleware import OutputContractMiddleware

app.add_middleware(
    OutputContractMiddleware,
    contracts={"/tools/search": contract},
    on_violation="error",  # or "monitor" while you roll contracts out
)
```

Valid responses go out redacted with `X-Output-Contracts-Valid: true`.
Invalid ones fail closed: a 422 with structured errors, and the raw
payload never leaves. Streaming tool events are redacted per frame;
on a violation the stream emits a `contract-violation` event and stops.
See [docs/middleware.md](docs/middleware.md) and
[examples/fastapi_middleware_demo.py](examples/fastapi_middleware_demo.py).

## CLI

```bash
output-contracts validate --contract contract.json --input output.json
output-contracts redact --input output.json --style partial
output-contracts check --contract contract.json --input output.json   # CI mode: exit 2 on invalid
```

## Benchmarks

Measured on this machine (see [benchmarks/results.md](benchmarks/results.md)
for the setup). The benchmark payload is a realistic nested tool
output with a declared secret, a phone number, and an API key in it.

| Benchmark | Result |
|---|---|
| Validate realistic payload (validate + redact) | 3,601 ops/sec |
| scan_and_redact only | 5,386 ops/sec |
| Validate trivial object | 61,617 ops/sec |
| Validate invalid payload (fails fast) | 3,524 ops/sec |

## Honest limitations

- Detection is regex and heuristics, not understanding. A secret in a
  format nobody listed passes through. See the full list in
  [docs/limitations.md](docs/limitations.md).
- Luhn-passing digit runs are not always credit cards; long order
  numbers can false-positive.
- `any_of` failures report one error, not the per-option detail.
- Validation deep-copies and walks the payload twice. Fine per tool
  call, not built for bulk ETL.

## Companion

[llm-sentinel](https://github.com/anushamukka9/llm-sentinel) guards
prompts going in. This guards tool outputs going out. Together they
cover both sides of the model.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Small and focused stays small
and focused: new detectors need adversarial tests, every feature
documents what it cannot do, and there are no em-dashes in this repo.

## License

MIT. See [LICENSE](LICENSE).
