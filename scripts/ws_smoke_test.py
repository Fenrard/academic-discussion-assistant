"""
One-off manual smoke test for WS /api/v1/ws/transcribe — not part of
the app, not imported anywhere. Registers/logs in a throwaway account
(auth is required now — see backend/core/security.py), then slices
recordings/lecture_preprocessed.wav into a couple of chunks (like
simulate_streaming.py) and drives the start -> binary chunks -> end
control flow over a real WebSocket, with the token as a ?token= query
param (the standard workaround for WS auth — see
backend/api/transcribe.py's docstring).

For the fuller REST + WS walkthrough (registration, async /transcribe
with polling, teacher enrollment, rate limiting, /metrics), see
scripts/v2_smoke_test.py instead.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

import requests
import websockets

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from simulate_streaming import split_into_chunks  # noqa: E402

BASE_URL = "http://127.0.0.1:8000/api/v1"
WS_URL = "ws://127.0.0.1:8000/api/v1/ws/transcribe"


def get_token() -> str:
    email = f"ws-smoke-test-{int(time.time())}@example.com"
    password = "wssmoketestpassword123"
    requests.post(f"{BASE_URL}/auth/register", json={"email": email, "password": password}).raise_for_status()
    response = requests.post(f"{BASE_URL}/auth/login", data={"username": email, "password": password})
    response.raise_for_status()
    return response.json()["access_token"]


async def main():
    token = get_token()

    input_path = REPO_ROOT / "recordings" / "lecture_preprocessed.wav"
    chunk_paths = split_into_chunks(input_path, chunk_duration_seconds=3.0)
    print(f"Split into {len(chunk_paths)} chunk(s): {[p.name for p in chunk_paths]}")

    async with websockets.connect(f"{WS_URL}?token={token}", max_size=None) as ws:
        await ws.send(json.dumps({
            "type": "start",
            "title": "WS smoke test",
            "consent_confirmed": True,
            "options": {"enable_vad": True},
        }))
        print("->", await ws.recv())

        for chunk_path in chunk_paths:
            await ws.send(chunk_path.read_bytes())
            response = json.loads(await ws.recv())
            print(f"-> chunk_result: text={response.get('text')!r} error={response.get('detail')}")

        await ws.send(json.dumps({"type": "end"}))
        print("-> session_ended:", await ws.recv())


if __name__ == "__main__":
    asyncio.run(main())
