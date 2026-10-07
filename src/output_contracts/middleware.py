"""Optional FastAPI middleware: validate and redact every tool response.

This module is the HTTP layer on top of the zero-dependency core. It
needs FastAPI (installed as the ``http`` extra: ``pip install
output-contracts[http]``) and is deliberately NOT imported by
``output_contracts/__init__.py``, so importing the core never pulls in
a web framework.

Typical setup, one line per app:

    from output_contracts.middleware import OutputContractMiddleware

    app.add_middleware(
        OutputContractMiddleware,
        contracts={"/tools/search": search_contract},
        default=fallback_contract,
        on_violation="error",
    )
"""

from __future__ import annotations

import codecs
import json
from collections.abc import AsyncIterator
from typing import Any

try:
    from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response, StreamingResponse
except ImportError as exc:  # pragma: no cover - exercised by missing-extra docs
    raise ImportError(
        "OutputContractMiddleware needs FastAPI. Install the optional extra: "
        "pip install output-contracts[http]"
    ) from exc

from output_contracts.validate import Contract

VALID_HEADER = "X-Output-Contracts-Valid"
REDACTIONS_HEADER = "X-Output-Contracts-Redactions"


def _to_contract(value: Contract | dict[str, Any]) -> Contract:
    if isinstance(value, Contract):
        return value
    return Contract(value)


def _match_contract(contracts: dict[str, Contract], path: str) -> Contract | None:
    """Exact path match first, then longest matching path prefix."""
    if path in contracts:
        return contracts[path]
    best: Contract | None = None
    best_len = -1
    for prefix, contract in contracts.items():
        if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
            if len(prefix) > best_len:
                best = contract
                best_len = len(prefix)
    return best


def _extract_frames(text: str) -> tuple[list[str], str]:
    """Split complete SSE frames off the head of text.

    Frames end at a blank line. Anything after the last blank line is a
    partial frame and stays in the buffer until the rest arrives.
    """
    normalized = text.replace("\r\n", "\n")
    parts = normalized.split("\n\n")
    complete = [part for part in parts[:-1] if part]
    return complete, parts[-1]


def _split_data_lines(frame: str) -> tuple[list[str], list[str]]:
    others: list[str] = []
    data: list[str] = []
    for line in frame.split("\n"):
        if line.startswith("data:"):
            value = line[len("data:") :]
            data.append(value[1:] if value.startswith(" ") else value)
        else:
            others.append(line)
    return others, data


def _violation_frame(path: str, report_errors: list[dict[str, Any]]) -> str:
    payload = json.dumps({"path": path, "errors": report_errors})
    return f"event: contract-violation\ndata: {payload}"


class OutputContractMiddleware(BaseHTTPMiddleware):
    """Validate and redact every tool response in a FastAPI agent backend.

    JSON responses are validated against the matched contract, redacted,
    and re-serialized. Server-sent event streams are validated frame by
    frame, so long-running tool streams get the same treatment. Anything
    else passes through untouched.

    The middleware never crashes the app: a body it cannot decode or a
    validation error it cannot build a response for falls back to
    passing the response through untouched.
    """

    def __init__(
        self,
        app: Any,
        contracts: dict[str, Contract | dict[str, Any]] | None = None,
        default: Contract | dict[str, Any] | None = None,
        on_violation: str = "error",
    ) -> None:
        if on_violation not in ("error", "monitor"):
            raise ValueError(f"on_violation must be 'error' or 'monitor', got {on_violation!r}")
        super().__init__(app)
        self.contracts = {path: _to_contract(c) for path, c in (contracts or {}).items()}
        self.default = _to_contract(default) if default is not None else None
        self.on_violation = on_violation

    def _resolve(self, path: str) -> Contract | None:
        return _match_contract(self.contracts, path) or self.default

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        contract = self._resolve(request.url.path)
        response = await call_next(request)
        if contract is None:
            return response
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return self._handle_sse(response, contract, request.url.path)
        if "application/json" in content_type:
            return await self._handle_json(response, contract, request.url.path)
        return response

    async def _read_body(self, response: Response) -> bytes:
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        return body

    def _passthrough_headers(self, response: Response) -> dict[str, str]:
        return {
            name.decode("latin-1"): value.decode("latin-1")
            for name, value in response.raw_headers
            if name.lower() != b"content-length"
        }

    async def _handle_json(self, response: Response, contract: Contract, path: str) -> Response:
        body = await self._read_body(response)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            # Cannot make sense of the body: hand it back untouched.
            return Response(
                content=body,
                status_code=response.status_code,
                headers=self._passthrough_headers(response),
                media_type=response.headers.get("content-type"),
            )
        report = contract.validate(payload)
        headers = self._passthrough_headers(response)
        headers[VALID_HEADER] = "true" if report.valid else "false"
        if report.valid:
            headers[REDACTIONS_HEADER] = str(len(report.redactions))
            return JSONResponse(
                content=report.clean,
                status_code=response.status_code,
                headers=headers,
            )
        if self.on_violation == "monitor":
            return JSONResponse(
                content=payload,
                status_code=response.status_code,
                headers=headers,
            )
        return JSONResponse(
            content={
                "detail": "output contract violation",
                "path": path,
                "errors": report.errors,
                "redactions": report.redactions,
            },
            status_code=422,
            headers=headers,
        )

    def _handle_sse(self, response: Response, contract: Contract, path: str) -> Response:
        passthrough = self._passthrough_headers(response)

        async def stream() -> AsyncIterator[bytes]:
            decoder = codecs.getincrementaldecoder("utf-8")()
            buffer = ""
            terminated = False
            try:
                async for chunk in response.body_iterator:
                    try:
                        buffer += decoder.decode(chunk)
                    except UnicodeDecodeError:
                        # Undecodable chunk: drop it rather than corrupt the
                        # stream, and keep the rest flowing.
                        continue
                    frames, buffer = _extract_frames(buffer)
                    for frame in frames:
                        emitted = self._process_frame(frame, contract, path)
                        for out in emitted:
                            yield (out + "\n\n").encode("utf-8")
                        if self._terminated(emitted):
                            terminated = True
                            break
                    if terminated:
                        break
                if not terminated:
                    tail = decoder.decode(b"", True)
                    if tail:
                        buffer += tail
                    frames, _ = _extract_frames(buffer + "\n\n")
                    for frame in frames:
                        for out in self._process_frame(frame, contract, path):
                            yield (out + "\n\n").encode("utf-8")
            except Exception:
                # Streaming must never hang or crash: if anything goes
                # wrong mid-stream, the cleanest honest move is to stop.
                return

        return StreamingResponse(
            stream(),
            status_code=response.status_code,
            headers=passthrough,
            media_type="text/event-stream",
        )

    def _terminated(self, emitted: list[str]) -> bool:
        return any(frame.startswith("event: contract-violation") for frame in emitted)

    def _process_frame(self, frame: str, contract: Contract, path: str) -> list[str]:
        others, data_lines = _split_data_lines(frame)
        if not data_lines:
            # Comments, heartbeats, and event-only frames pass through.
            return [frame]
        payload_text = "\n".join(data_lines)
        try:
            payload = json.loads(payload_text)
        except ValueError:
            # Non-JSON data (e.g. a "[DONE]" sentinel) passes through.
            return [frame]
        report = contract.validate(payload)
        if report.valid:
            rebuilt = "\n".join(others + [f"data: {json.dumps(report.clean)}"])
            return [rebuilt]
        if self.on_violation == "monitor":
            note = f": output-contracts: contract violation at {path}, passed through"
            return [frame, note]
        return [_violation_frame(path, report.errors)]
