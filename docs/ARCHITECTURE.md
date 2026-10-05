# Architecture

> Written 2026-09-15 as part of a full reverse-engineering documentation pass. Every claim below
> is traced to a specific file — see the citation after each statement. Start at `CLAUDE.md` Part 1
> if you haven't already; this document goes one level deeper on the same picture.

## The two-process split, and why it exists

The single most important architectural fact about this backend: **it is two separate operating-
system processes, not one.**

1. **The API tier** — `uvicorn backend.main:app`. Handles every HTTP request and every WebSocket
   connection. Reads and writes the database directly for anything that isn't ML inference
   (registering a user, listing sessions, reading back a finished transcript). **Never runs a
   machine-learning model.** Verified directly this pass: importing `backend.main` in a fresh
   Python process pulls in zero of `torch`/`faster_whisper`/`pyannote`/`speechbrain`/`silero_vad`.
2. **The worker tier** — `celery -A backend.worker.celery_app worker`. A completely separate
   process (can even be a separate machine) that does the actual audio processing. This is the
   only process that ever imports the ML libraries above.

**Why the split exists** (`backend/main.py`'s own docstring, and `backend/worker/celery_app.py`'s):
originally, this was one process, and an `async def` FastAPI route ran the ML pipeline inline.
FastAPI's event loop is single-threaded for `async def` code — a CPU-bound Whisper transcription
call running inside a route handler blocks that one thread, so *no other request* (not even an
unrelated `/health` check) can be served until it finishes. That's a real, measured bug from this
project's own history (`CLAUDE.md` Part 2, "Production Architecture (Round 3)"), not a hypothetical
concern. The fix is the standard one: hand CPU-bound work to a task queue (Celery) backed by a
separate process pool, and let the API process stay purely I/O-bound.

## How the two processes talk to each other

Two channels, both flowing through the same optional Redis instance (or, if there's no Redis
configured, entirely in-process):

- **API → Worker: Celery task enqueue.** `backend/api/transcribe.py`'s WebSocket handler calls
  `transcribe_chunk_task.delay(...)` for every binary chunk it receives — this returns immediately;
  it does not wait for the task to run. If `CELERY_BROKER_URL` is unset, Celery runs in **eager
  mode**: the task body executes synchronously, in the same process, the moment `.delay()` is
  called (`backend/worker/celery_app.py`: `task_always_eager=settings.celery_broker_url is None`).
  This is a real, documented Celery testing pattern, not a hack — it's what lets this whole system
  run with zero extra infrastructure installed. When a real Redis/Memurai instance is configured,
  `.delay()` instead serializes the task and pushes it onto a Redis list; a genuinely separate
  worker process picks it up whenever it's free.
- **Worker → API: pub/sub.** When a worker task finishes a chunk, it calls `publish_sync(f"session:
  {id}:results", result_dict)` (`backend/core/pubsub.py`). The API tier's WebSocket handler has a
  background coroutine (`listen_results()` in `backend/api/transcribe.py`) subscribed to that exact
  channel; the moment a message arrives, it's forwarded straight over the live WebSocket to the
  phone. Same eager/real-Redis duality as above: with no Redis configured, `pubsub.py` uses an
  in-process `asyncio.Queue` per channel instead of real pub/sub — this is a *faithful* stand-in
  specifically because eager mode guarantees the "worker" and the "API" code are running in the
  same process/thread in that configuration; it would not be a faithful stand-in if eager mode
  weren't also active.

**One subtlety worth internalizing:** in eager mode, the entire round trip — chunk arrives over
the WebSocket → task runs synchronously → result is pushed onto the in-process queue → the
`listen_results()` loop picks it up → sent back to the phone — all happens before the WebSocket
handler's `receive()` call returns for the *next* chunk. In real (non-eager) mode, chunk N+1 can
arrive and get enqueued while chunk N is still being processed by a different OS process entirely.
Both modes are correctness-tested (`tests/test_tasks.py` covers out-of-order completion explicitly),
but they have very different performance characteristics — see `docs/ML_PIPELINE.md` §Performance.

## Full architecture diagram

See `CLAUDE.md` Part 1B for the box diagram. The prose version, traced through actual function
calls:

```
android/lib/screens/recording/live_recording_screen.dart
  _start() → WsTranscribeClient.connect() → wss://<host>/api/v1/ws/transcribe?token=<JWT>
  _beginStreamingAudio() → record package's startStream() → PcmChunker.add() → LocalVad.hasSpeech()
    gates each chunk → WsTranscribeClient.sendChunk(wavBytes) [binary WS frame]

backend/api/transcribe.py: transcribe_stream()
  receive_chunks() loop: each binary frame → transcribe_chunk_task.delay(session_id, chunk_index,
    base64(bytes), pipeline_options, enrolled_teacher_embeddings)
  listen_results() loop (concurrent, via asyncio.gather): subscribed to session:{id}:results,
    forwards each message to the WebSocket as JSON

backend/worker/tasks.py: transcribe_chunk_task()
  write_temp_audio() → backend/services/audio_service.py: run_pipeline()
    ingest_audio() → clean_audio() → detect_speech() → transcribe_audio() [+ glossary.apply() per
    segment] → [diarize_audio() + merge_transcript_with_speakers(), if enabled] →
    [apply_teacher_verification(), if enabled]
  session_service.append_chunk_result() → writes to SessionRecord.chunk_results (JSON column),
    recomputes transcript_text/transcript_segments as the longest CONTIGUOUS prefix by chunk index
    (so an out-of-order-arriving chunk never makes text appear out of sequence)
  publish_sync("session:{id}:results", {...}) → picked up by the API tier's listen_results() above

  [client sends the "end" control frame] →
backend/api/transcribe.py: finalize_and_close()
  session_service.finalize_session() — RUNS IN THE API PROCESS, not the worker:
    keyword_service.extract_keywords(keyword_service.build_weighted_text(segments))
    minutes_service.generate_minutes(segments, keywords, ...)
  → one final "session_ended" WS message: {transcript, keywords, minutes}

android/lib/screens/recording/live_recording_screen.dart: _handleWsMessage()
  on SessionEndedMessage → Navigator pushes TranscriptScreen(sessionId)
```

**Why minutes generation runs in the API process, not the worker:** it's cheap. TextRank
(`networkx`) and the rule-based minutes generator are pure Python with no heavy ML dependency —
`requirements-api.txt` includes `networkx` specifically for this reason (its own header comment
says so explicitly). Routing this through the worker tier and back would add a round trip for no
benefit; running it inline in the API process at the one moment it's needed (session finalize, not
per-chunk) doesn't reintroduce the original blocking-event-loop problem because it's fast enough
not to matter in practice, and it's a one-time cost per session rather than per chunk.

## The three other request shapes (not the WS streaming path)

- **Whole-file upload:** `POST /api/v1/transcribe` (multipart form) — `backend/api/transcribe.py:
  transcribe_file()`. Creates a `SessionRecord` synchronously, writes the upload to a temp file,
  enqueues `transcribe_file_task.delay(...)`, returns `202 Accepted` immediately. The client is
  expected to poll `GET /api/v1/sessions/{id}` until `status != "processing"`
  (`android/lib/core/polling.dart: pollUntil()` is the client-side helper for this pattern — also
  used for teacher-enrollment polling).
- **Teacher enrollment:** `POST /api/v1/teachers/enroll` — same async pattern: create a `"pending"`
  row synchronously, enqueue `enroll_teacher_task.delay(...)`, client polls `GET /api/v1/teachers/
  {id}` for `status: "ready"|"failed"`.
- **Everything else (auth, listing sessions/teachers, reading a finished session, exporting
  minutes, deleting)** — plain synchronous FastAPI routes, no Celery involvement at all, since none
  of it touches an ML model.

## Data flow workflows, traced end to end

### Workflow A — User opens the app

`android/lib/main.dart` → `ScaitaleApp` (`android/lib/app.dart`) constructs an `AuthController`
(`android/lib/core/auth_controller.dart`) that checks `flutter_secure_storage` for a previously
saved JWT. `MaterialApp(home: auth.isAuthenticated ? HomeScreen() : LoginScreen())` — the visible
screen is a direct function of that one boolean, rebuilt whenever `AuthController.notifyListeners()`
fires (login, logout, or a forced logout from a 401 response anywhere in the app). If authenticated,
`HomeScreen.initState()` calls `_load()` → `ApiClient.listSessions()` → `GET /api/v1/sessions` →
`session_service.list_sessions()` → one row per `SessionRecord` owned by this user, newest first.

### Workflow B — User records audio

`HomeScreen`'s FAB → pushes `LiveRecordingScreen`. User checks the consent checkbox (required —
the backend refuses to create a session without `consent_confirmed=true`, see `backend/models/
session.py`'s comment on that field) and taps "Start recording". `_start()` connects the WebSocket
first (`WsTranscribeClient.connect()`), sends a `start` JSON control frame
(`{"type":"start","title":...,"options":{...},"consent_confirmed":true}`), and only begins actually
streaming microphone audio once the server replies with `session_started` — see Workflow C.

### Workflow C — Audio is sent to the backend

Once `session_started` arrives, `_beginStreamingAudio()` calls the `record` package's
`startStream()` (config: PCM16, 16000Hz, mono — matching `SAMPLE_RATE` in `backend/core/config.py`
exactly, so no resampling is needed at the phone). Each raw PCM callback is fed into
`PcmChunker.add()`, which buffers until it has a full `chunk_duration_seconds`-sized block, wraps
it as a self-contained WAV (`wav_encoder.dart` — the `record` package's stream is headerless PCM,
so a RIFF header has to be added client-side for the server's FFmpeg step to parse each chunk as a
standalone file), and gates it through `LocalVad.hasSpeech()` (with a 1-chunk hangover so trailing
speech isn't clipped at a chunk boundary, and a 30-second keep-alive floor so a long silent stretch
doesn't let the WebSocket sit fully idle long enough for a NAT/proxy timeout to kill it). Each
chunk that passes the gate goes out as one binary WebSocket frame.

### Workflow D — Backend processes audio

See "Full architecture diagram" above — `transcribe_chunk_task` → `run_pipeline()`.

### Workflow E — Speech recognition occurs

Inside `run_pipeline()`, after denoise/VAD: `transcribe_audio()` (`backend/services/
audio_service.py`) iterates the VAD-detected speech spans, runs `faster_whisper.WhisperModel.
transcribe()` on each independently (no forced language — auto-detected per span), and immediately
applies `glossary.apply()` to each resulting segment's text before it's added to the result.

### Workflow F — Speaker identification/diarization occurs

Two genuinely independent mechanisms, both optional, neither depends on the other:
- **Diarization** (`enable_diarization`, off by default): `diarization_service.diarize_audio()`
  runs pyannote, producing generic `"Speaker A"/"Speaker B"` labels attached to Whisper segments by
  time-overlap (`merge_transcript_with_speakers()`).
- **Teacher verification** (`enable_teacher_verification`): `apply_teacher_verification()` slices
  the waveform by each Whisper segment's own timestamps (not by any diarized speaker turn), extracts
  a SpeechBrain ECAPA embedding for that slice, and compares it by cosine similarity against every
  enrolled teacher's stored embedding. Best match wins; result is `is_teacher`/`teacher_name`/
  `confidence` on the segment.

### Workflow G — Language/code-switching processing occurs

This happens *inside* Workflow E, not as a separate stage: `glossary.apply(segment.text)` runs the
moment each Whisper segment is decoded (`backend/services/glossary_service.py`), correcting known
Hiligaynon/Filipino/English terms via a case-insensitive, case-preserving regex substitution.

### Workflow H — Summarization/minutes generation occurs

Only at session finalize (`session_service.finalize_session()`, called from the API process when
the `"end"` control frame arrives — see above), over the *entire* session's transcript, never per
chunk: `keyword_service.extract_keywords()` (TextRank) → `minutes_service.generate_minutes()`
(silence-gap topic grouping, teacher-prioritized key-point ranking, regex-pattern definitions and
action-item detection).

### Workflow I — Results return to Flutter

Two paths, matching the two request shapes: for streaming, each `chunk_result` WS message updates
`LiveRecordingScreen`'s `_liveTranscript` state (rendered as one continuously-growing text block,
not per-line timed captions), and the final `session_ended` message triggers navigation to
`TranscriptScreen`. For a whole-file upload, `TranscriptScreen`'s own `_load()` polls `GET /sessions/
{id}` until processing completes.

### Workflow J — User exports/saves results

`MinutesScreen`'s share-icon menu → `ApiClient.exportMinutes(sessionId, format: "markdown"|"txt")`
→ `GET /api/v1/sessions/{id}/minutes/export?format=...` → `backend/api/minutes.py:
_render_minutes()` builds the text → returned as a `PlainTextResponse` with a `Content-Disposition:
attachment` header → the Flutter client reads the response body and hands it to `SharePlus.instance.
share(ShareParams(text: body, ...))`, which opens Android's native share sheet. **Note:** this
shares the content as text, not as an attached file with the `.md`/`.txt` extension the server's
header specifies — depending on the destination app the user picks, it may land as inline pasted
text rather than a discrete file.

## Contracts — what other parts of the system depend on, and must not change casually

| Contract | Defined in | Also depended on by | What breaks if you change it without updating both sides |
|---|---|---|---|
| WebSocket message `type` values (`start`, `chunk_result`, `error`, `session_started`, `session_ended`) | `backend/api/transcribe.py` (server-side sends), `backend/schemas/session.py` | `android/lib/models/ws_messages.dart`'s `fromJson()` switch, `live_recording_screen.dart`'s `_handleWsMessage()` switch | An unrecognized `type` string silently falls into no matching Dart `case` — Dart's exhaustive-switch-on-sealed-class pattern here means a genuinely new type needs a new case added on the client, or messages of that type are simply never handled |
| `PipelineOptions` field names (`enable_denoise`, `enable_vad`, `enable_diarization`, `enable_teacher_verification`, `num_speakers`, `beam_size`, `chunk_duration_seconds`) | `backend/schemas/pipeline.py` | `android/lib/models/pipeline_config.dart`'s `toJson()` — field names must match **exactly** (snake_case, not camelCase) since the backend is stateless and receives concrete values, never preset names | A renamed field on either side means that setting silently reverts to its Pydantic default rather than erroring — e.g. rename `enable_denoise` server-side without updating the client and every session silently runs with denoise off, with no error anywhere |
| `SUPPORTED_EXTENSIONS` | Duplicated in `backend/services/audio_service.py` AND `scripts/preprocess_audio.py` — kept in sync by convention, checked by `tests/test_audio_extensions.py` | File upload validation | A file extension present in one copy but not the other passes/fails inconsistently depending which code path handles it |
| `/api/v1` route prefix | `backend/main.py`'s `app.include_router(..., prefix=API_PREFIX)` | Every hardcoded path in `android/lib/core/api_client.dart` and `ws_transcribe_client.dart` | Changing the prefix breaks every client request until the Flutter side is updated to match |
| Environment variable names (`JWT_SECRET_KEY`, `DATABASE_URL`, `CELERY_BROKER_URL`, etc.) | `backend/core/config.py` | Deployment configs (`deployment/docker-compose.yml`, `.github/workflows/ci.yml`), and anyone's local shell session | A renamed env var silently falls back to `config.py`'s hardcoded default instead of erroring — e.g. rename `HF_TOKEN` and diarization silently becomes unavailable with only a log line, no crash |
| `session:{id}:results` pub/sub channel naming | `backend/core/pubsub.py`'s callers (`backend/worker/tasks.py` publishes, `backend/api/transcribe.py` subscribes) | Nothing external — but both call sites must agree | A mismatched channel string on either side means results are published into the void and the WebSocket hangs waiting for chunks that will never arrive |
| `chunk_results` JSON shape, keyed by `str(chunk_index)` | `backend/models/session.py`, `session_service.materialize_transcript()` | Nothing reads this directly except that one function — but it's the literal source of truth for the visible transcript | Changing the key scheme (e.g. to arrival order instead of chunk index) reintroduces the out-of-order-chunk bug this design specifically avoids |
| Database table/column names | `backend/models/*.py` + `backend/database/migrations/versions/0001_initial_schema.py` | Alembic's own migration history — a schema change needs a new migration, not a hand-edit of the existing model | Editing an existing model's column without a matching Alembic migration leaves SQLite (auto-created) and Postgres (migration-driven) diverging silently |
