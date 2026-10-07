# FastAPI middleware

One middleware that validates and redacts every tool response your
FastAPI agent backend sends. Drop it in and every JSON endpoint and
every SSE stream gets the same guard your wrapped tools already have.

This is an optional layer: it lives in
`output_contracts.middleware` (not imported by the top-level package,
so the core stays importable without FastAPI) and needs the `http`
extra:

```bash
pip install "output-contracts[http]"
```

## Quickstart

```python
from fastapi import FastAPI
from output_contracts.middleware import OutputContractMiddleware

contract = {
    "type": "object",
    "properties": {
        "result": {"type": "string"},
        "api_key": {"type": "string", "secret": True},
    },
    "required": ["result"],
}

app = FastAPI()
app.add_middleware(
    OutputContractMiddleware,
    contracts={"/tools/search": contract},  # plain dicts are fine
    on_violation="error",
)
```

Now `/tools/search` responses are validated against your contract
before they leave the server. A valid response goes out redacted, with
`X-Output-Contracts-Valid: true` and `X-Output-Contracts-Redactions: N`
headers. An invalid one never leaves: the client gets a 422 with
structured errors instead.

## Constructor reference

```python
OutputContractMiddleware(
    app,
    contracts=None,   # dict mapping route path -> Contract or plain dict schema
    default=None,      # Contract/dict applied when no path matches; None = passthrough
    on_violation="error",  # "error" or "monitor"
)
```

**Path matching.** Exact path first, then longest matching path
prefix, so `"/tools/search"` beats `"/tools"`. A prefix only matches
on a path boundary: `"/tools"` covers `"/tools/run"` but not
`"/toolshed"`. Paths with no match fall back to `default`; with no
default they pass through untouched.

**on_violation="error"** (the default) fails closed. Bad payloads
become a 422:

```json
{
  "detail": "output contract violation",
  "path": "/tools/search",
  "errors": [{"path": "result", "message": "...", "expected": "...", "actual": "..."}],
  "redactions": [{"path": "api_key", "kind": "declared_secret"}]
}
```

**on_violation="monitor"** passes the original body through with
`X-Output-Contracts-Valid: false` on the response. Use it when you are
rolling contracts out and want to see what would break before you
start blocking.

## JSON mode

Responses whose content type contains `application/json` are parsed,
validated with `Contract.validate`, and re-serialized from
`report.clean`. That means the response the client receives is the
redacted copy, even in monitor mode for valid payloads. Secrets are
redacted before serialization, so a leaked `sk-...` key never appears
in the wire bytes.

If the body cannot be decoded as UTF-8 or is not valid JSON, the
middleware passes the response through untouched rather than guessing.

## SSE mode

Responses with `text/event-stream` are handled frame by frame. Frames
end at blank lines, and a frame split across TCP chunks is buffered
until its terminator arrives, so chunking never breaks validation.

- Frames with a `data:` line that parses as JSON are validated and
  re-emitted with the redacted JSON.
- Comments (`:` lines), heartbeats, `event:`/`id:`-only frames, and
  non-JSON data (like a `[DONE]` sentinel) pass through untouched.
- Multi-line `data:` payloads are joined and re-emitted as one `data:`
  line, which the SSE spec treats identically.

On an invalid JSON event with `on_violation="error"`, the middleware
emits an `event: contract-violation` frame carrying the path and the
structured errors, then terminates the stream. The remainder is
dropped: once a tool stream goes off-contract, downstream consumers
should not trust what follows it. With `"monitor"`, the bad event
passes through and a `: comment` frame noting the violation is emitted
after it.

## Honest limitations

- Buffering a frame adds latency: a frame is not forwarded until its
  blank-line terminator arrives. SSE frames must arrive whole
  eventually; an unbounded frame with no terminator is buffered until
  the stream ends.
- Binary and non-JSON, non-SSE responses are not inspected at all.
- The middleware sees response bodies only, never request bodies or
  tool call parameters. Guard the parameters with `@enforce_contract`
  on the tool itself.
- A body that cannot be decoded is passed through untouched rather
  than blocked. If your threat model needs fail-closed on undecodable
  bodies, wrap those endpoints separately.
- Headers are re-emitted as a dict, so duplicate `Set-Cookie` headers
  collapse to one. If your endpoints set multiple cookies, set them
  outside the middleware's reach.
