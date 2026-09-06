from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.rate_limit import MaxUploadSizeMiddleware


def _build_test_app(max_bytes: int) -> FastAPI:
    app = FastAPI()
    app.add_middleware(MaxUploadSizeMiddleware, max_bytes=max_bytes)

    @app.post("/echo")
    def echo():
        return {"ok": True}

    return app


def test_upload_under_limit_passes_through():
    client = TestClient(_build_test_app(max_bytes=1000))
    response = client.post("/echo", content=b"x" * 500, headers={"Content-Length": "500"})
    assert response.status_code == 200


def test_upload_over_limit_is_rejected_with_413():
    client = TestClient(_build_test_app(max_bytes=1000))
    response = client.post("/echo", content=b"x" * 2000, headers={"Content-Length": "2000"})
    assert response.status_code == 413


def test_missing_content_length_passes_through():
    # Starlette's TestClient always sets Content-Length for a bytes body, so this mostly
    # documents the (permissive) behavior when a client omits it entirely — the request
    # isn't rejected up front; FastAPI's own body-size handling is the next line of defense.
    client = TestClient(_build_test_app(max_bytes=1000))
    response = client.post("/echo")
    assert response.status_code == 200


def test_malformed_content_length_is_rejected_not_crashed():
    # Regression test: int(content_length) used to run unguarded, so a
    # non-integer header (garbage, or a hand-crafted/malicious request)
    # raised an uncaught ValueError -- a request this middleware couldn't
    # even evaluate turned into a raw 500 instead of a clean 4xx.
    client = TestClient(_build_test_app(max_bytes=1000))
    response = client.post("/echo", content=b"x" * 10, headers={"Content-Length": "not-a-number"})
    assert response.status_code == 400
