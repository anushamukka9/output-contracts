"""Tests for the optional FastAPI middleware. Needs the http extra."""

import json

import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from fastapi.testclient import TestClient

from output_contracts.middleware import OutputContractMiddleware

TOOL_CONTRACT = {
    "type": "object",
    "properties": {
        "result": {"type": "string"},
        "api_key": {"type": "string", "secret": True},
    },
    "required": ["result", "api_key"],
}

LEAKY = {"result": "ok", "api_key": "sk-testkey123456789"}
BROKEN = {"result": 42, "api_key": "sk-testkey123456789"}


def build_app(on_violation="error", default=None):
    app = FastAPI()
    app.add_middleware(
        OutputContractMiddleware,
        contracts={"/tools": TOOL_CONTRACT},
        default=default,
        on_violation=on_violation,
    )

    @app.get("/tools/leaky")
    def leaky():
        return LEAKY

    @app.get("/tools/broken")
    def broken():
        return BROKEN

    @app.get("/tools/plain")
    def plain():
        return PlainTextResponse("just a string")

    @app.get("/tools/binary")
    def binary():
        return Response(content=b"\xff\xfe broken bytes", media_type="application/json")

    @app.get("/other/path")
    def other():
        return {"free": "as in untouched"}

    return app


@pytest.fixture()
def client():
    return TestClient(build_app())


def test_valid_json_redacts_and_sets_headers(client):
    r = client.get("/tools/leaky")
    assert r.status_code == 200
    body = r.json()
    assert body["result"] == "ok"
    assert body["api_key"] != LEAKY["api_key"]
    assert "REDACTED" in body["api_key"]
    assert "sk-testkey123456789" not in r.text
    assert r.headers["X-Output-Contracts-Valid"] == "true"
    assert int(r.headers["X-Output-Contracts-Redactions"]) >= 1


def test_invalid_json_returns_422_without_raw_leak(client):
    r = client.get("/tools/broken")
    assert r.status_code == 422
    body = r.json()
    assert body["detail"] == "output contract violation"
    assert body["path"] == "/tools/broken"
    assert body["errors"], "expected structured errors"
    assert any(e["path"] == "result" for e in body["errors"])
    # The offending value and the leaked secret must not appear anywhere.
    assert "sk-testkey123456789" not in r.text


def test_monitor_mode_passes_body_through_with_false_header():
    client = TestClient(build_app(on_violation="monitor"))
    r = client.get("/tools/broken")
    assert r.status_code == 200
    assert r.json() == BROKEN
    assert r.headers["X-Output-Contracts-Valid"] == "false"


def test_unmatched_path_passes_through_untouched(client):
    r = client.get("/other/path")
    assert r.status_code == 200
    assert r.json() == {"free": "as in untouched"}
    assert "X-Output-Contracts-Valid" not in r.headers


def test_default_contract_applies_to_unmatched_paths():
    client = TestClient(build_app(default=TOOL_CONTRACT))
    r = client.get("/other/path")
    # The payload has neither required field, so the default contract
    # rejects it in error mode.
    assert r.status_code == 422
    assert r.json()["path"] == "/other/path"


def test_non_json_response_passes_through(client):
    r = client.get("/tools/plain")
    assert r.status_code == 200
    assert r.text == "just a string"
    assert "X-Output-Contracts-Valid" not in r.headers


def test_undecodable_json_body_passes_through(client):
    r = client.get("/tools/binary")
    assert r.status_code == 200
    assert r.content == b"\xff\xfe broken bytes"


def test_longest_prefix_match_wins():
    contract_a = {
        "type": "object",
        "properties": {"a": {"type": "integer"}},
        "required": ["a"],
    }
    contract_b = {
        "type": "object",
        "properties": {"b": {"type": "integer"}},
        "required": ["b"],
    }
    app = FastAPI()
    app.add_middleware(
        OutputContractMiddleware,
        contracts={"/tools": contract_a, "/tools/search": contract_b},
    )

    @app.get("/tools/search")
    def search():
        return {"b": 2}  # valid only under contract B

    @app.get("/tools/run")
    def run():
        return {"a": 1}  # valid only under contract A

    client = TestClient(app)
    assert client.get("/tools/search").status_code == 200
    assert client.get("/tools/run").status_code == 200


# --- SSE tests -----------------------------------------------------------


def build_sse_app(on_violation="error"):
    app = FastAPI()
    app.add_middleware(
        OutputContractMiddleware,
        contracts={"/events": TOOL_CONTRACT},
        on_violation=on_violation,
    )

    @app.get("/events")
    def events():
        async def gen():
            yield b": keep-alive\n\n"
            # A frame deliberately split across two chunks.
            first = b'data: {"result": "one", "api_key": "sk-te'
            yield first
            yield b'stkey123456789"}\n\n'
            # Invalid event, then one more good event after it.
            yield b'data: {"result": 123, "api_key": "x"}\n\n'
            yield b'data: {"result": "three", "api_key": "x"}\n\n'

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


def _read_stream(client, path="/events"):
    with client.stream("GET", path) as r:
        assert r.status_code == 200
        return r.read().decode("utf-8")


def test_sse_redacts_split_frames_and_passes_comments():
    client = TestClient(build_sse_app(on_violation="monitor"))
    text = _read_stream(client)
    assert ": keep-alive" in text
    assert "sk-testkey123456789" not in text
    assert "REDACTED" in text


def test_sse_violation_error_mode_emits_event_and_terminates():
    client = TestClient(build_sse_app(on_violation="error"))
    text = _read_stream(client)
    frames = [f for f in text.replace("\r\n", "\n").split("\n\n") if f]
    violation = next(f for f in frames if f.startswith("event: contract-violation"))
    data_line = next(line for line in violation.splitlines() if line.startswith("data:"))
    payload = json.loads(data_line[len("data:") :])
    assert payload["path"] == "/events"
    assert payload["errors"], "expected structured errors in the violation frame"
    # The stream stops at the violation: the third event never arrives.
    assert '"three"' not in text


def test_sse_violation_monitor_mode_passes_through_with_note():
    client = TestClient(build_sse_app(on_violation="monitor"))
    text = _read_stream(client)
    # The bad event passes through, flagged by a comment frame.
    assert '"result": 123' in text
    assert "contract violation" in text
    # And the stream keeps going after it.
    assert '"three"' in text


def test_sse_non_json_data_passes_through():
    app = FastAPI()
    app.add_middleware(OutputContractMiddleware, contracts={"/events": TOOL_CONTRACT})

    @app.get("/events")
    def events():
        async def gen():
            yield b"data: [DONE]\n\n"
            yield b"data: not json at all\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    text = _read_stream(TestClient(app))
    assert "data: [DONE]" in text
    assert "data: not json at all" in text


def test_bad_on_violation_rejected():
    app = FastAPI()
    with pytest.raises(ValueError, match="on_violation"):
        OutputContractMiddleware(app, on_violation="explode")
