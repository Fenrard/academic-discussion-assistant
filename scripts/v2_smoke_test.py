"""
One-off manual smoke test for the rearchitected API (auth + async
transcribe + teacher enrollment + WS). Not part of the app, not
imported anywhere — a runnable checklist. NOTE: with no
CELERY_BROKER_URL configured, tasks run in Celery's eager mode
(inline, synchronous) — this proves the request/response contracts and
persistence are correct, but does NOT demonstrate genuine non-blocking
concurrency, which needs a real broker + separate worker process this
sandbox has no way to run.
"""

import asyncio
import json
import time
from pathlib import Path

import requests
import websockets

BASE_URL = "http://127.0.0.1:8000/api/v1"
WS_URL = "ws://127.0.0.1:8000/api/v1/ws/transcribe"
# __file__-relative, not CWD-relative (unlike the "../recordings/..." literal this replaced) --
# works regardless of whether this script is launched from scripts/ or the repo root. Reproduced
# directly: the old literal raised FileNotFoundError when run as `python scripts/v2_smoke_test.py`
# from the repo root, since ".." then resolved to the repo root's own parent, not scripts/'s parent.
AUDIO_FILE = Path(__file__).resolve().parent.parent / "recordings" / "lecture_preprocessed.wav"


def poll_session(token: str, session_id: str, timeout_seconds: float = 60.0) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = requests.get(f"{BASE_URL}/sessions/{session_id}", headers=headers)
        response.raise_for_status()
        data = response.json()
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(1)
    raise TimeoutError(f"Session {session_id} did not complete within {timeout_seconds}s")


def main() -> None:
    email = f"smoketest-{int(time.time())}@example.com"
    password = "smoketestpassword123"

    print("== register ==")
    r = requests.post(f"{BASE_URL}/auth/register", json={"email": email, "password": password})
    print(r.status_code, r.json())
    assert r.status_code == 201

    print("== login ==")
    r = requests.post(f"{BASE_URL}/auth/login", data={"username": email, "password": password})
    print(r.status_code)
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    print("== unauthenticated request rejected ==")
    r = requests.get(f"{BASE_URL}/sessions")
    print(r.status_code)
    assert r.status_code == 401

    print("== list sessions (empty) ==")
    r = requests.get(f"{BASE_URL}/sessions", headers=headers)
    print(r.status_code, r.json())
    assert r.status_code == 200

    print("== POST /transcribe (async, poll) ==")
    with open(AUDIO_FILE, "rb") as audio_file:
        r = requests.post(
            f"{BASE_URL}/transcribe",
            headers=headers,
            files={"file": ("lecture.wav", audio_file, "audio/wav")},
            data={"title": "v2 smoke test", "consent_confirmed": "true", "enable_vad": "true"},
        )
    print(r.status_code, r.json())
    assert r.status_code == 202
    session_id = r.json()["session_id"]

    completed = poll_session(token, session_id)
    print("session completed:", completed["status"], "transcript:", completed["transcript_text"][:80])
    assert completed["status"] == "completed"
    assert completed["transcript_text"]

    print("== DELETE session ==")
    r = requests.delete(f"{BASE_URL}/sessions/{session_id}", headers=headers)
    print(r.status_code, r.json())
    assert r.status_code == 200

    print("== teacher enrollment (async, poll) ==")
    with open(AUDIO_FILE, "rb") as audio_file:
        r = requests.post(
            f"{BASE_URL}/teachers/enroll",
            headers=headers,
            files={"file": ("enroll.wav", audio_file, "audio/wav")},
            data={"name": "Test Teacher"},
        )
    print(r.status_code, r.json())
    assert r.status_code == 202
    teacher_id = r.json()["id"]

    for _ in range(60):
        r = requests.get(f"{BASE_URL}/teachers/{teacher_id}", headers=headers)
        if r.json()["status"] in ("ready", "failed"):
            break
        time.sleep(1)
    print("teacher status:", r.json())
    assert r.json()["status"] == "ready"

    print("== metrics endpoint ==")
    r = requests.get("http://127.0.0.1:8000/metrics")
    print(r.status_code, "content-length:", len(r.text))
    assert r.status_code == 200

    print("== WS with token ==")
    asyncio.run(ws_smoke_test(token))

    print("\nALL SMOKE TESTS PASSED")


async def ws_smoke_test(token: str) -> None:
    async with websockets.connect(f"{WS_URL}?token={token}", max_size=None) as ws:
        await ws.send(json.dumps({
            "type": "start",
            "title": "ws v2 smoke test",
            "consent_confirmed": True,
            "options": {"enable_vad": True},
        }))
        started = json.loads(await ws.recv())
        print("session_started:", started)
        assert started["type"] == "session_started"

        with open(AUDIO_FILE, "rb") as audio_file:
            await ws.send(audio_file.read())

        result = json.loads(await ws.recv())
        print("chunk_result:", {k: v for k, v in result.items() if k != "whisper_segments"})
        assert result["type"] == "chunk_result"

        await ws.send(json.dumps({"type": "end"}))
        ended = json.loads(await ws.recv())
        print("session_ended:", {k: v for k, v in ended.items() if k not in ("minutes",)})
        assert ended["type"] == "session_ended"
        assert ended["transcript"]


if __name__ == "__main__":
    main()
