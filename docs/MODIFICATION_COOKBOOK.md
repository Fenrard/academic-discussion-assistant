# Modification Cookbook

> Written 2026-09-16 for a beginner developer who can read Python and Dart but has no mental model
> of this project's architecture yet. Every file path, class name, and function name below was
> checked directly against the repository this pass — not written from memory. Read
> `CLAUDE.md` Part 1 first if you haven't (10-minute orientation); this document assumes you know
> the two-process split (FastAPI "API tier" in `backend/main.py`, zero ML imports; Celery "worker
> tier" in `backend/worker/`, all ML imports) and won't re-explain it in every entry.
>
> **Format per task:** files to inspect, exact classes/functions, what to change, what NOT to
> change, dependencies affected, tests to run, expected result, common mistakes. Entries reference
> each other rather than repeating shared context (e.g. "the pipeline order" is explained once,
> under VAD, and referenced everywhere else it matters).
>
> **Before you touch anything:** run the two baseline test suites so you know what "still working"
> looks like on your machine, right now.
> ```powershell
> # Backend, from the repo root, venv active, JWT_SECRET_KEY set:
> pytest tests/ -v          # expect: 90 passed, 1 skipped
> # Flutter, from android/:
> flutter analyze           # expect: No issues found
> flutter test               # expect: all tests passed (12 files)
> ```

---

## 1. Change the Flutter UI (styling/layout of an existing screen)

**Files to inspect:** the specific screen under `android/lib/screens/<area>/<name>_screen.dart`
(eight screens total: `auth/login_screen.dart`, `auth/register_screen.dart`,
`home/home_screen.dart`, `enrollment/teacher_enrollment_screen.dart`,
`recording/live_recording_screen.dart`, `transcript/transcript_screen.dart`,
`minutes/minutes_screen.dart`, `settings/settings_screen.dart`). Theme lives in
`android/lib/app.dart`'s `ScaitaleApp.build()` (`ThemeData(colorSchemeSeed: Colors.indigo, ...)`).

**Exact classes/functions:** each screen is a `StatefulWidget`/`State` pair; the visual tree is
built in that `State`'s `build(BuildContext)` method and usually split into private `_buildXxx()`
helpers (e.g. `LiveRecordingScreen`'s `_buildSetupForm()` / `_buildRecordingView()`).

**What to change:** widget tree and `Theme.of(context)`/`ThemeData` values only. Don't touch a
screen's non-UI methods (anything not named `build*`/starting with a widget return) unless your
task is actually behavioral.

**What NOT to change:** the global theme seed color/`useMaterial3` without checking every screen
still reads clearly in both light and dark (`ThemeData`/`darkTheme` are both defined in
`app.dart`); don't rename a screen class without updating every `Navigator.push`/`pushReplacement`
call site that references it (`Explore`/`grep -rn "ScreenName(" android/lib/`).

**Dependencies affected:** none outside `android/` — the backend has no concept of the UI.

**Tests to run:** `flutter analyze && flutter test` from `android/`. Widget-level UI changes
usually don't need new tests unless you're changing testable behavior (a button's `onPressed`
condition, a form's validation) — pure visual changes (color, padding, text) aren't unit-tested in
this project's suite.

**Expected result:** `flutter analyze` clean, existing tests still green, and — since this project's
own convention (see `CLAUDE.md`'s "Flutter Client (Built)" section) is that WS-timing and gesture
bugs were only ever caught by actually running the app — do a real `flutter run` against a live
backend for anything touching `live_recording_screen.dart` or `home_screen.dart`'s list/dismiss
behavior specifically.

**Common mistakes:** editing widget code inside a `setState(() { ... })` callback that also does
non-UI work (state mutation) — keep `setState` bodies to state assignment only, matching this
codebase's existing style. Forgetting `const` constructors where the codebase already uses them
(harmless, but inconsistent with the surrounding style you're editing).

---

## 2. Add a new Flutter screen

**Files to inspect:** an existing screen as a template — `android/lib/screens/enrollment/
teacher_enrollment_screen.dart` is a good middle-complexity example (form + async submit +
polling). `android/lib/app.dart` (routing/auth gate). `android/lib/core/api_client.dart` (if the
new screen needs a new backend call — see entry 9, "Add an API endpoint," for the backend half).

**Exact classes/functions:** create `android/lib/screens/<area>/<name>_screen.dart` following the
existing `StatefulWidget` pattern. Wire navigation from whichever screen should link to it via
`Navigator.of(context).push(MaterialPageRoute(builder: (_) => YourNewScreen()))` — this project
uses direct `MaterialPageRoute` pushes throughout (see `LiveRecordingScreen._handleWsMessage()`'s
`SessionEndedMessage` case for the exact idiom), not a named-route table or a router package.

**What to change:** add the new file; add exactly one `Navigator.push(...)` call site from
wherever the screen should be reachable (e.g. a new button on `HomeScreen`). If it needs
API access, add a method to `ApiClient` (`android/lib/core/api_client.dart`) mirroring the
existing one-method-per-endpoint pattern.

**What NOT to change:** `ScaitaleApp`'s `home:` auth gate in `app.dart` — that's the
login/home top-level switch, not where a new *interior* screen belongs; adding it there would
make it a second top-level destination bypassing login. `PipelineOptions`
(`android/lib/models/pipeline_config.dart`) — only touch this if the new screen genuinely needs a
new pipeline toggle (see entry 11).

**Dependencies affected:** `android/pubspec.yaml` only if the new screen needs a new package
(check `flutter pub add <package>` — this project already uses `provider`, `record`,
`shared_preferences`, `flutter_secure_storage`, `share_plus`).

**Tests to run:** add a widget test under `android/test/` for the new screen if it has meaningful
logic (see `android/test/home_screen_test.dart` for a real example — it drives a swipe gesture and
asserts on the resulting state, not just that the widget builds). `flutter analyze && flutter test`.

**Expected result:** the screen builds, navigates to correctly, and (if it talks to the backend) a
real on-device/emulator run against a live backend succeeds — this project's own history
(`CLAUDE.md`'s "One real bug found and fixed by this on-device run") shows WS/navigation timing
bugs specifically don't show up in `flutter test` alone.

**Common mistakes:** forgetting `AuthController`'s token isn't automatically available — screens
that call `ApiClient` need `context.read<AuthController>().token`, following
`LiveRecordingScreen._start()`'s pattern. Building a new screen that duplicates
`PollUntil`/`pollUntil()` logic instead of reusing `android/lib/core/polling.dart` — every
async-status screen in this app (`teacher_enrollment_screen.dart`, and the whole-file-upload path
if it ever gets a UI) uses that one helper.

---

## 3. Change recording behavior (start/stop logic, mic handling)

**Files to inspect:** `android/lib/screens/recording/live_recording_screen.dart` — the entire
recording lifecycle lives in this one file's `_start()`, `_beginStreamingAudio()`, `_stop()`,
`_handleWsMessage()`, `_handleUnexpectedDisconnect()`.

**Exact classes/functions:** `_recorder` is a `record` package `AudioRecorder`. `_start()` requests
mic permission (`_recorder.hasPermission()`), opens the WS (`_wsClient.connect(...)`), and sends
the `start` control frame (`_wsClient.sendStart(StartFrame(...))`). `_beginStreamingAudio()` opens
the actual PCM stream (`_recorder.startStream(RecordConfig(...))`) only after the server responds
`session_started` — **not** immediately in `_start()`; this ordering matters (see "what NOT to
change" below). `_stop()` cancels the mic subscription, flushes `PcmChunker`, sends the `end`
control frame, and waits for the server's `session_ended` to trigger navigation (it does **not**
navigate itself).

**What to change:** anything inside these five methods for behavioral changes (e.g. adding a pause
button would add a new `_Phase` enum value and branch in `_buildRecordingView()`/`_stop()`).

**What NOT to change:** the fact that `_beginStreamingAudio()` only runs after `session_started`
arrives (in the `SessionStartedMessage()` case of `_handleWsMessage`'s switch) — starting the mic
stream before the server has created the session row would let chunks race a session that doesn't
exist in the DB yet. Also don't remove the `unawaited(_wsClient.close())` call in the
`SessionEndedMessage` case — a real, previously-fixed bug (see `CLAUDE.md`'s "One real bug found
and fixed by this on-device run") was exactly this: the WS's `onDone` firing on the server's own
graceful close raced the screen's navigation and could pop back over it. That line marks the
closure as intentional before navigating, specifically to prevent that race from recurring.

**Dependencies affected:** `record` package version (`android/pubspec.yaml`) if you need a feature
it doesn't currently expose (e.g. pause/resume — check the package's own API surface first, this
project only uses `hasPermission()`/`startStream()`/`stop()`/`dispose()`).

**Tests to run:** `android/test/pcm_chunker_test.dart` if you touch chunking; no existing unit test
covers `LiveRecordingScreen` itself beyond `app_auth_gate_test.dart` (unrelated) — a real on-device
run is the actual verification method this project uses for this file (see `CLAUDE.md`).

**Expected result:** a session still reaches `status: "completed"` server-side and the Transcript
screen loads after stopping.

**Common mistakes:** adding UI state changes without going through `setState()` (silent no-op
rebuilds); forgetting `if (!mounted) return;` after an `await` before touching `context` — this
file already does this consistently (see `_start()`'s permission check) specifically because a 401
mid-recording can dispose the screen while an async call is in flight.

---

## 4. Change recording duration (chunk length)

**Files to inspect:** `android/lib/models/pipeline_config.dart` (`kMinChunkDurationSeconds`,
`kMaxChunkDurationSeconds`, each `PipelinePresets` entry's `chunkDurationSeconds`),
`backend/core/config.py` (`min_chunk_duration_seconds`, `max_chunk_duration_seconds`),
`backend/schemas/pipeline.py` (`PipelineOptions.chunk_duration_seconds`'s `Field(ge=..., le=...)`).

**Exact classes/functions:** the value flows: Settings screen slider → `SettingsController.
updateOptions()` → `PipelineOptions.chunkDurationSeconds` → sent as `chunk_duration_seconds` in
the WS `start` frame's `options` (see `StartFrame.toJson()`) → `PipelineOptions(**session.
pipeline_options)` on the backend (`backend/api/transcribe.py`) → `LiveRecordingScreen.
_beginStreamingAudio(chunkDurationSeconds)` constructs `PcmChunker(chunkDuration: Duration(...))`,
whose `bytesPerChunk` getter is the actual sizing math.

**What to change:** to widen the *allowed range*, change both `kMinChunkDurationSeconds`/
`kMaxChunkDurationSeconds` (Dart) **and** `min_chunk_duration_seconds`/`max_chunk_duration_seconds`
(Python) — these are two independently-maintained copies of the same spec (no shared source
between the two deployables, per `pipeline_config.dart`'s own comment) and must be changed
together or the two sides silently disagree about what's valid. To change a *default* preset's
duration, edit the relevant `PipelinePresets.{fast,balanced,accurate}` entry and/or
`PipelineOptions.chunk_duration_seconds`'s Pydantic `default=3.0`.

**What NOT to change:** `PcmChunker`'s `bytesPerChunk` formula itself unless you're deliberately
changing the sizing algorithm — it already correctly floors to "at least one full sample frame."
Don't set a chunk duration below roughly 1s in practice — this project's own history
(`CLAUDE.md`'s round-10 fix in `simulate_streaming.py`) found a ≤1s trailing chunk reliably
triggers a Whisper repetition-loop hallucination; the same risk applies to a genuinely short
`chunk_duration_seconds` on every chunk, not just a trailing one.

**Dependencies affected:** none new; this is a pure config-value change.

**Tests to run:** `android/test/pcm_chunker_test.dart` (chunk-sizing assertions),
`android/test/pipeline_config_test.dart` (preset value assertions — will need updating if you
change a preset's default), `pytest tests/test_transcribe_api.py -v` and any pipeline-schema test.

**Expected result:** the Settings screen's slider bounds match the new range; a live recording
session sends chunks of the new size (verify with a short on-device run).

**Common mistakes:** changing only one side (Dart *or* Python) of the min/max constants — the
Pydantic `Field(ge=..., le=...)` in `backend/schemas/pipeline.py` will silently reject a value the
Flutter slider happily let the user pick, surfacing as a confusing 422 only at request time.

---

## 5. Change audio format (WAV encoding details)

**Files to inspect:** `android/lib/core/wav_encoder.dart` (`wrapPcm16AsWav()`), the `RecordConfig`
construction in `LiveRecordingScreen._beginStreamingAudio()`, `backend/services/audio_service.py`
(`ingest_audio()`, `SUPPORTED_EXTENSIONS`).

**Exact classes/functions:** `wrapPcm16AsWav(pcmData, {sampleRate, numChannels, bitsPerSample})`
builds a 44-byte RIFF/WAVE header by hand around raw PCM16LE bytes. `ingest_audio()` on the backend
always runs FFmpeg (`ffmpeg -i <input> -ar 16000 -ac 1 -c:a pcm_s16le -af loudnorm <output>`) on
every chunk/file regardless of what arrives, per the locked "FFmpeg preprocessing is ALWAYS ON"
rule — so the wire format only needs to be *something FFmpeg can decode*, not already-canonical
16kHz mono PCM16.

**What to change:** if you need a different container/encoding on the wire (e.g. Opus for
bandwidth), you'd change `RecordConfig(encoder: ...)` in `live_recording_screen.dart` **and**
either replace `wrapPcm16AsWav()` entirely (if the new encoder doesn't need a hand-built header) or
adjust it. The backend side needs zero changes for a *decodable* format change — FFmpeg sniffs
content, not the extension — as long as the new container is one `ingest_audio()`'s FFmpeg
invocation can actually demux (check `ffmpeg -demuxers`).

**What NOT to change:** don't try to send truly headerless/raw PCM straight over the WS without a
container — `backend/api/transcribe.py`'s WS handler writes each binary frame straight to a
`.wav`-suffixed temp file (see `backend/utils/audio_io.write_temp_audio` usage patterns) and hands
it to FFmpeg, which needs to sniff a real container from the bytes. This is exactly why
`wrapPcm16AsWav()` exists at all (see its own doc comment) — `record`'s `startStream()` only emits
headerless PCM.

**Dependencies affected:** if switching encoders, check the `record` package's supported
`AudioEncoder` enum values for what's actually available on Android.

**Tests to run:** `android/test/wav_encoder_test.dart` (RIFF/WAVE/fmt/data header correctness —
update if you change the header-building logic), `pytest tests/test_audio_extensions.py`,
`pytest tests/test_audio_denoise.py` (denoise assumes 16kHz PCM WAV input to FFmpeg).

**Expected result:** a chunk survives the round trip and transcribes correctly; verify with a real
recording, not just that FFmpeg doesn't error (a format mismatch can decode "successfully" into
garbage audio).

**Common mistakes:** changing `bitsPerSample`/`numChannels` in the Dart encoder without updating
`SAMPLE_RATE`-adjacent assumptions on the backend — `load_waveform()` in `audio_service.py`
explicitly raises `ValueError` if `soundfile` reports anything other than exactly `settings.
sample_rate` (16000) after FFmpeg's own resample — so a format change that doesn't end up at
16kHz mono by the time it reaches `load_waveform()` will hard-fail, not silently misbehave.

---

## 6. Change sample rate

**Files to inspect:** `backend/core/config.py` (`Settings.sample_rate`), `backend/services/
audio_service.py` (`SAMPLE_RATE = settings.sample_rate`, used throughout `ingest_audio()`,
`detect_speech()`, `load_waveform()`), `android/lib/screens/recording/live_recording_screen.dart`
(`RecordConfig(sampleRate: 16000, ...)`), `android/lib/core/pcm_chunker.dart`
(`PcmChunker({this.sampleRate = 16000, ...})`).

**What to change:** `Settings.sample_rate` on the backend (this one value drives `ingest_audio()`'s
`-ar` flag, `detect_speech()`'s Silero call, and `load_waveform()`'s validation — all downstream of
this single constant, no other backend file hardcodes `16000`). On Flutter: the `RecordConfig`'s
`sampleRate` argument in `_beginStreamingAudio()`, and `PcmChunker`'s constructor default if you
want the client's own chunk-sizing math to stay correct without having to pass the new rate
explicitly at every call site.

**What NOT to change:** don't change just one side. `load_waveform()`'s `if sample_rate !=
SAMPLE_RATE: raise ValueError(...)` means a client sending at the old rate against a backend
expecting the new one fails **every single chunk**, loudly — this is a hard contract, not a soft
default. Don't change it without also considering Silero VAD's own supported rates — `silero-vad`
expects 8000 or 16000 Hz specifically; an arbitrary rate will not work with `get_speech_timestamps`
regardless of what FFmpeg resamples to.

**Dependencies affected:** none new, but every model in the pipeline (Whisper, Silero, SpeechBrain
ECAPA, pyannote) has its own expectations about input rate — 16kHz is the common denominator all
four were chosen around; verify each still accepts your new rate before assuming FFmpeg's resample
alone makes this a safe change.

**Tests to run:** the full `pytest tests/ -v` — sample rate touches nearly every pipeline stage.
`tests/test_audio_denoise.py`, `tests/test_tasks.py` (timestamp math assumes 16kHz throughout).

**Expected result:** identical pipeline behavior at the new rate, just resampled — if you're doing
this for a real reason (bandwidth, model requirement), expect to re-verify Whisper/Silero/
SpeechBrain/pyannote each still perform acceptably; this project's own instrumentation
(`evaluation/latency.py`) exists specifically to measure exactly this kind of change.

**Common mistakes:** assuming a higher sample rate uniformly improves accuracy — Whisper `small`
was trained on 16kHz audio; feeding it a higher rate through FFmpeg's resample buys nothing and
costs bandwidth/CPU. This is almost never actually the right change — reconsider whether the real
goal is something else (audio quality, denoising) before doing it.

---

## 7. Change WebSocket behavior (message protocol, reconnect logic)

**Files to inspect:** `backend/api/transcribe.py` (`transcribe_stream()`, `_handle_start_message()`
— the entire server-side WS state machine), `android/lib/core/ws_transcribe_client.dart`
(`WsTranscribeClient` — the client-side counterpart), `android/lib/models/ws_messages.dart`
(`StartFrame`, `EndFrame`, `WsServerMessage` sealed class + its `fromJson()` dispatcher).

**Exact classes/functions:** the message-type contract is: client sends `{"type": "start", ...}`
first (mandatory), then binary WAV frames, then `{"type": "end"}`; server sends `session_started`,
zero or more `chunk_result`/`error`, then exactly one `session_ended` and closes the socket. Server
state lives in `transcribe_stream()`'s local `state` dict (`enqueued`/`completed`/`ending`/
`finalized`/`disconnected`) shared between its two concurrent loops (`receive_chunks()`,
`listen_results()`, run via `asyncio.gather`).

**What to change:** to add a new message type (e.g. a `pause` control frame), add a new `case` in
`_handle_start_message`/`receive_chunks()`'s `control.get("type")` branch on the backend, and a new
matching class + `fromJson()` case in `WsServerMessage`/`StartFrame` (whichever direction) on the
Flutter side — **both sides must agree on the exact field names**, this is JSON over the wire with
no schema validation on the WS path (unlike the REST routes, which use Pydantic — see
`docs/API_CONTRACT.md`'s documented discrepancy: `StartSessionMessage`/`EndSessionMessage` Pydantic
schemas exist in `backend/schemas/` but the actual handler uses raw `dict.get()`, not schema
validation, so a typo on either side fails silently rather than with a clear validation error).

**What NOT to change:** the `finalize_and_close()` completion condition
(`state["ending"] and state["completed"] >= state["enqueued"]`) without understanding the
out-of-order-chunk-completion problem it solves — chunks are processed by a Celery worker pool and
can complete in any order; this condition is what guarantees the session only finalizes after
*every* enqueued chunk has actually reported back, not just after the `end` frame arrives. Also:
`db.rollback()` right before the loop starts (see entry on database/idle-in-transaction, this file
Section 22) — removing it reintroduces a real, previously-fixed Postgres connection-pinning bug.

**Dependencies affected:** `backend/core/pubsub.py` (`subscribe()`) if you change how results are
relayed between the worker and API tiers — this is real Redis pub/sub when `CELERY_BROKER_URL` is
set, an in-process `asyncio.Queue` fan-out otherwise; a new message type must be published on the
same `session:{id}:results` channel to reach `listen_results()`.

**Tests to run:** `pytest tests/test_tasks.py -v` (materialize/ordering logic), a real WS smoke
test — `scripts/ws_smoke_test.py` and `scripts/v2_smoke_test.py` (against a running
`uvicorn backend.main:app`) are this project's actual integration-test tool for this path, since
`pytest`'s own coverage here is unit-level, not a real live-socket round trip. `android/test/
ws_messages_test.dart` for the Dart-side parsing.

**Expected result:** existing message types still round-trip exactly as before; a new message type
is dispatched correctly on both ends without breaking the `sealed class` exhaustiveness check in
Dart (the compiler will actually force you to handle a new case in every `switch` — a real safety
net this project relies on, don't work around it with a `default:` catch-all).

**Common mistakes:** changing a JSON field's name on one side only (this is the single highest-risk
class of bug in this entire codebase — see `docs/API_CONTRACT.md`'s note that `chunk_result`
already sends a `speaker_segments` field Flutter's `ChunkResultMessage.fromJson()` never reads, a
real existing discrepancy, not hypothetical). Forgetting the WS auth is a `?token=` query param,
not an `Authorization` header — the browser/Flutter WebSocket API can't set custom headers on the
opening handshake (see `transcribe.py`'s own docstring).

---

## 8. Change backend URL (where the Flutter app points)

**Files to inspect:** `android/lib/core/settings_controller.dart` (`SettingsController.
_defaultBaseUrl()`), the Settings screen (`android/lib/screens/settings/settings_screen.dart`) for
the user-editable field.

**Exact classes/functions:** `_defaultBaseUrl()` returns `http://10.0.2.2:8000` on Android
(the emulator's alias back to the host machine's loopback) or `http://127.0.0.1:8000` otherwise.
The actual value used at runtime is `SettingsController.baseUrl`, persisted via
`shared_preferences` (`_baseUrlKey`) and editable from the Settings screen — **not** a compile-time
constant.

**What to change:** for a permanent default change (e.g. pointing at a deployed server instead of
localhost), edit `_defaultBaseUrl()`. For your own local testing against a physical device, use the
Settings screen's editable field instead of changing code — that's exactly what it's for (see
`CLAUDE.md`'s "physical-device testing" notes on why `10.0.2.2` only works for the emulator and a
real device needs the host's LAN IP).

**What NOT to change:** don't hardcode a URL anywhere else in the app — every API/WS call goes
through `ApiClient`/`WsTranscribeClient`, both constructed with `settings.baseUrl` at the call
site, not a second copy of the URL.

**Dependencies affected:** none. If pointing at a non-`http`/non-loopback host, remember
`android/android/app/src/main/AndroidManifest.xml`'s `usesCleartextTraffic="true"` is required for
plain `http://`/`ws://` (see entry 27's TLS note) — a real HTTPS deployment wouldn't need this flag
at all.

**Tests to run:** none required for a URL-only change; `flutter test` won't catch a wrong URL since
it doesn't make real network calls. Manually verify by launching the app and checking Settings
shows/accepts the expected value, then attempting a login.

**Expected result:** the app successfully reaches the backend at the new address.

**Common mistakes:** for a physical-device test, forgetting the backend itself must also be
started with `--host 0.0.0.0` (`uvicorn backend.main:app --host 0.0.0.0 --port 8000`) — the default
`--reload`-only invocation binds loopback-only and a phone on the real Wi-Fi NIC gets silently
refused (a hang, not a clear error) — see `CLAUDE.md`'s "Known Open Issues" on this exact gap.

---

## 9. Add an API endpoint

**Files to inspect:** any existing router file in `backend/api/` as a template — `backend/api/
teacher.py` is a good one (shows the async-task-enqueue pattern; `backend/api/minutes.py` shows a
simpler synchronous-read pattern). `backend/main.py` (`app.include_router(...)` calls — this is
where a new router actually gets mounted). `backend/schemas/` for request/response Pydantic models.

**Exact classes/functions:** every route file exports an `APIRouter()` instance (e.g.
`router = APIRouter(prefix="/teachers", tags=["teacher-verification"])`); routes are added with
`@router.get/post/delete(...)` decorators; every route that needs a logged-in user takes
`current_user: User = Depends(get_current_user)` (from `backend.api.deps`) and every route that
touches the DB takes `db: DbSession = Depends(get_db)`.

**What to change:** create a new file under `backend/api/` (or add a route to an existing one if
it's a natural fit — e.g. a new `sessions.py` route belongs there, not in a new file), define your
Pydantic request/response schemas in `backend/schemas/` if the shape is nontrivial, then add
`app.include_router(your_module.router, prefix=API_PREFIX)` in `backend/main.py` — **all routes
are versioned under `/api/v1`** via that shared `API_PREFIX` constant; don't hardcode the prefix
inside your own router unless it needs to differ.

**What NOT to change:** don't put ML/pipeline logic directly in the route handler — if the new
endpoint needs to run inference, follow the existing pattern (enqueue a Celery task via
`.delay()`, return `202`, let the client poll) rather than calling `audio_service.run_pipeline()`
inline — that's exactly the blocking-event-loop bug this project's whole architecture exists to
avoid (see `CLAUDE.md`'s "Production Architecture" section). Don't import anything from
`backend/services/audio_service.py`, `diarization_service.py`, `teacher_verification_service.py`,
torch, faster_whisper, pyannote, or speechbrain directly into a `backend/api/*.py` file — this
would reintroduce ML imports into the API-tier process, defeating the whole point of the split
(verified in this project by directly checking `import backend.main` pulls in zero ML libraries —
don't be the change that breaks that invariant).

**Dependencies affected:** none, unless the new endpoint needs a new third-party package (add to
`requirements.txt`, and `requirements-api.txt` specifically if the route itself needs it in the
lean API-tier Docker image).

**Tests to run:** add a new `tests/test_<name>_api.py` following `tests/test_transcribe_api.py` or
`tests/test_minutes_api.py`'s pattern (FastAPI's `TestClient`, real SQLite test DB via
`tests/conftest.py`'s fixtures). Run the full `pytest tests/ -v` afterward to check nothing else
broke (e.g. a route ordering collision).

**Expected result:** the new route appears in FastAPI's auto-generated docs (`/docs`, since
`ENVIRONMENT=development` doesn't disable them) and responds correctly to a manual `curl`/Postman
call before you consider it done.

**Common mistakes:** forgetting `owner_id` scoping — every existing resource (`sessions`,
`teacher_enrollments`) is filtered by the current user's `owner_id` in `backend/services/
session_service.py`'s query functions; a new endpoint that returns another user's data without
this check is a real security bug, not a style nit. Forgetting rate limiting on a
credential/expensive endpoint — see `backend/core/rate_limit.py`'s `limiter` and the
`@limiter.limit(settings.rate_limit_xxx)` decorator pattern already used on `/auth/login`,
`/transcribe`, `/teachers/enroll`.

---

## 10. Change ASR model (swap Whisper for something else, or change model size)

**Files to inspect:** `backend/core/config.py` (`whisper_model_size`, `whisper_device`,
`whisper_compute_type`, `whisper_cpu_threads`), `backend/services/audio_service.py`
(`load_whisper_model()`, `transcribe_audio()`).

**Exact classes/functions:** `load_whisper_model()` constructs a `faster_whisper.WhisperModel`
from exactly those four config values. For a same-family size change (e.g. `small` → `medium`),
**no code changes are needed at all** — set the `WHISPER_MODEL_SIZE` env var (or edit the
`Settings.whisper_model_size` default) to any faster-whisper-supported size string
(`tiny`/`base`/`small`/`medium`/`large-v3`/etc.) or a Hugging Face repo ID. This project's own
`docs/ML_REPRODUCIBILITY.md` confirms the actual resolved model as of this pass is
`Systran/faster-whisper-small` (not `openai/whisper-small` directly) — faster-whisper resolves
plain size names to a Systran-maintained CTranslate2-converted repo automatically.

**What to change:** for a genuinely different ASR engine (not just a Whisper size), you'd rewrite
`load_whisper_model()` and `transcribe_audio()` entirely — `transcribe_audio()`'s return shape
(`{"text", "language", "language_probability", "speech_segments", "whisper_segments"}`, where each
segment has `start`/`end`/`text`/`avg_logprob`/`no_speech_prob`) is what every downstream stage
(glossary, diarization merge, teacher verification, minutes) expects; a replacement engine must
either produce this same shape or every downstream consumer needs updating too.

**What NOT to change:** don't swap the model without also reconsidering `beam_size`
(entry 11) and device/compute-type (entry 24) together — they interact (a larger model at a high
beam size on CPU can be dramatically slower; this project's own measured RTF was 2.4–2.9 on
`small`/int8/CPU, meaning even the current smallest practical setup is already slower than
real-time). Don't assume a fine-tuned checkpoint just drops in — `ai/finetuning/
convert_to_faster_whisper.py` exists specifically to convert a LoRA-merged HF checkpoint into the
CTranslate2 format `WhisperModel` needs; a raw `transformers`-format checkpoint will not load.

**Dependencies affected:** `requirements-worker.txt` (`faster-whisper`, `ctranslate2` — only the
worker tier ever imports these, per the API/worker split). A genuinely different engine
(WhisperX, e.g. — confirmed **not used anywhere** in this codebase per `CLAUDE.md`'s tech stack
table) would add a new dependency entirely.

**Tests to run:** `pytest tests/ -v` (nothing in the pure-logic test suite actually loads Whisper —
check `tests/conftest.py` for how model-dependent tests are skipped/mocked), then a real manual
run: `scripts/transcribe_audio.py recordings/lecture_preprocessed.wav` or a full smoke test
(`scripts/v2_smoke_test.py`) against a live backend, since transcription quality can only be judged
by listening/reading, not by an automated assertion.

**Expected result:** transcription still returns the same result shape; latency/RTF numbers change
(measure with `evaluation/latency.py`) — a larger model is slower but (usually) more accurate; a
smaller/quantized one is the opposite trade.

**Common mistakes:** changing `whisper_model_size` to a huge model without checking it fits in
available RAM/VRAM on the target machine (CPU-only `large-v3` int8 is a real multi-GB resident
model) — verify with the actual target hardware, not just that it loads on a dev machine with more
RAM.

---

## 11. Change ASR parameters (beam size, etc.)

**Files to inspect:** `backend/schemas/pipeline.py` (`PipelineOptions.beam_size`, default `5`),
`android/lib/models/pipeline_config.dart` (`kMinBeamSize`/`kMaxBeamSize`, each preset's
`beamSize`), `backend/services/audio_service.py` (`transcribe_audio(..., beam_size: int = 5)`,
passed straight through to `model.transcribe(clip, beam_size=beam_size)`).

**What to change:** `beam_size` is already a first-class, per-request, client-controlled parameter
— nothing needs unlocking to change it per-session (the Settings screen's advanced panel already
exposes it, per `CLAUDE.md`'s "Advanced settings panel with outcome-framed labels"). To change a
*default*, edit `PipelineOptions.beam_size`'s Pydantic default (Python) and the relevant
`PipelinePresets` entries (Dart) together — same "keep both copies in sync" caveat as chunk
duration (entry 4). To expose an ASR parameter faster-whisper supports but this project doesn't
yet (e.g. `temperature`, `vad_filter`, `condition_on_previous_text`), add it to both
`PipelineOptions` schemas (Python + Dart), thread it through `transcribe_audio()`'s
`model.transcribe(...)` call, and expose a UI control if it should be user-facing.

**What NOT to change:** `kMinBeamSize`/`kMaxBeamSize` (`1`–`10`) reflects this project's own tested
finding that faster-whisper's practical range for a CPU int8 model tops out around there — going
higher "just burns CPU with no real accuracy gain on this model size" per the code's own comment;
don't raise the ceiling without actually re-measuring.

**Dependencies affected:** none — this is a parameter within the existing faster-whisper call.

**Tests to run:** `pytest tests/test_transcribe_api.py`, `android/test/pipeline_config_test.dart`
(if you touch preset defaults). Manually verify actual transcription quality/speed trade-off with
`evaluation/latency.py` and a real audio file — beam size's effect is not something a unit test
can meaningfully assert on.

**Expected result:** transcription latency scales roughly with beam size; accuracy differences are
usually marginal below ~8 on a small model per general faster-whisper behavior — measure, don't
assume.

**Common mistakes:** forgetting `beam_size` is threaded through `PipelineOptions.model_dump()` and
sent as a `dict` from `backend/api/transcribe.py`'s `.delay()` calls — a new ASR parameter needs
adding to `PipelineOptions` specifically (not just passed as a stray kwarg somewhere), or it'll
never survive the Celery task serialization boundary between the API and worker tiers.

---

## 12. Change language configuration (which languages are recognized/expected)

**Files to inspect:** `CLAUDE.md`'s "Language Scope (CRITICAL)" section (trilingual-only:
Hiligaynon, Filipino, English — a locked project rule, not just a code default),
`backend/services/audio_service.py` (`transcribe_audio()` — note there is **no forced-language
argument passed to `model.transcribe()`**; Whisper auto-detects per segment), `backend/services/
keyword_service.py` (`_STOPWORDS` — the trilingual stopword set), `backend/data/glossary.json`
(trilingual term corrections), `backend/services/minutes_service.py` (`_ACTION_TRIGGERS`,
`_DEFINITION_PATTERNS` — trilingual regex patterns).

**What to change:** Whisper itself needs no per-language config change since it's multilingual and
auto-detecting already — "changing language configuration" in this codebase almost always means
editing the trilingual *auxiliary* logic (glossary terms, stopwords, action/definition patterns),
not the ASR call itself.

**What NOT to change:** don't add a `language=` argument to `model.transcribe()` to "force" one of
the three languages — that would break code-switching support entirely (a session that's
genuinely multilingual within itself would get every segment mis-transcribed as whichever language
you forced). The whole point of this pipeline (per the thesis's own research questions) is
per-segment auto-detection precisely because speakers switch languages mid-session.

**Dependencies affected:** none.

**Tests to run:** `pytest tests/test_keyword_service.py`, `pytest tests/test_minutes_service.py`,
`pytest tests/test_glossary_service.py`.

**Expected result:** unchanged transcription behavior; changed keyword/minutes/glossary output for
whichever language-specific patterns you edited.

**Common mistakes:** using "Tagalog" anywhere in code, comments, or docs — `CLAUDE.md` explicitly
calls this an ERROR; the correct designation in this project is "Filipino." Also: **Kinaray-a was
explicitly considered and cut** — don't add it back without checking with whoever owns scope
decisions (`CLAUDE.md`'s "Explicitly Out of Scope" list).

---

## 13. Add another language

**Files to inspect:** same four files as entry 12, plus `CLAUDE.md`'s "Language Scope (CRITICAL)"
section itself (you are changing a documented, locked project decision, not just code).

**What to change:** Whisper's multilingual model already supports far more languages than the
three this project targets — technically, no ASR-side code change is needed for Whisper to
*attempt* a fourth language; it already will if the audio contains it (there's no allow-list on
`model.transcribe()`'s language detection). What you'd actually need to add: entries in
`_STOPWORDS` (`keyword_service.py`) for the new language's function words, entries in
`glossary.json`'s `terms` dict for known correction pairs, new regex alternatives in
`_ACTION_TRIGGERS`/`_DEFINITION_PATTERNS` (`minutes_service.py`) for that language's phrasing.

**What NOT to change:** don't do this without first updating `CLAUDE.md`'s "Language Scope
(CRITICAL)" section and getting sign-off — this is explicitly called a locked decision
("TRILINGUAL ONLY... 'Quadrilingual' anywhere in code, comments, or docs is an ERROR"), and this
document's own convention (see `ARCHITECTURE_DECISIONS.md`) is that locked scope decisions are the
project owner's call, not something to route around silently.

**Dependencies affected:** none — no new package is needed to *attempt* recognizing another
language Whisper already knows; a genuinely low-resource language absent from Whisper's training
data would need its own fine-tuning effort, mirroring the Hiligaynon LoRA/PEFT scaffold in
`ai/finetuning/` (currently untrained — see `docs/ML_REPRODUCIBILITY.md`).

**Tests to run:** same as entry 12.

**Expected result:** glossary/keyword/minutes quality improves for the new language's content;
core transcription behavior is otherwise unaffected (Whisper was already capable of it).

**Common mistakes:** assuming you need to "enable" a language somewhere — there is no such switch
in this codebase; the entire mechanism is Whisper's own built-in multilingual detection plus this
project's own auxiliary trilingual pattern-matching layers, which is exactly what needs extending.

---

## 14. Change code-switching processing (glossary-based correction)

**Files to inspect:** `backend/services/glossary_service.py` (`Glossary` class, `load_glossary()`),
`backend/data/glossary.json` (the actual term data — a hand-edited starter list per its own
`_meta` field, "not derived from real Whisper error logs yet").

**Exact classes/functions:** `Glossary.__init__(terms: dict[str, str])` builds a single compiled
regex (`\b(?:term1|term2|...)\b`, case-insensitive, longest-phrase-first) from the `terms` dict's
keys; `Glossary.apply(text)` runs that regex against transcribed text and case-preserves the
replacement via `_replace_match()`. This runs **once per Whisper segment, immediately after
transcription**, inside `transcribe_audio()` — see `audio_service.py`'s
`corrected_text = glossary.apply(seg.text.strip())`.

**What to change:** to add/edit corrections, edit `backend/data/glossary.json`'s `terms` object
directly — no code change needed for new term pairs; the mechanism already handles arbitrary
entries. To change *how* matching/replacement works (e.g. fuzzy matching instead of exact phrase
match), you'd modify `Glossary.__init__`/`apply()`/`_replace_match()` themselves.

**What NOT to change:** don't add an empty-string or whitespace-only key to `glossary.json` — this
was a real, fixed bug (`glossary_service.py`'s own comment: an empty key used to compile to a
regex matching every word boundary, splicing the replacement in everywhere); the current
`Glossary.__init__` filters these out defensively, but don't rely on that filter as a substitute
for just not doing it. Keep `glossary.json` saved as UTF-8 — a Windows editor saving it as
ANSI/cp1252 crashes worker startup with a clear error (`load_glossary()`'s `UnicodeDecodeError`
handling), by design, rather than silently corrupting non-ASCII characters.

**Dependencies affected:** none.

**Tests to run:** `pytest tests/test_glossary_service.py -v`.

**Expected result:** the corrected term appears verbatim (case-matched to the original) in place
of every case-insensitive match in subsequent transcripts.

**Common mistakes:** adding a mixed-case key expecting case-sensitive matching — matching is
always case-insensitive by design (`re.IGNORECASE`); only the *replacement*'s case is adapted to
match what was actually said. Forgetting "longest phrase first" ordering matters — if you add both
`"ma am"` and `"ma am po"` as separate keys, the class already handles the ordering correctly
internally (sorts by key length), so you don't need to order the JSON dict yourself, but you do
need both entries if you want both phrasings corrected — one doesn't imply the other.

---

## 15. Change VAD (voice activity detection)

**Files to inspect:** there are **two independent VAD implementations** in this project — know
which one you mean before editing:
- **Server-side (real ML model):** `backend/services/audio_service.py`'s `detect_speech()`, using
  Silero VAD (`silero_vad.get_speech_timestamps`/`load_silero_vad`, from the `silero-vad` pip
  package — the model weights are bundled inside the package itself, no network download; see
  `docs/ML_REPRODUCIBILITY.md`). This decides which parts of each chunk/file actually get sent to
  Whisper.
- **Client-side (non-ML energy gate):** `android/lib/core/local_vad.dart`'s `LocalVad` class
  (windowed RMS/energy check) plus `android/lib/core/pcm_chunker.dart`'s `_gate()` method — this
  decides whether an outgoing chunk is even worth *sending* to the server at all, before any
  server-side processing happens.

**Exact classes/functions:** server-side: `detect_speech(audio_path, enable_vad, silero_vad_model)`
— when `enable_vad=False`, returns one synthetic whole-file segment instead of running the model at
all (used by the "Fast" preset's implicit config and any explicit toggle-off). Client-side:
`LocalVad.hasSpeech(Uint8List pcm16le)` — splits into ~30ms sub-frames, RMS per sub-frame, `true` if
*any* sub-frame clears `threshold` (default ≈ −40 dBFS). `PcmChunker._gate()` combines `hasSpeech()`
with a 1-chunk hangover (`_lastChunkHadSpeech`) and a keepalive heartbeat
(`keepAliveInterval`, default 30s, forces a chunk through periodically even during genuine silence
so the WS connection doesn't sit idle long enough to trip a NAT/proxy timeout).

**What to change:** server-side VAD sensitivity: nothing in this codebase directly exposes Silero's
own threshold knobs — `get_speech_timestamps()` is called with only `sampling_rate`; you'd add
Silero's own tunable kwargs (e.g. `threshold`, `min_speech_duration_ms`) to that call if you need
finer control. Client-side sensitivity: `LocalVad`'s `threshold` constructor argument (normalized
RMS, default `0.01`) — documented in its own class comment as an "unvalidated heuristic default,"
same caveat style as the teacher-verification threshold (entry 18).

**What NOT to change:** don't confuse the two VADs when debugging a "missing speech" report — check
which stage actually dropped it (client-side `LocalVad` never sends the chunk at all, so the
server never even sees it; server-side Silero VAD receives the chunk but excludes it from
transcription). Don't remove `PcmChunker`'s 1-chunk hangover or keepalive heartbeat casually — both
close real, previously-identified gaps (trailing speech clipped at a chunk boundary; a long silent
stretch tripping a connection timeout).

**Dependencies affected:** `requirements-worker.txt` (`silero-vad`) for server-side; none for
client-side (pure Dart, no package).

**Tests to run:** `android/test/local_vad_test.dart`, `android/test/pcm_chunker_test.dart`
(includes the `'PcmChunker VAD gating'` group testing the hangover sequence specifically), and on
the backend, any test exercising `detect_speech()` (check `tests/test_tasks.py` for pipeline-level
coverage — there's no dedicated `test_vad.py` file at present).

**Expected result:** server-side change affects which portions of audio get transcribed at all;
client-side change affects how many chunks even leave the phone (a stricter/looser threshold
directly changes bandwidth usage and how much silence-adjacent speech gets clipped).

**Common mistakes:** testing client-side VAD changes only on an emulator — its virtual mic is
silent, so nearly every chunk is gated except the guaranteed-first-chunk and periodic keepalives;
this is real and expected (see `CLAUDE.md`'s documented gap on this), but it means an emulator run
alone can't validate a *sensitivity* threshold change — you need real audio (recorded file played
through, or a physical device) to judge that.

---

## 16. Change noise reduction (denoising)

**Files to inspect:** `backend/services/audio_service.py`'s `clean_audio()` and `DENOISE_FILTER`
constant. **Read `docs/GIT_HISTORY.md`'s "Replaced models / libraries" section first** — this
stage has a real, documented history of breaking (RNNoise → pyrnnoise → the current FFmpeg
`afftdn`), and the reasons for landing on `afftdn` specifically (a Python-dependency dead-end, not
a preference) matter before you touch this again.

**Exact classes/functions:** `clean_audio(input_path, enable_denoise)` — when `enable_denoise=
False` (the default), returns `input_path` unchanged, doing nothing at all (not even invoking
FFmpeg). When enabled, runs one `subprocess.run(["ffmpeg", "-i", ..., "-af", DENOISE_FILTER, ...])`
call. `DENOISE_FILTER = "afftdn=nr=12:nf=-25:tn=1"` — `nr` (reduction amount, 12 = FFmpeg's
moderate default), `nf` (noise floor, raised from FFmpeg's own −50dB default to −25dB for
classroom-ambient-level noise), `tn=1` (track non-stationary noise rather than lock to the first
frame).

**What to change:** to tune aggressiveness, edit the `nr`/`nf`/`tn` values in `DENOISE_FILTER`
directly (it's a single FFmpeg filtergraph string — see FFmpeg's own `afftdn` filter docs for the
full parameter set). These are explicitly flagged in the code's own comment as an "unvalidated
starting point... tune against real noisy classroom recordings once they exist" — this is exactly
the kind of change that's expected to happen, just needs real audio to validate against, not
guesswork.

**What NOT to change:** don't reintroduce `pyrnnoise`/RNNoise — it is fully removed from
`requirements.txt`/`requirements-worker.txt` and known-broken against this project's other
dependencies on Python 3.11 (see `docs/GIT_HISTORY.md`). Don't remove the `finally`-block cleanup
in `run_pipeline()` that deletes `cleaned_path` — a prior version of this exact function leaked
temp files on every exception path before that fix.

**Dependencies affected:** none — `afftdn` is a built-in FFmpeg filter, no Python package.

**Tests to run:** `pytest tests/test_audio_denoise.py -v` (includes a real noise-floor before/after
check and a filtergraph-validity check).

**Expected result:** denoised output measurably reduces a synthetic/real noise floor without
audibly damaging speech — listen to the actual output, don't just trust that FFmpeg exited `0`.

**Common mistakes:** cranking `nr` very high expecting "more denoising is always better" — FFT
denoisers like `afftdn` introduce audible artifacts ("musical noise") at aggressive settings that
can hurt Whisper's transcription accuracy more than the original noise did; this needs real
before/after WER comparison (`evaluation/wer.py`), not ear-only judgment, before shipping a change.

---

## 17. Change teacher voice recognition

**Files to inspect:** `backend/services/teacher_verification_service.py` (the whole
identification mechanism), `backend/services/audio_service.py`'s `apply_teacher_verification()`
(how it's invoked per-segment), `backend/api/teacher.py` (the enrollment endpoint),
`backend/worker/tasks.py`'s `enroll_teacher_task` (where enrollment embeddings actually get
computed).

**Exact classes/functions:** `load_verification_model()` loads SpeechBrain's
`EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb", ...)` once per worker
process. `extract_embedding(model, waveform)` returns a 192-dim (ECAPA's own output size) `list[
float]` embedding. `verify_segment(model, waveform_slice, enrolled_teachers, threshold)` computes
cosine similarity against every enrolled teacher and returns
`{"is_teacher", "teacher_name", "confidence"}` for the best match. `apply_teacher_verification()`
in `audio_service.py` calls this once per Whisper segment (not per diarized speaker turn — a
structural fact documented in `CLAUDE.md`'s "What this is NOT" section), skipping segments shorter
than 0.3s as too short to embed reliably.

**What to change:** to change the underlying speaker-embedding model, edit
`settings.speaker_verification_model` (`backend/core/config.py`) to a different SpeechBrain-
compatible model ID (must work with `EncoderClassifier.from_hparams`) — this is a config-only
change if the replacement model has the same interface. A genuinely different embedding framework
(not SpeechBrain) would require rewriting `load_verification_model()`/`extract_embedding()`
entirely; `cosine_similarity()` and `verify_segment()`'s logic are framework-agnostic (they operate
on plain `list[float]` embeddings) and wouldn't need to change as long as the new model also
produces fixed-length embeddings.

**What NOT to change:** don't move teacher verification to run *before* transcription — see
`CLAUDE.md`'s "Pipeline Order (Locked)" section: this stage structurally needs Whisper's segments
to already exist, since it slices the waveform by segment timestamps, not by diarized turns. This
was tried conceptually (per the thesis manuscript) and found not implementable as literally
described — don't re-attempt without understanding why (`docs/paper-vs-implementation.md`).

**Dependencies affected:** `requirements-worker.txt`'s `speechbrain` line; the `models/` directory
(gitignored) caches the downloaded checkpoint — deleting it forces a re-download on next use.

**Tests to run:** no dedicated `test_teacher_verification_service.py` at present — check
`tests/test_session_service.py`/`tests/test_tasks.py` for any coverage that exercises the
enrollment/verification flow; add tests if you're changing core logic, following this project's
existing pattern of pure-function unit tests (mock the embedding vectors, don't require the actual
model to be downloaded to test `cosine_similarity`/`verify_segment`'s branching logic).

**Expected result:** a real enrolled voice scores meaningfully higher cosine similarity against
itself than against unrelated voices/silence/noise — `CLAUDE.md`'s round-8 functional check found
0.66–0.88 for a matching voice vs. 0.04–0.12 for pitch-shifted/silence/noise, a clean separation;
re-verify this kind of separation holds after any change here.

**Common mistakes:** assuming a higher-dimensional or "better" embedding model automatically
improves teacher-ID accuracy without re-tuning `teacher_verification_threshold` (entry 18) —
different embedding spaces have different typical cosine-similarity ranges; the current `0.35`
default is specifically calibrated (informally) around ECAPA-TDNN/VoxCeleb's typical operating
point, not a universal constant.

---

## 18. Change speaker similarity threshold

**Files to inspect:** `backend/core/config.py` (`Settings.teacher_verification_threshold`, env var
`TEACHER_VERIFICATION_THRESHOLD`, default `0.35`), `backend/services/
teacher_verification_service.py`'s `verify_segment()` (where it's actually applied:
`is_teacher = best_score >= similarity_threshold`).

**What to change:** set the `TEACHER_VERIFICATION_THRESHOLD` env var, or edit the `Settings`
default directly. No code change needed beyond that — the threshold is already a first-class,
per-call-overridable parameter (`verify_segment(..., threshold: float | None = None)` falls back
to the config default only when not explicitly passed).

**What NOT to change:** don't hardcode a threshold value somewhere else that bypasses this single
source of truth — every call site in this codebase goes through `settings.
teacher_verification_threshold` or an explicit override on `verify_segment()` itself.

**Dependencies affected:** none.

**Tests to run:** any test exercising `verify_segment()`'s branching (mock `cosine_similarity`'s
result and assert on the boundary condition, both just above and just below the threshold —
`>=`, not `>`, so an exact-threshold score counts as a match).

**Expected result:** raising the threshold reduces false-positive teacher matches at the cost of
more false-negatives (real teacher speech mislabeled as non-teacher), and vice versa for lowering
it. This is a genuine precision/recall trade-off — `evaluation/teacher_id.py` exists specifically
to measure precision/recall/F1/FAR/FRR against labeled data once real classroom recordings with
ground truth exist; per `CLAUDE.md`, this has never actually been run against real data, so the
current `0.35` is a documented heuristic, not an empirically-tuned value.

**Common mistakes:** tuning this threshold based on a handful of manual spot-checks instead of
running `evaluation/teacher_id.py` against a proper labeled dataset — a threshold that "feels
right" on 3 examples can easily be badly miscalibrated at scale.

---

## 19. Change summarization (keyword extraction / TextRank)

**Files to inspect:** `backend/services/keyword_service.py` — the entire TextRank implementation.
**Important context:** there is no LLM anywhere in this pipeline; "summarization" here means
TextRank keyword/keyphrase extraction plus the separate rule-based minutes generator (entry 20) —
not an abstractive summary in the generative-AI sense. Confirm you actually mean this stage before
editing, since "change summarization" could reasonably mean either this file or
`minutes_service.py`.

**Exact classes/functions:** `extract_keywords(text, top_n=10)` — tokenize
(`_WORD_PATTERN`, `_tokenize()`) → drop stopwords (`_STOPWORDS`, a hand-curated trilingual set) →
build a sliding-window (`_WINDOW_SIZE = 4`) co-occurrence graph (`networkx.Graph`) → PageRank
(`nx.pagerank`, with a weighted-degree-centrality fallback if PageRank fails to converge) → merge
adjacent top-ranked tokens back into phrases (`_merge_into_keyphrases()`). `build_weighted_text()`
repeats teacher-labeled segments in the input text before extraction so instructional speech
dominates the resulting keyword list.

**What to change:** `_WINDOW_SIZE` (co-occurrence window width), `top_n`'s default, `_STOPWORDS`
(add/remove terms — see entry 12/13 for language-specific additions), `teacher_weight` in
`build_weighted_text()` (how much more heavily teacher speech counts — default `2.0`, i.e. counted
twice).

**What NOT to change:** don't swap this for an LLM-based approach without understanding that's a
significant, documented architectural property of this project, not an oversight —
`CLAUDE.md`'s "What this is NOT" section states explicitly: "There is no LLM anywhere in this
pipeline... not a generative model call." If you're deliberately changing this, that's a real
scope decision worth flagging, not a routine tweak.

**Dependencies affected:** `networkx` (already a dependency; no new package for tuning existing
logic). An LLM-based swap would add a new dependency (an API client or a local-inference library)
entirely outside this project's current shape.

**Tests to run:** `pytest tests/test_keyword_service.py -v`.

**Expected result:** different/reranked keywords for the same input text; verify manually that the
output still looks like plausible topic words, not just that the code runs — TextRank quality is
not something an existing unit test's fixed input/output pairs alone can fully validate for a
tuning change.

**Common mistakes:** forgetting `build_weighted_text()`'s teacher-weighting is a no-op when
`enable_teacher_verification` was off for a session (no `is_teacher` labels exist to check) — don't
"fix" this as if it were a bug; it's documented, intentional graceful degradation.

---

## 20. Change generated minutes (structure/content of the minutes output)

**Files to inspect:** `backend/services/minutes_service.py` — the entire rule-based generator.
`backend/models/session.py`'s `SessionRecord.minutes` (JSON column — the storage shape).

**Exact classes/functions:** `generate_minutes(segments, keywords, topic_gap_seconds,
total_duration_seconds)` is the single entry point, called once per session at finalize time (in
the API process, not the worker — see `CLAUDE.md`'s architecture diagram, this is deliberately
cheap pure-Python work). It orchestrates: `_group_into_topics()` (groups segments into topic
blocks by silence-gap, default `topic_gap_seconds=8.0` from `settings.topic_gap_seconds`),
`_label_topic()` (keyword match, teacher-speech-first), `_key_points()` (teacher-labeled segments
ranked first, then longest-first), `_find_definitions()` (trilingual regex pattern matching against
`_DEFINITION_PATTERNS`), `_find_action_items()` (trilingual trigger-phrase matching against
`_ACTION_PATTERN`), `_participants()`, `_teacher_speech_ratio()`, `_teacher_speakers()`.

**What to change:** to add a new minutes field (e.g. "questions asked"), add a new private
`_find_xxx()` function following the existing pattern, call it inside `generate_minutes()`'s
return dict, and update `backend/models/session.py`'s docstring comment on the `minutes` column
(it's a loose JSON blob, so no schema migration is needed, but the shape should stay documented
somewhere). To change topic grouping sensitivity, adjust `settings.topic_gap_seconds`. To change
action-item/definition detection, edit `_ACTION_TRIGGERS`/`_DEFINITION_PATTERNS`'s regex lists.

**What NOT to change:** don't forget any new field needs `.get()`-style defensive access wherever
it's read back out (see `backend/api/minutes.py`'s `_render_minutes()`, which uses
`minutes.get("teacher_speech_ratio")` specifically because older finalized sessions in the DB won't
have newer fields — a `KeyError` there would break exporting minutes generated before your change).
Don't change `_key_points()`'s teacher-ranking-first behavior without checking it's still a no-op
(pure-length sort) when no segment carries an `is_teacher` label — this graceful-degradation
property is deliberate, not incidental.

**Dependencies affected:** none.

**Tests to run:** `pytest tests/test_minutes_service.py -v`, `pytest tests/test_minutes_api.py -v`
(covers the export-rendering path specifically, including the `0.0`-ratio-not-dropped regression
test).

**Expected result:** the new/changed field appears correctly in both `GET /sessions/{id}/minutes`
(raw JSON) and `GET /sessions/{id}/minutes/export` (rendered markdown/text) — check both, they're
two separate code paths (`minutes_service.py` builds the dict; `minutes.py`'s `_render_minutes()`
independently formats it for export).

**Common mistakes:** treating this as an NLP problem worth throwing more regex at indefinitely —
the code's own comments repeatedly flag this as "pattern matching, not NLP... precision/recall
unmeasured until real classroom audio exists." Improving *precision* (fewer false positives) is
usually safer to reason about locally than improving *recall* (catching more real cases), which
needs real labeled data to validate against.

---

## 21. Change DOCX output

**There is currently no DOCX output anywhere in this application.** Before making this change,
confirm this is actually what's needed — `backend/api/minutes.py`'s `export_minutes()` endpoint
only supports `format="markdown"` or `format="txt"` (`PlainTextResponse`, not a binary file). This
was explicitly checked this session: `python-docx` is listed in `CLAUDE.md`'s tech stack table as
"**NOT USED ANYWHERE**... despite this appearing in some early conceptual-framework drafts."

**Files to inspect (if actually adding DOCX export, a new feature, not a "change"):**
`backend/api/minutes.py` (`export_minutes()`, `_render_minutes()` — the closest existing analog),
`requirements.txt`/`requirements-api.txt` (would need `python-docx` added — it's currently absent
from every requirements file in this project).

**What to change:** you would add a new `format="docx"` branch to `export_minutes()`, build a
`docx.Document()` from the same `session.minutes` dict `_render_minutes()` already knows how to
walk (topics/key-points/definitions/action-items), and return it via FastAPI's `Response` with
`media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"` instead of
`PlainTextResponse`.

**What NOT to change:** don't confuse this with the actual thesis manuscript `.docx` file at the
repo root — that is Nathan's own document, never programmatically generated by this app, and under
a standing rule to never be committed to git. A new DOCX-export *feature* for minutes is unrelated
to that file.

**Dependencies affected:** would add `python-docx` as a genuinely new dependency to
`requirements.txt`/`requirements-api.txt` (lean API-tier image — this feature would run in the API
process alongside the other export formats, not the worker tier, since it's pure formatting, no
ML).

**Tests to run:** a new test following `tests/test_minutes_api.py`'s pattern, asserting the
returned content is a valid `.docx` (e.g. round-trip it through `python-docx`'s own reader).

**Expected result:** N/A until built — this is scoped as "not yet implemented," not "broken."

**Common mistakes:** assuming this exists somewhere already because an early manuscript draft
described it — it doesn't; `CLAUDE.md`'s own note flags this exact discrepancy explicitly so a
future developer doesn't waste time looking for it.

---

## 22. Change database behavior

**Files to inspect:** `backend/database/db.py` (engine/session setup, `init_db()`,
`get_db()`), `backend/models/session.py`/`teacher.py`/`user.py` (the three ORM models — see entry
9's note on `owner_id` scoping), `backend/database/migrations/` (Alembic, Postgres path only).

**Exact classes/functions:** `Base` (SQLAlchemy declarative base, imported by every model file).
`init_db()` calls `Base.metadata.create_all(...)` — this is what auto-creates tables for the SQLite
dev path; it's a no-op against a Postgres DB Alembic has already migrated (`checkfirst=True` is
`create_all()`'s default). `get_db()` is the FastAPI dependency every route/WS handler uses to get
a session-scoped `DbSession`.

**What to change:** to add a new column to an existing model, add the `Mapped[...]` field to the
relevant model class in `backend/models/`; for SQLite dev, `init_db()`'s `create_all()` picks it up
automatically on a fresh DB (but **not** on an existing SQLite file with the old schema — delete
`backend/database/scaitale.db` in dev, or write a real migration). For Postgres, you must write a
new Alembic migration (`alembic revision --autogenerate -m "..."` from the repo root, with
`DATABASE_URL` pointed at a real Postgres instance, then review the generated migration file by
hand before applying it — autogenerate is a starting point, not a guarantee).

**What NOT to change:** don't add a new relational table for something like individual transcript
segments without first reading `backend/models/session.py`'s own docstring — this project made a
deliberate, documented choice to denormalize (JSON columns for `chunk_results`/
`transcript_segments`/`speaker_segments`/`minutes`) because "a thesis-prototype session library
doesn't need to query across segments relationally." Revisiting that is a real architectural
decision, not a routine change — see `docs/ARCHITECTURE_DECISIONS.md` for the full reasoning
before deciding to normalize it.

**Dependencies affected:** `psycopg` (Postgres driver, only touched if `DATABASE_URL` points at
Postgres), `alembic`.

**Tests to run:** `pytest tests/test_session_service.py -v` (includes the real-Postgres row-lock
concurrency test, skipped unless `DATABASE_URL` points at a real Postgres instance — run it against
your native Postgres install if you're touching anything concurrency-related, not just the
default SQLite-backed suite). Full `pytest tests/ -v` afterward.

**Expected result:** SQLite dev/test path continues to need zero extra setup; a Postgres migration
applies cleanly with `alembic upgrade head` and reverses cleanly with `alembic downgrade base`
(verify both directions, per `CLAUDE.md`'s own verification note for the original migration).

**Common mistakes:** forgetting `with_for_update=True` when reading a row you're about to
read-modify-write under potential multi-worker contention — `session_service.
append_chunk_result()`'s use of this exact pattern (added specifically after a real, proven data-
loss bug — see `CLAUDE.md`'s round 6) is the template to follow for any new mutate-under-
contention code path. This is a no-op on SQLite (whose dialect has no `FOR UPDATE`, and which
serializes writes at the whole-database level anyway) but a real fix on Postgres — don't assume
"it works in dev" (SQLite) means it's safe under the real multi-worker Postgres deployment.

---

## 23. Change authentication

**Files to inspect:** `backend/core/security.py` (`hash_password`, `verify_password`,
`create_access_token`, `decode_access_token`, `get_current_user`,
`get_current_user_from_token_string`), `backend/api/auth.py` (register/login routes),
`backend/api/deps.py` (re-exports `get_current_user`/`get_db` for route files to import from a
single place).

**Exact classes/functions:** passwords are hashed with `bcrypt` **directly**, not via passlib's
`CryptContext` — this is a deliberate, documented choice (passlib 1.7.4 is unmaintained and breaks
against modern bcrypt's version metadata; see the module's own docstring). JWTs are signed with
`PyJWT` (`HS256`, `JWT_SECRET_KEY` env var, `ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12`, i.e. 12
hours — chosen for a mobile app that doesn't want to force re-login every session, unlike a
browser session's typical shorter expiry). `get_current_user` is the standard `Depends()`-chain
version for HTTP routes (via `OAuth2PasswordBearer`); `get_current_user_from_token_string` is the
WS-specific version (no `Depends()` chain available inside a WebSocket handler, so the `?token=`
query param is decoded manually — see entry 7).

**What to change:** to change token expiry, edit `ACCESS_TOKEN_EXPIRE_MINUTES`. To add
role-based access (currently **not implemented** — a single undifferentiated `User` model, per
`CLAUDE.md`'s Status Report table and `docs/future_ideas.md`), you'd add a `role` column to
`backend/models/user.py`, a migration, and a new `Depends()`-based check (e.g.
`require_role("admin")`) layered on top of `get_current_user` in whichever routes need it.

**What NOT to change:** don't switch back to passlib's `CryptContext` — this is a known-broken
combination against the bcrypt version this project installs, confirmed directly (not a
hypothetical compatibility concern). Don't remove the `_BCRYPT_MAX_BYTES = 72` truncation in
`hash_password()`/`verify_password()` — this is bcrypt's own hard algorithmic limit (it silently
ignores bytes past 72), not an arbitrary choice; removing the truncation wouldn't cause a bug so
much as make the actual limiting behavior less visible in the code.

**Dependencies affected:** `bcrypt`, `PyJWT` — both already pinned; a role-based-access addition
needs no new dependency, just schema + route changes.

**Tests to run:** `pytest tests/test_security.py -v` (includes JWT-tampering coverage — a
previously-fixed test flake, per `docs/GIT_HISTORY.md`'s commit `89d6b6e`).

**Expected result:** login/register continue to work; token expiry/role changes are enforced
exactly where you added the check, nowhere else silently.

**Common mistakes:** forgetting `JWT_SECRET_KEY` must be identical across every process reading a
given token — in the real (non-eager) deployment, the API process and every worker process must
share the same value (env var, not a per-process random default) or tokens issued by one won't
validate consistently; `security.py`'s own comment flags exactly this risk.

---

## 24. Change GPU/CPU configuration

**Files to inspect:** `backend/core/config.py` (`whisper_device`, `whisper_compute_type`,
`whisper_cpu_threads`), `backend/services/audio_service.py` (`load_whisper_model()`).
**Read `CLAUDE.md`'s "GPU/CUDA note" first** — confirmed by direct execution this session: the
installed `torch` build in this project's `.venv` is `2.13.0+cpu` (`torch.cuda.is_available() ==
False`), despite the dev machine having a working, idle RTX 3050 (`nvidia-smi` confirms it).
**Zero references to `cuda`/`gpu`/`.to(device)` exist anywhere in `backend/`** except the one
`WHISPER_DEVICE` knob — SpeechBrain and pyannote have no device-selection code path in this
codebase at all currently.

**What to change:** to move Whisper to GPU: (1) reinstall a CUDA-enabled `torch` build (not just
flip a setting — the currently-installed wheel is physically CPU-only), (2) set
`WHISPER_DEVICE=cuda` (env var, read by `Settings.whisper_device`), (3) reconsider
`whisper_compute_type` — `int8` is a CPU-oriented choice; a GPU deployment would typically use
`float16` instead for better throughput. To also move SpeechBrain/pyannote to GPU, you'd need to
add device-selection code to `teacher_verification_service.py`'s `load_verification_model()`
(SpeechBrain's `EncoderClassifier.from_hparams` accepts a `run_opts={"device": "cuda"}` kwarg) and
`diarization_service.py`'s pipeline loading (pyannote's `Pipeline` has its own `.to(torch.device(
...))` call) — **neither of these currently has any such code**, so this is new code, not a config
flip, for those two models.

**What NOT to change:** don't assume setting `WHISPER_DEVICE=cuda` alone does anything useful
without first confirming (`python -c "import torch; print(torch.cuda.is_available())"`) that the
installed torch build actually has CUDA support — with the current CPU-only wheel, setting this
env var would just make `WhisperModel(...)` fail to load outright, not silently fall back to CPU.

**Dependencies affected:** `torch`/`torchaudio` (a CUDA build is a different wheel entirely,
typically installed via a specific `--index-url` pointing at PyTorch's CUDA-build index — not the
default PyPI wheel this project currently installs) — this affects `requirements-worker.txt`.

**Tests to run:** `pytest tests/ -v` (nothing in the pure-logic suite requires a GPU; it should
pass identically either way). Manually verify with `evaluation/latency.py` before/after — every
measured performance number in this project's history to date, per `CLAUDE.md`, is a CPU number,
so this is genuinely unmeasured territory, not a regression check against known GPU numbers.

**Expected result:** if done correctly, transcription/verification/diarization latency drops
substantially (Whisper on GPU is typically several times faster than CPU int8 for the same model
size) — but this needs to actually be measured on this specific hardware/model combination, not
assumed from general Whisper benchmarks.

**Common mistakes:** installing a CUDA-enabled torch wheel that doesn't match the machine's
installed CUDA/driver version (`nvidia-smi`'s reported "CUDA Version" is the *maximum* the driver
supports, not necessarily what's installed as a toolkit) — check PyTorch's own install-matrix
before picking a wheel.

---

## 25. Add logging

**Files to inspect:** `backend/core/logging.py` (`configure_logging()`, `get_logger()` — shared,
deliberately starlette-free so the worker-tier Docker image never needs to import starlette
transitively), `backend/core/request_context.py` (the request-ID contextvar + HTTP middleware,
API-tier only, genuinely needs starlette).

**Exact classes/functions:** `get_logger(name: str)` returns a standard-library `logging.Logger`
configured with a JSON formatter by `configure_logging()` (called once, at each process's own
startup — see `backend/main.py`'s and `backend/worker/celery_app.py`'s respective top-level calls).
Existing usage pattern: `_logger = get_logger("scaitale.<component>")` at module level, then
`_logger.info(...)`/`_logger.warning(...)`/`_logger.error(...)` calls.

**What to change:** to add logging to a new or existing module, follow that exact pattern —
`from backend.core.logging import get_logger; _logger = get_logger("scaitale.<your_module>")` —
don't use a bare `print()` anywhere in backend code. This was a real, previously-fixed bug: an
earlier version of `celery_app.py` used raw `print()`, which is precisely why `logging.py` and
`request_context.py` were split apart in the first place (see `docs/GIT_HISTORY.md`'s `796760c`
entry) — worker log output needs to go through the shared structured logger so it's actually
capturable/parseable, not lost to stdout.

**What NOT to change:** don't import anything from `backend/core/request_context.py` into worker-
tier code (`backend/worker/`, `backend/services/`) — that module is API-tier-only specifically
because it depends on starlette, which `requirements-worker.txt` doesn't install; importing it
there would break the worker image's lean dependency set.

**Dependencies affected:** none — stdlib `logging` only, by design (see `CLAUDE.md`'s
"Observability" section: "stdlib `logging` + JSON formatter, no new dependency").

**Tests to run:** none required for adding a log line; if you're changing `configure_logging()`'s
formatting itself, verify manually that both the API process's and a worker process's log output
still look correct (they share this one configuration function).

**Expected result:** new log lines appear in the process's stdout in the same JSON-structured
format as every existing log line.

**Common mistakes:** logging inside a hot per-chunk/per-segment loop at `INFO` level without
considering volume — a classroom session can generate hundreds of chunks; verbose per-chunk
logging at `INFO` would flood real logs. Use `DEBUG` for anything that fires per-chunk/per-segment
and reserve `INFO` for per-session or coarser events, matching the restraint already visible in
this project's existing log call sites.

---

## 26. Debug a backend failure

**Files to inspect first:** `docs/TROUBLESHOOTING.md` (this project already has a dedicated
troubleshooting doc — check it before re-diagnosing something already documented there). Then,
depending on symptom:
- **A request hangs or times out:** check whether the failure is in the API tier or worker tier —
  remember `backend/main.py` never runs ML code itself; a hang during actual transcription means
  the *worker* process (or eager-mode's inline execution) is stuck, not the API. `backend/worker/
  celery_app.py`'s `_load_models()` is where model-loading failures surface (each model's load is
  independently try/excepted with a `_logger.warning` — check worker startup logs for which
  model, if any, failed to load, since a missing model doesn't crash the worker, it just makes
  that toggle unusable).
- **A WS session behaves oddly:** re-read `backend/api/transcribe.py`'s `transcribe_stream()`
  state machine (entry 7) — the `enqueued`/`completed`/`ending` counters are the actual source of
  truth for whether a session should have finalized yet.
- **A 500 on a specific route:** check that route's file in `backend/api/` for what exceptions it
  actually catches vs. lets propagate — most routes convert known failure modes to a clean
  `HTTPException`; an uncaught exception becoming a raw 500 usually means a genuinely new/unhandled
  case, not existing behavior.

**Tools available:** `scripts/v2_smoke_test.py` and `scripts/ws_smoke_test.py` — full REST+WS
walkthroughs against a running server, this project's actual integration-test tool (both expect
`uvicorn backend.main:app` already running on port 8000, and both end in an explicit pass/fail).
`/health` (liveness only) and `/metrics` (Prometheus) endpoints, always mounted. Structured JSON
logs via `get_logger()` (entry 25) — check both the API process's and (if running non-eager) the
separate worker process's output; a failure inside a Celery task shows up in the *worker's* log,
not the API's.

**What NOT to do:** don't add a broad `try/except: pass` to make an error "go away" — every
existing exception-handling site in this codebase either converts to a specific `HTTPException`
with a real error `detail`, or lets a genuinely-unexpected error surface (converting a mystery 500
into a silent no-op just hides the same bug from tests too). Don't assume eager mode's behavior
generalizes to the real Celery-worker-process deployment — several real bugs in this project's
history (see `docs/GIT_HISTORY.md`'s "Round 9" entries) only manifested against a real separate
worker process and real Postgres/Redis, never in eager mode.

**Tests to run:** `pytest tests/ -v -k <relevant_test_file>` to narrow down, then the full suite.
If the bug is concurrency-related, specifically run `tests/test_session_service.py` against a real
Postgres (`DATABASE_URL` set) — it's skipped by default against SQLite.

**Expected result:** a reproducible failing test (write one if none exists) before attempting a
fix — this project's own convention throughout its history (see every "Resolved this pass" section
in `CLAUDE.md`) is fix-plus-regression-test, not fix-and-hope.

**Common mistakes:** debugging only against eager mode (the zero-infra default) when the actual
bug is a real-worker/real-Postgres/real-Redis concurrency or connection-lifecycle issue — these
categorically cannot reproduce in eager mode, since eager mode runs everything inline in one
process with one DB connection.

---

## 27. Debug a Flutter failure

**Files to inspect first:** `flutter analyze` output (static errors/warnings) before runtime
debugging — this project keeps analyze clean as a baseline, so a new warning is almost always
directly related to your change. `docs/TROUBLESHOOTING.md` for known issues.

**Tools available:** `flutter test` (unit/widget tests — fast, no device needed) vs. `flutter run`
against a real emulator/device (needed for anything involving the WS connection, mic, or
navigation timing — this project's own history shows real bugs, like the `session_ended`/
navigation race in `live_recording_screen.dart`, that no unit test caught, only a real on-device
run did). `flutter devices` to check what's available before `flutter run`.

**What to check for common symptom classes:**
- **A screen doesn't update after a server response:** check whether the relevant `ChangeNotifier`
  (`AuthController`, `SettingsController`) actually calls `notifyListeners()`, and whether the
  widget reads it via `context.watch<T>()` (rebuilds on change) vs. `context.read<T>()` (does not).
- **A field silently doesn't reach the server (or vice versa):** almost always a `toJson()`/
  `fromJson()` key-name mismatch against the backend's Pydantic schema — see entry 7's note on
  `docs/API_CONTRACT.md`'s documented real discrepancies; grep both sides for the exact JSON key
  string, don't assume the Dart field name and JSON key match (they often don't, by Dart naming
  convention — `chunkDurationSeconds` ↔ `'chunk_duration_seconds'`).
- **A crash after an async gap:** check for a missing `if (!mounted) return;` after an `await`
  before touching `context`/`setState` — this project's existing screens consistently guard this;
  a new async code path that doesn't is a likely crash source if the screen can be disposed mid-
  operation (e.g. a forced logout).

**What NOT to do:** don't "fix" a failing widget test by loosening its assertion instead of fixing
the underlying behavior — `android/test/home_screen_test.dart`'s Dismissible-crash test
specifically exists because a real crash was found and proven via a revert-and-confirm cycle
(reverting the fix made the test fail again); weakening a test like this erases exactly the safety
net this project's own history shows matters.

**Tests to run:** the specific test file for the area you're debugging, then the full
`flutter test` afterward to check for unrelated regressions. `flutter analyze` should stay clean
throughout — don't suppress an analyzer warning with `// ignore:` unless you understand exactly
why it's a false positive.

**Expected result:** a reproducible failing test before the fix (write one if none exists,
following this project's established pattern of pairing every real bug fix with a regression
test — see `CLAUDE.md`'s "Flutter Client (Built)" section for several concrete examples of this
exact workflow), passing after.

**Common mistakes:** debugging a WS/networking issue purely via `flutter test` — this project's
mock-free integration testing for anything involving a live server connection is a real on-device
run against a real running backend, not a widget test with a fake `ApiClient`. Assuming an
emulator run validates real-device behavior — the loopback-vs-LAN-IP distinction (entry 8) and the
silent-virtual-mic limitation (entry 15) are both real, documented gaps between emulator and
physical-device behavior in this specific project.

---

*This document does not enumerate every possible modification — it covers the 26 requested
categories with the exact files/functions this pass verified against the live repository. For
anything not covered here, the closest matching entry above plus `docs/ARCHITECTURE.md` (system
design), `docs/BACKEND.md`/`docs/FRONTEND.md` (module-by-module tours), and
`docs/CODEBASE_DEPENDENCY_MAP.md` (who-calls-what) should get you to the right files quickly.*
