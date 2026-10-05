# API Contract — Flutter ↔ Backend Communication Boundary

> Written 2026-09-18 by reading every route handler in `backend/api/*.py`, every schema in
> `backend/schemas/*.py`, every publish call in `backend/worker/tasks.py`, and — critically — the
> actual Flutter-side consumer of each: `android/lib/core/api_client.dart`,
> `android/lib/core/ws_transcribe_client.dart`, and every file under `android/lib/models/`, read in
> full this pass, side by side with their backend counterparts. Every endpoint below is real and
> currently reachable in this codebase; none were invented. Every example payload uses realistic,
> non-secret values. Two genuine frontend/backend discrepancies were found doing this side-by-side
> read and are called out explicitly in §5 — not glossed over.

All routes below are mounted under the `/api/v1` prefix (`backend/main.py`) except `/health` and
`/metrics`. Every route except `/health`, `/metrics`, `/auth/register`, and `/auth/login` requires
`Authorization: Bearer <JWT>` — the WebSocket route is the one exception to the *header* mechanism
specifically (see §2).

---

## 1. HTTP endpoints

### `POST /api/v1/auth/register`

| | |
|---|---|
| **PURPOSE** | Create a new account. |
| **REQUEST FORMAT** | JSON body: `{"email": string, "password": string (8–72 chars)}` |
| **RESPONSE FORMAT** | `201`, JSON: `{"id": string, "email": string, "created_at": ISO-8601 string}` |
| **ERROR FORMAT** | `409 {"detail": "An account with email '...' already exists."}`; `422` (Pydantic validation, e.g. malformed email or password too short) |
| **AUTHENTICATION** | None required |
| **CALLING FLUTTER FILE** | `android/lib/core/api_client.dart` |
| **FLUTTER HANDLER** | `ApiClient.register(email, password)` → `UserOut.fromJson()` (`android/lib/models/auth_models.dart`) |
| **CALLING PYTHON FILE** | N/A (this *is* the Python side) |
| **PYTHON HANDLER** | `backend/api/auth.py: register()` → `backend/services/user_service.py: register_user()` |

Example request:
```json
{"email": "teacher.reyes@example.com", "password": "correcthorsebattery"}
```
Example success response:
```json
{"id": "b9827e753d5d43a095794436bcb50f27", "email": "teacher.reyes@example.com", "created_at": "2026-09-15T12:39:09.703487"}
```

### `POST /api/v1/auth/login`

| | |
|---|---|
| **PURPOSE** | Exchange email/password for a JWT bearer token. |
| **REQUEST FORMAT** | `application/x-www-form-urlencoded` (OAuth2 password-grant convention): `username=<email>&password=<password>` — note the field is literally named `username` by the OAuth2 spec even though the value is an email address |
| **RESPONSE FORMAT** | `200`, JSON: `{"access_token": string, "token_type": "bearer"}` |
| **ERROR FORMAT** | `401 {"detail": "Incorrect email or password."}` (with `WWW-Authenticate: Bearer` header); `429` if rate-limited (10/minute default) |
| **AUTHENTICATION** | None required (this issues the token) |
| **CALLING FLUTTER FILE** | `android/lib/core/api_client.dart` |
| **FLUTTER HANDLER** | `ApiClient.login(email, password)` → `TokenResponse.fromJson()`; caller is `AuthController.login()` |
| **PYTHON HANDLER** | `backend/api/auth.py: login()` → `user_service.authenticate_user()` → `backend/core/security.py: create_access_token()` |

Example request body (form-encoded, not JSON): `username=teacher.reyes%40example.com&password=correcthorsebattery`

Example success response:
```json
{"access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiOTgyN2U3NS4uLiJ9.xxxxx", "token_type": "bearer"}
```

### `POST /api/v1/transcribe` — **NOT CALLED FROM ANYWHERE IN THE FLUTTER APP** (see §5)

| | |
|---|---|
| **PURPOSE** | Whole-file (non-streaming) transcription of an already-recorded audio file. |
| **REQUEST FORMAT** | `multipart/form-data`: `file` (the audio file), `consent_confirmed` (bool, required), `title` (optional string), `enable_denoise`/`enable_vad`/`enable_diarization`/`enable_teacher_verification` (bools), `num_speakers` (optional int), `beam_size` (default 5) |
| **RESPONSE FORMAT** | `202`, JSON: `{"session_id": string, "status": "processing"}` — client is expected to poll `GET /sessions/{id}` |
| **ERROR FORMAT** | `400` (unsupported file extension, from `ingest_audio()`'s `ValueError`); `413` (over `MAX_UPLOAD_BYTES`, default 200MB); `422` (missing required form field) |
| **AUTHENTICATION** | Bearer token required |
| **CALLING FLUTTER FILE** | **None.** Grepped `android/lib/core/api_client.dart` in full this pass — there is no method that calls this route. |
| **CALLING PYTHON FILE** | `scripts/v2_smoke_test.py`, `scripts/ws_smoke_test.py` (dev-only smoke tests) call it directly via raw `requests.post` |
| **PYTHON HANDLER** | `backend/api/transcribe.py: transcribe_file()` → `session_service.create_session()` → `transcribe_file_task.delay()` (`backend/worker/tasks.py`) |

Example success response:
```json
{"session_id": "8d416d193a3f4cc081cefd92a6076f13", "status": "processing"}
```

### `GET /api/v1/sessions`

| | |
|---|---|
| **PURPOSE** | List every session owned by the current account, newest first. |
| **REQUEST FORMAT** | No body; no query parameters. |
| **RESPONSE FORMAT** | `200`, JSON array of `SessionSummary`: `[{"id", "title", "status", "created_at", "duration_seconds"}, ...]` |
| **ERROR FORMAT** | `401` if no/invalid token |
| **AUTHENTICATION** | Bearer token required |
| **CALLING FLUTTER FILE** | `android/lib/screens/home/home_screen.dart` (`_load()`) |
| **FLUTTER HANDLER** | `ApiClient.listSessions()` → `List<SessionSummary>` (`android/lib/models/session_models.dart`) |
| **PYTHON HANDLER** | `backend/api/sessions.py: list_sessions()` → `session_service.list_sessions()` |

Example response:
```json
[
  {"id": "8d416d193a3f4cc081cefd92a6076f13", "title": "Grade 10 Statistics", "status": "completed", "created_at": "2026-09-15T12:49:08.226297", "duration_seconds": 312.5},
  {"id": "fa5ac7ce44724bc4b575ed9e8ebff187", "title": null, "status": "in_progress", "created_at": "2026-09-15T13:02:11.004512", "duration_seconds": null}
]
```

### `GET /api/v1/sessions/{session_id}`

| | |
|---|---|
| **PURPOSE** | Full detail for one session — the complete transcript, per-segment metadata, keywords, minutes, and per-stage latency data. |
| **RESPONSE FORMAT** | `200`, JSON `SessionDetail` (see §3 for the full field catalog) |
| **ERROR FORMAT** | `404 {"detail": "No session found with id '...'."}` (also returned if the session exists but belongs to a different account — ownership and existence are indistinguishable by design) |
| **AUTHENTICATION** | Bearer token required |
| **CALLING FLUTTER FILE** | `android/lib/screens/transcript/transcript_screen.dart` (`_load()`, with `pollUntil()` if `isProcessing`) |
| **FLUTTER HANDLER** | `ApiClient.getSession(id)` → `SessionDetail.fromJson()` |
| **PYTHON HANDLER** | `backend/api/sessions.py: get_session()` → `session_service.get_session()` → `SessionRecord.to_detail_dict()` |

### `DELETE /api/v1/sessions/{session_id}`

| | |
|---|---|
| **PURPOSE** | Permanently delete a session (full purge — RA 10173 right-to-deletion). |
| **RESPONSE FORMAT** | `200 {"deleted": true}` |
| **ERROR FORMAT** | `404` (same not-found/not-owned ambiguity as above) |
| **AUTHENTICATION** | Bearer token required |
| **CALLING FLUTTER FILE** | `android/lib/screens/home/home_screen.dart` (`_delete()`, called from the swipe-to-delete gesture) |
| **FLUTTER HANDLER** | `ApiClient.deleteSession(id)` |
| **PYTHON HANDLER** | `backend/api/sessions.py: delete_session()` → `session_service.delete_session()` |

### `WS /api/v1/ws/transcribe?token=<JWT>`

See §2 for the complete lifecycle. Documented here for completeness of the endpoint list.

| | |
|---|---|
| **PURPOSE** | Live, chunk-by-chunk streaming transcription during an active recording. |
| **AUTHENTICATION** | JWT as a `?token=` query parameter — **not** a header (browsers/Flutter's WS client cannot set a custom header on the WS handshake) |
| **CALLING FLUTTER FILE** | `android/lib/screens/recording/live_recording_screen.dart` |
| **FLUTTER HANDLER** | `WsTranscribeClient` (`android/lib/core/ws_transcribe_client.dart`) |
| **PYTHON HANDLER** | `backend/api/transcribe.py: transcribe_stream()` |

### `POST /api/v1/teachers/enroll`

| | |
|---|---|
| **PURPOSE** | Submit a voice sample to enroll (or re-enroll under a new name) a teacher voice profile. |
| **REQUEST FORMAT** | `multipart/form-data`: `name` (string, the teacher's display name), `file` (the audio sample) |
| **RESPONSE FORMAT** | `202`, JSON `TeacherOut`: `{"id", "name", "status": "pending", "error_detail": null, "created_at"}` — client polls `GET /teachers/{id}` |
| **ERROR FORMAT** | `429` if rate-limited (10/minute default); `422` if `name` or `file` missing |
| **AUTHENTICATION** | Bearer token required |
| **CALLING FLUTTER FILE** | `android/lib/screens/enrollment/teacher_enrollment_screen.dart` (`_submit()`) |
| **FLUTTER HANDLER** | `ApiClient.enrollTeacher(name, audioBytes, filename)` — builds a real `MultipartRequest`, field `name` + file field `file` |
| **PYTHON HANDLER** | `backend/api/teacher.py: enroll_teacher()` → `session_service.create_pending_teacher()` (synchronous) → `enroll_teacher_task.delay()` (`backend/worker/tasks.py`) |

Example success response:
```json
{"id": "96d75f2e58464478a206a99756092c85", "name": "Ms. Reyes", "status": "pending", "error_detail": null, "created_at": "2026-09-15T12:49:20.099203"}
```

### `GET /api/v1/teachers`

| | |
|---|---|
| **PURPOSE** | List every teacher enrollment owned by the current account. |
| **RESPONSE FORMAT** | `200`, JSON array of `TeacherOut` |
| **CALLING FLUTTER FILE** | `android/lib/screens/enrollment/teacher_enrollment_screen.dart` (`_load()`) |
| **FLUTTER HANDLER** | `ApiClient.listTeachers()` |
| **PYTHON HANDLER** | `backend/api/teacher.py: list_teachers()` |

### `GET /api/v1/teachers/{teacher_id}`

| | |
|---|---|
| **PURPOSE** | Poll one enrollment's status until it settles to `ready`/`failed`. |
| **RESPONSE FORMAT** | `200`, JSON `TeacherOut` — `status` is `"pending"`, `"ready"`, or `"failed"`; `error_detail` is populated only when `status == "failed"` |
| **ERROR FORMAT** | `404` if not found/not owned |
| **CALLING FLUTTER FILE** | `android/lib/screens/enrollment/teacher_enrollment_screen.dart` (`_pollTeacherStatus()`, via `pollUntil()`) |
| **FLUTTER HANDLER** | `ApiClient.getTeacher(id)` |
| **PYTHON HANDLER** | `backend/api/teacher.py: get_teacher()` |

Example "ready" response:
```json
{"id": "96d75f2e58464478a206a99756092c85", "name": "Ms. Reyes", "status": "ready", "error_detail": null, "created_at": "2026-09-15T12:49:20.099203"}
```
Example "failed" response:
```json
{"id": "96d75f2e58464478a206a99756092c85", "name": "Ms. Reyes", "status": "failed", "error_detail": "Teacher verification model is not loaded (speechbrain missing on the worker).", "created_at": "2026-09-15T12:49:20.099203"}
```

### `DELETE /api/v1/teachers/{teacher_id}`

| | |
|---|---|
| **RESPONSE FORMAT** | `200 {"deleted": true}` |
| **ERROR FORMAT** | `404` if not found/not owned |
| **CALLING FLUTTER FILE** | `android/lib/screens/enrollment/teacher_enrollment_screen.dart` (`_delete()`) |
| **FLUTTER HANDLER** | `ApiClient.deleteTeacher(id)` |
| **PYTHON HANDLER** | `backend/api/teacher.py: delete_teacher()` |

### `GET /api/v1/sessions/{session_id}/minutes`

| | |
|---|---|
| **PURPOSE** | Fetch the raw structured-minutes JSON for a finalized session. |
| **RESPONSE FORMAT** | `200`, JSON `Minutes` object (full field catalog in §3) |
| **ERROR FORMAT** | `404` (session not found/not owned); `409 {"detail": "Minutes have not been generated yet for this session."}` (session exists but hasn't finalized, or had no detected speech) |
| **CALLING FLUTTER FILE** | `android/lib/screens/minutes/minutes_screen.dart` (`_load()`) |
| **FLUTTER HANDLER** | `ApiClient.getMinutes(sessionId)` → raw `Map<String, dynamic>`, then `Minutes.fromJson()` in the screen itself |
| **PYTHON HANDLER** | `backend/api/minutes.py: get_minutes()` |

### `GET /api/v1/sessions/{session_id}/minutes/export?format=markdown|txt`

| | |
|---|---|
| **PURPOSE** | Render the structured minutes as a downloadable document. |
| **REQUEST FORMAT** | Query param `format`, one of `"markdown"` (default) or `"txt"` |
| **RESPONSE FORMAT** | `200`, `Content-Type` **not JSON** — plain text (Markdown or plain-text formatting), with `Content-Disposition: attachment; filename="minutes_<id>.md"` (or `.txt`) |
| **ERROR FORMAT** | `400 {"detail": "format must be 'markdown' or 'txt'."}`; `404`; `409` (same as above) |
| **AUTHENTICATION** | Bearer token required |
| **CALLING FLUTTER FILE** | `android/lib/screens/minutes/minutes_screen.dart` (`_export()`) |
| **FLUTTER HANDLER** | `ApiClient.exportMinutes(sessionId, format)` — **deliberately bypasses `_handle()`** (which would call `jsonDecode()` on a non-JSON body and throw) in favor of `_ensureOk()`, then returns the raw response body as a `String`; the screen hands that string to `SharePlus.instance.share(ShareParams(text: body, ...))` |
| **PYTHON HANDLER** | `backend/api/minutes.py: export_minutes()` → `_render_minutes()` |

Example response body (`format=txt`, truncated):
```
Minutes: Grade 10 Statistics
Generated: 2026-09-15T12:49:30.011375+00:00
Duration: 312.5s
Participants: Speaker A, Speaker B
Teacher speech: 64.2% (Speaker A)
Keywords: variance, standard deviation, sample mean

Topics:
 Variance and standard deviation [12.0s - 96.5s]
  - Variance measures how far each data point is from the mean
  ...
```

### `GET /health` — **NOT under `/api/v1`, no auth**

| | |
|---|---|
| **PURPOSE** | Liveness probe. Does not touch the database or worker tier. |
| **RESPONSE FORMAT** | `200 {"status": "ok", "environment": "development"}` |
| **CALLING FLUTTER FILE** | None — not called anywhere in the app. Used by `deployment/Dockerfile.api`'s own `HEALTHCHECK` and by manual `curl`/troubleshooting. |
| **PYTHON HANDLER** | `backend/main.py: health_check()` |

### `GET /metrics` — **NOT under `/api/v1`, no auth**

| | |
|---|---|
| **PURPOSE** | Prometheus-format scrape endpoint. |
| **CALLING FLUTTER FILE** | None. |
| **PYTHON HANDLER** | Auto-registered by `Instrumentator().instrument(app).expose(app, endpoint="/metrics")` in `backend/main.py` — not a hand-written route. |

---

## 2. WebSocket — the complete message lifecycle

**Connection:** `wss://<host>/api/v1/ws/transcribe?token=<JWT>` (or `ws://` on plaintext dev
setups — see `docs/DEVELOPMENT.md` on `usesCleartextTraffic`). Established by
`WsTranscribeClient.connect()`, which awaits `channel.ready` before returning.

**Step 1 — client sends the `start` control frame** (a text/JSON WebSocket frame):
```json
{"type": "start", "title": "Grade 10 Statistics", "consent_confirmed": true, "options": {
  "enable_denoise": false, "enable_vad": true, "enable_diarization": false,
  "enable_teacher_verification": true, "num_speakers": null, "beam_size": 5,
  "chunk_duration_seconds": 3.0
}}
```
Built by `StartFrame.toJson()`, sent by `WsTranscribeClient.sendStart()`, called from
`LiveRecordingScreen._start()` immediately after the socket connects. Server-side, this is the
**first** message the connection must send — `backend/api/transcribe.py: _handle_start_message()`
reads it, validates `type == "start"`, and calls `session_service.create_session()`.

**Step 2a — server replies with `session_started`** (success path):
```json
{"type": "session_started", "session_id": "fa5ac7ce44724bc4b575ed9e8ebff187"}
```
Flutter's `_handleWsMessage()` reacts to `SessionStartedMessage` by calling
`_beginStreamingAudio()`, which is the point the microphone stream actually starts being consumed
and chunked — **audio capture does not begin until this message arrives**, not when the socket
first opens.

**Step 2b — server replies with `error` and closes** (failure path — e.g. malformed start frame):
```json
{"type": "error", "detail": "consent_confirmed must be true to create a session."}
```
No `chunk_index` field on this shape (there is no chunk yet). The connection is closed by the
server immediately after.

**Step 3 — client streams binary WAV frames**, one per chunk, each a complete, self-contained
44-byte-header WAV file (`wav_encoder.dart: wrapPcm16AsWav()`), gated through
`local_vad.dart`'s energy check before being sent at all. Not JSON — a raw binary WebSocket frame.
Sent by `WsTranscribeClient.sendChunk(Uint8List wavBytes)`.

**Step 4 — server replies with one `chunk_result` per completed chunk**, in **completion order,
not necessarily send order**:
```json
{
  "type": "chunk_result",
  "chunk_index": 0,
  "text": "Variance measures how far each data point is from the mean.",
  "language": "en",
  "whisper_segments": [
    {"start": 0.0, "end": 3.24, "text": "Variance measures how far each data point is from the mean.",
     "avg_logprob": -0.21, "no_speech_prob": 0.02, "speaker": "Speaker A", "is_teacher": true,
     "teacher_name": "Ms. Reyes", "confidence": 0.78}
  ],
  "speaker_segments": [
    {"speaker": "Speaker A", "start": 0.0, "end": 3.24, "duration": 3.24}
  ],
  "transcript_so_far": "Variance measures how far each data point is from the mean."
}
```
Or, on a chunk-level failure (non-fatal — the session continues):
```json
{"type": "error", "chunk_index": 2, "detail": "Transcription failed on segment {...}: <exception message>"}
```

**Step 5 — client sends the `end` control frame**:
```json
{"type": "end"}
```
Built by `EndFrame.toJson()`, sent by `WsTranscribeClient.sendEnd()`, called from
`LiveRecordingScreen._stop()` after flushing any buffered partial chunk.

**Step 6 — server sends exactly one final `session_ended` message, then closes the socket**:
```json
{
  "type": "session_ended",
  "session_id": "fa5ac7ce44724bc4b575ed9e8ebff187",
  "transcript": "Variance measures how far each data point is from the mean. Standard deviation is its square root.",
  "keywords": ["variance", "standard deviation", "square root"],
  "minutes": {
    "generated_at": "2026-09-15T12:49:34.552210+00:00",
    "duration_seconds": 8.0,
    "participants": ["Speaker A"],
    "teacher_speech_ratio": 1.0,
    "teacher_speakers": ["Speaker A"],
    "keywords": ["variance", "standard deviation", "square root"],
    "topics": [{"label": "variance", "start": 0.0, "end": 8.0, "key_points": ["Variance measures how far each data point is from the mean."]}],
    "definitions": [],
    "action_items": []
  }
}
```
This is sent from `finalize_and_close()` (`backend/api/transcribe.py`), the **only** call site in
the entire codebase for `session_service.finalize_session()`. The server closes the socket
immediately after sending it — `LiveRecordingScreen._handleWsMessage()`'s `SessionEndedMessage`
case marks the closure as intentional (`_wsClient.close()`) **before** navigating to
`TranscriptScreen`, specifically to avoid racing the socket's own `onDone` callback (a real bug
found and fixed on-device — `CLAUDE.md` Part 2, Flutter Client section).

**Unhandled/malformed message type:** `WsServerMessage.fromJson()`'s `default` branch converts
*any* unrecognized `type` value into a `WsErrorMessage` with a synthetic detail string
(`'Unrecognized message type: ...'`) rather than throwing — this is a deliberate defensive
default, not a gap; it means a future new server message type is silently swallowed into a
generic error snackbar rather than crashing the app, until someone adds a matching `case`.

---

## 3. Full JSON object catalog

| Object | Defined (backend) | Defined (Flutter) | Notes |
|---|---|---|---|
| `SessionSummary` | `backend/schemas/session.py` | `android/lib/models/session_models.dart` | Fields match exactly, field-for-field |
| `SessionDetail` | `backend/schemas/session.py` (extends `SessionSummary`) | `session_models.dart` | Fields match exactly |
| `TranscriptSegment` (one entry of `transcript_segments`/`whisper_segments`) | Not a named Pydantic model — assembled ad hoc in `backend/services/audio_service.py: transcribe_audio()`/`apply_teacher_verification()` | `session_models.dart: TranscriptSegment` | `start`, `end`, `text` always present; `avg_logprob`, `no_speech_prob` always present on a real Whisper segment; `speaker` only if diarization ran; `is_teacher`/`teacher_name`/`confidence` only if teacher verification ran — Flutter's `fromJson` treats all four as nullable, correctly |
| `UserOut` | `backend/schemas/auth.py` | `auth_models.dart` | Matches exactly |
| `Token` | `backend/schemas/auth.py` | `auth_models.dart: TokenResponse` | Matches exactly (Flutter's class is named differently, fields identical) |
| `TeacherOut` | `backend/schemas/teacher.py` | `teacher_models.dart` | Matches exactly |
| `PipelineOptions` | `backend/schemas/pipeline.py` | `pipeline_config.dart` | Matches exactly — the single highest-risk hand-maintained contract in the app, per that file's own comment |
| `Minutes` (the dict `generate_minutes()` returns) | Not a named Pydantic model — a plain dict from `backend/services/minutes_service.py: generate_minutes()` | `minutes_models.dart: Minutes` | See discrepancy note below on `.get()`-defensive optional fields |
| WS `start` frame | `backend/schemas/session.py: StartSessionMessage` (defined, but **not actually used** for parsing — `transcribe.py`'s `_handle_start_message()` parses the raw dict directly with `.get()` calls, not via this Pydantic model) | `ws_messages.dart: StartFrame` | See discrepancy note below |
| WS `chunk_result`/`error`/`session_started`/`session_ended` | Assembled as raw dicts in `backend/api/transcribe.py` and `backend/worker/tasks.py` — **no Pydantic model exists for any WS server-to-client message** | `ws_messages.dart: WsServerMessage` hierarchy | Entirely hand-maintained parity, no schema validation on either side |

---

## 4. Contracts that must not be changed casually

- **`PipelineOptions` field names** — a rename on either side is silently absorbed by Pydantic's
  defaults (server) or Dart's `?? default` fallbacks (client) — **no error, no crash, just wrong
  behavior**. Check both `backend/schemas/pipeline.py` and `pipeline_config.dart`'s `toJson()`
  together, always.
- **WS message `type` string values** — check `backend/api/transcribe.py` and `worker/tasks.py`
  (senders) against `ws_messages.dart`'s `fromJson()` switch (receiver) together. An unrecognized
  type doesn't crash (see the `default` case above) but silently degrades to a generic error.
- **The `/api/v1` prefix** — every hardcoded path in `api_client.dart`'s `_uri()` helper and
  `ws_transcribe_client.dart`'s connect URL assumes this exact prefix.
- **`_handle()` vs `_ensureOk()` in `api_client.dart`** — every endpoint that returns JSON must go
  through `_handle()`; the one endpoint that returns plain text (`exportMinutes`) must use
  `_ensureOk()` instead. Routing a new plain-text endpoint through `_handle()` reproduces the
  exact `FormatException` bug fixed in round 8 (`CLAUDE.md` Part 2).
- **The `TranscriptSegment` optional-field contract** — `speaker`/`is_teacher`/`teacher_name`/
  `confidence` are genuinely absent (not just null) on any segment from a session that ran with
  diarization/teacher-verification off. Any new consumer of this shape must treat all four as
  optional, the way `session_models.dart` already does.

---

## 5. Discrepancies found between what the frontend expects and what the backend sends

**1. `chunk_result`'s `speaker_segments` field is sent by the backend and silently dropped by the
Flutter client.** `backend/worker/tasks.py: transcribe_chunk_task()` publishes `speaker_segments`
as part of every `chunk_result` message (confirmed directly in its `publish_sync(...)` call).
`android/lib/models/ws_messages.dart: ChunkResultMessage.fromJson()` parses `chunk_index`, `text`,
`language`, `whisper_segments`, and `transcript_so_far` — **`speaker_segments` is read nowhere in
this factory constructor.** This is not a crash (Dart's `Map<String, dynamic>` parsing simply
ignores keys it doesn't ask for) but it means live per-chunk diarization data, if diarization is
enabled for a session, is computed server-side and transmitted over the wire on every single chunk
and then discarded client-side without ever reaching the UI. The equivalent data **is** available
later, per-segment, via `GET /sessions/{id}`'s `speaker_segments`/`transcript_segments` fields
once the session ends — so nothing is permanently lost, but the live-streaming view genuinely
receives and drops this data on every chunk. **Which side "wins" currently:** the frontend's
narrower expectation is what's actually in effect; the backend's broader payload is partially
wasted bandwidth for this one field, live, in the currently-shipped app.

**2. `POST /transcribe` (whole-file upload) has no Flutter call site at all.** The endpoint is
fully implemented, tested (`tests/test_transcribe_api.py`), and exercised by both smoke-test
scripts against a live server — but a full read of `android/lib/core/api_client.dart` this pass
found no method that calls it. This matches `docs/future_ideas.md`'s own note that the "Import
audio file" flow was deliberately descoped from the six required screens, but it's worth stating
in contract terms precisely: **the backend implements a contract the frontend has no code path to
invoke.** Not a disagreement about shape — a real, confirmed asymmetry in what's actually wired
up end to end.

**3. `StartSessionMessage`/`EndSessionMessage` (`backend/schemas/session.py`) are defined but
never actually used for request validation.** `backend/api/transcribe.py: _handle_start_message()`
parses the incoming WS `start` frame with plain `dict.get()` calls on the raw decoded JSON, not by
constructing a `StartSessionMessage` instance — meaning these two Pydantic models currently
document an *intended* shape but provide **zero runtime validation** on the actual WS control
frames. A malformed `options` sub-object, for instance, is only caught because
`PipelineOptions(**control.get("options", {}))` is called separately, one line later, on the raw
dict — not because `StartSessionMessage` validated anything. This is not a frontend/backend
mismatch in the sense of the app sending something the server rejects; both sides currently agree
on the actual shape sent/received. It is a documentation-vs-enforcement gap: these schema classes
exist and describe the contract correctly, but are not wired into the code path that would
actually enforce them.

No other discrepancy was found between what `android/lib/models/*.dart` parses and what
`backend/schemas/*.py` + the raw dicts assembled in `backend/api/*.py`/`backend/worker/tasks.py`
actually send, checked field-for-field this pass.
