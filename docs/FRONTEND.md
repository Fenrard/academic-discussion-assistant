# Frontend — Complete Flutter Reference

> Written 2026-09-15. Every file below was read directly this pass. Validated this pass on this
> machine: `flutter analyze` → "No issues found!"; `flutter test` → 69/69 passing.

## How Flutter starts

`android/lib/main.dart` → calls `runApp(ScaitaleApp(...))` (`android/lib/app.dart`), wiring up the
app's `Provider`s (`AuthController`, `SettingsController`, `ApiClient`) before anything else runs.
`ScaitaleApp` is a `MaterialApp` whose `home` is computed directly from
`AuthController.isAuthenticated`: `HomeScreen()` if true, `LoginScreen()` if false — rebuilt
automatically whenever `AuthController.notifyListeners()` fires (login, logout, or a forced logout
triggered by any `401` response anywhere in the app, via `ApiClient`'s global handler).

## Routing / navigation

No named-route table, no `go_router` or similar package — plain imperative
`Navigator.of(context).push(MaterialPageRoute(builder: (_) => SomeScreen(...)))` throughout. The
top-level auth gate (in `app.dart`) is the only place navigation is driven by app-wide state rather
than a direct user action.

## Screens (`android/lib/screens/`)

- **`auth/login_screen.dart`, `auth/register_screen.dart`** — plain email/password forms, call
  `ApiClient.login()`/`register()`.
- **`home/home_screen.dart`** — landing screen post-auth. Loads the session list
  (`GET /sessions`), a FAB pushes `LiveRecordingScreen` (guarded against a double-tap with an
  `_isOpeningRecorder` flag), app-bar icons open `TeacherEnrollmentScreen` and `SettingsScreen`.
  Swipe-to-delete via `SessionListTile`'s `Dismissible` — `_delete()` removes the item from local
  state **unconditionally** (before the server call resolves), a deliberate fix for a real crash
  (see `docs/DEVELOPMENT.md`).
- **`recording/live_recording_screen.dart`** — the WS-driven recording screen. See
  `docs/ARCHITECTURE.md` Workflow B/C for the full trace. Only Start/Stop controls exist — no
  pause/resume. Shows elapsed time, a static recording indicator, and the live-growing transcript
  as one plain scrolling text block (no per-segment speaker/timestamp/teacher differentiation in
  this view — that richer view is on `TranscriptScreen`, reached only after the session ends).
- **`transcript/transcript_screen.dart`** — post-session view: full per-segment transcript with
  timestamp, speaker chip, and a distinct "Teacher" chip (school icon) when `is_teacher` is true,
  plus a client-side search box with live match-count and yellow highlight
  (`_highlightedText()` — deliberately falls back to un-highlighted text if lowercasing would
  change a string's length, to avoid a `RangeError` on the handful of Unicode edge cases where
  that happens; near-impossible for Hiligaynon/Filipino/English text but handled anyway).
- **`minutes/minutes_screen.dart`** — structured minutes view: header (duration, participants,
  teacher-speech %), Keywords chips, Topics (expandable, key points nested), Definitions, Action
  items, and an export menu (Markdown/plain text via the OS share sheet).
- **`enrollment/teacher_enrollment_screen.dart`** — records a ~10–15s sample via the `record`
  package (WAV, not streamed PCM — this path uses `AudioRecorder.start(path: ...)` rather than
  `startStream()`), uploads it, polls for `pending → ready|failed`. Lists all enrolled teachers
  with delete.
- **`settings/settings_screen.dart`** — server address field, preset selector
  (`PipelinePresetSelector`), and `AdvancedSettingsPanel` (outcome-framed toggles: "Reduce
  background noise," "Skip silent gaps," "Separate speakers" [+ optional speaker-count field],
  "Prioritize teacher's voice," plus "Accuracy vs. speed" and "Live update frequency" sliders).
  **Does not** include font size, theme, or export-format settings — those don't exist anywhere in
  the app despite appearing in some early conceptual-framework drafts.

## Core (`android/lib/core/`) — the plumbing every screen depends on

- **`api_client.dart`** — one method per backend REST endpoint. `_handle()` (2xx → `jsonDecode()`,
  non-2xx → throws `ApiException`, any `401` → calls `AuthController.forceLogout()` globally) vs.
  `_ensureOk()` (status-check only, no JSON decode — used specifically for the minutes-export
  endpoint, which returns plain text, not JSON; an earlier version routed export through `_handle()`
  and threw on every successful export — see `docs/DEVELOPMENT.md`).
- **`ws_transcribe_client.dart`** — `WsTranscribeClient`: `connect()`, `sendStart()`, `sendChunk()`,
  `sendEnd()`, a broadcast `Stream<WsServerMessage>` of parsed incoming messages. Deliberately does
  **not** attempt to reconnect on an unexpected drop (no "resume session X" protocol exists
  server-side, so a reconnect UX would be fake) — `onDisconnected` callback lets the screen surface
  it instead.
- **`auth_controller.dart`** — `AuthController extends ChangeNotifier`: holds the current JWT (via
  `secure_storage.dart`), `login()`, `logout()`, `forceLogout()` (the global-401 path).
- **`settings_controller.dart`** — server base URL + `PipelineOptions`, persisted via
  `shared_preferences`. `applyPreset()` sets all fields from `PipelinePresets.{fast,balanced,
  accurate}`; `updateOptions()` (any manual field edit) resets the selected preset to "Custom".
- **`secure_storage.dart`** — thin wrapper around `flutter_secure_storage`, JWT only.
- **`pcm_chunker.dart`** + **`local_vad.dart`** — see `docs/ARCHITECTURE.md` Workflow C. Fully
  covered by `pcm_chunker_test.dart` and `local_vad_test.dart`.
- **`wav_encoder.dart`** — `wrapPcm16AsWav()`: builds a 44-byte RIFF/WAVE/fmt/data header around a
  raw PCM16LE buffer. Covered by `wav_encoder_test.dart` (header-correctness assertions).
- **`polling.dart`** — `pollUntil<T>({fetch, isDone, timeout})`: generic exponential-backoff
  polling helper, used identically for whole-file-transcription status and teacher-enrollment
  status.

## Models (`android/lib/models/`)

Plain Dart classes with `fromJson()`/`toJson()`, one file per backend schema family:
`pipeline_config.dart` (`Preset` enum → `PipelineOptions`, field names matching `backend/schemas/
pipeline.py` exactly — see `docs/ARCHITECTURE.md` §Contracts), `session_models.dart`,
`teacher_models.dart`, `minutes_models.dart`, `auth_models.dart`, `ws_messages.dart` (the
`WsServerMessage` sealed-class-style hierarchy with a `fromJson()` factory switching on the
server's `"type"` field).

## Widgets (`android/lib/widgets/`)

Small, reusable, screen-agnostic: `error_banner.dart`, `loading_view.dart`,
`session_list_tile.dart` (the `Dismissible` swipe-to-delete row), `status_badge.dart`
(pending/ready/failed pill), `pipeline_preset_selector.dart`, `advanced_settings_panel.dart`.

## State management

No dedicated state-management package (no `bloc`, `riverpod`, `get`) — `provider` only, and even
that's used sparingly: three app-wide `ChangeNotifier`s (`AuthController`, `SettingsController`,
plus `ApiClient` itself exposed via `Provider` for DI convenience) injected at the root, read via
`context.read<T>()`/`context.watch<T>()`. Every screen's own transient state (loading flags, form
values, the live transcript string) is plain `StatefulWidget`/`setState()` — no cross-screen shared
mutable state beyond those three providers.

## Networking

`http` package for REST (`api_client.dart`), `web_socket_channel` for the streaming path
(`ws_transcribe_client.dart`). Base URL is user-editable in Settings (`SettingsController.baseUrl`,
persisted). No retry/backoff on REST calls beyond what `polling.dart` provides for the two
async-task-polling flows specifically — a one-off REST call that fails simply throws
`ApiException`, caught and surfaced as a snackbar/error banner by the calling screen.

## Recording / permissions / audio handling

The `record` package (`^7.1.1`) for microphone capture, in two different modes depending on screen:
`startStream()` (headerless PCM16, live-recording screen — see above) vs. `start(path: ...)`
(WAV file written to disk, teacher-enrollment screen). `permission_handler` (pinned via a
`dependency_overrides` entry to `13.0.1` — see `docs/TROUBLESHOOTING.md`) requests
`RECORD_AUDIO`/`INTERNET`/`MODIFY_AUDIO_SETTINGS` (declared in `AndroidManifest.xml`).
Mic-permission-denied is handled explicitly on both recording screens (a snackbar, not a crash).

## Error states / loading states

Consistent pattern across every screen that loads data: a `bool _isLoading`, a `String? _error`,
and a dedicated `LoadingView`/`ErrorBanner` widget pair — no screen silently shows a blank page on
either a slow load or a failed one.

## Result display

Live: `LiveRecordingScreen`'s growing plain-text transcript. Post-session: `TranscriptScreen`
(searchable, per-segment, speaker/teacher-labeled) and `MinutesScreen` (structured summary).

## File export / download

Minutes only (Markdown or plain text), via the OS share sheet — see `docs/ARCHITECTURE.md`
Workflow J for the precise mechanism and its one caveat (shared as text, not as a literal file with
the server-specified extension). **No transcript export exists.** **No local file save/download
exists** — everything routes through the OS share sheet; there's no "Save to device" option
anywhere in the app.

## Local storage

`flutter_secure_storage` (JWT only) and `shared_preferences` (server URL + pipeline settings). No
local database, no offline cache of sessions/transcripts — every screen re-fetches from the server
on load.

## Authentication (client side)

JWT stored via `secure_storage.dart`, attached as `Authorization: Bearer <token>` on every REST
call (`api_client.dart`) and as a `?token=` query parameter on the WebSocket URL. A `401` from any
call triggers `AuthController.forceLogout()`, which clears the stored token and (via the app-wide
auth gate in `app.dart`) immediately swaps the visible screen back to `LoginScreen`, from wherever
the user currently is in the app.

## Tests (`android/test/`, 69 passing — confirmed this pass)

Pure-Dart unit tests needing no device: `pipeline_config_test.dart` (preset values + exact
`toJson()` key names — the single highest-risk typo surface, since a mismatched key silently
reverts to a server-side default rather than erroring), `wav_encoder_test.dart`,
`pcm_chunker_test.dart`, `local_vad_test.dart`, model `fromJson()` parsing tests
(`session_models_test.dart`, `teacher_models_test.dart`, `minutes_models_test.dart`,
`ws_messages_test.dart`), `polling_test.dart`, `api_client_test.dart`, plus two widget tests:
`app_auth_gate_test.dart` (confirms the app-wide auth gate actually swaps screens on login/
forceLogout — an empirically-verified claim, not assumed from reading Flutter's source) and
`home_screen_test.dart` (drives an actual swipe-to-delete gesture, including a failed-delete case —
this one caught a real crash; see `docs/DEVELOPMENT.md`).

**Not tested by anything in `android/test/`, and not testable there:** anything requiring a real
device/emulator (actual microphone capture, actual WebSocket round-trip against a real backend,
actual Android permission dialogs) — that category of testing is manual/on-device only, and the
project's own history (`CLAUDE.md` Part 2) documents specific on-device runs, not automated ones,
for that coverage.
