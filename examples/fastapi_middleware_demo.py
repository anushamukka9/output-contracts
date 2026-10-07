"""FastAPI demo: one middleware guarding every tool response.

Two JSON tool endpoints (one leaks a fake API key, one is clean), one
SSE endpoint streaming tool events, all guarded by
OutputContractMiddleware.

Run: uvicorn examples.fastapi_middleware_demo:app --reload
(uvicorn is NOT a dependency of output-contracts; install it yourself
with: pip install uvicorn)
"""

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from output_contracts.middleware import OutputContractMiddleware

# A plain dict works here too; the middleware builds a Contract from it.
TOOL_CONTRACT = {
    "type": "object",
    "properties": {
        "tool": {"type": "string"},
        "result": {"type": "string"},
        "api_key": {"type": "string", "secret": True},
    },
    "required": ["tool", "result"],
    "additional_properties": False,
}

app = FastAPI(title="output-contracts middleware demo")
app.add_middleware(
    OutputContractMiddleware,
    contracts={"/tools": TOOL_CONTRACT},
    default=TOOL_CONTRACT,
    on_violation="error",
)


@app.get("/tools/user_lookup")
def user_lookup():
    # Imagine a tool that accidentally echoes a debug credential.
    return {
        "tool": "user_lookup",
        "result": "found user u-123",
        "api_key": "sk-fake-key-for-demo-9876543210",
    }


@app.get("/tools/search")
def search():
    return {"tool": "search", "result": "3 tickets matched"}


@app.get("/tools/broken")
def broken():
    # Wrong type on purpose: the middleware answers 422 and the raw
    # payload never leaves.
    return {"tool": "broken", "result": 42}


@app.get("/events")
def events():
    async def gen():
        yield 'data: {"tool": "user_lookup", "result": "done"}\n\n'
        # The secret in this frame gets redacted before it streams out.
        yield 'data: {"tool": "search", "result": "ok", "api_key": "sk-fake-key-for-demo-9876543210"}\n\n'
        yield ": heartbeat\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    # uvicorn is not a dependency of output-contracts; install it with
    # pip install uvicorn, then run this file.
    import uvicorn  # type: ignore[import-not-found]

    uvicorn.run(app, host="127.0.0.1", port=8000)
