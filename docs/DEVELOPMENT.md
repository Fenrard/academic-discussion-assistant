# Development Guide — Known Bugs, Safe Modification, Testing

> Written 2026-09-15. The "known bugs/fragile areas" list below is built from a direct grep for
> `TODO`/`FIXME`/`HACK`/`XXX` across every `.py`/`.dart`/`.yaml`/`.yml`/`.kts` file (two results,
> both listed) plus this project's own documented fix history (`CLAUDE.md` Part 2), not guessed.

## Known bugs / fragile areas, ranked

### CRITICAL
*(Nothing currently rated CRITICAL — both test suites pass clean on this machine as of this pass,
and no data-loss or security-open-door issue was found this pass.)*

### HIGH
- **Android release APKs are signed with the auto-generated debug keystore.**
  `android/android/app/build.gradle.kts` line 34: `// TODO: Add your own signing config for the
  release build` — `signingConfig = signingConfigs.getByName("debug")`. Fine for installing on your
  own devices or handing an APK to a thesis panel; **Google Play would reject it**, and it is not a
  real release credential. Generating a proper upload keystore is a `keytool`-based step whenever
  real distribution matters.
- **All Flutter↔backend traffic is plaintext HTTP/WS.** `AndroidManifest.xml` sets
  `usesCleartextTraffic="true"` because the backend has no TLS certificate (it's a LAN-address dev
  machine, not a reachable hostname). Anyone else on the same Wi-Fi could sniff login credentials,
  the JWT, or raw audio chunks. Deliberate and acceptable for a trusted classroom Wi-Fi prototype;
  a real gap the moment this backend serves anything less trusted or moves off the local network.
- **The teacher-verification threshold (`0.35`) and the `afftdn` denoise parameters
  (`nr=12:nf=-25:tn=1`) are both unvalidated heuristic defaults**, not calibrated against any real
  classroom audio — every measurement this project has ever produced for teacher-ID accuracy or
  noise-suppression quality is synthetic/proxy data, not real. Treat any accuracy claim resting on
  these defaults as provisional until `evaluation/teacher_id.py`/real listening tests are run
  against real data.

### MEDIUM
- **`materialize_transcript()`/`append_chunk_result()` redo O(n) work on every single chunk
  arrival** (a full copy + full re-walk from index 0), making total work and total DB bytes written
  O(n²) across a session. Fine at the chunk counts this project has tested; a real concern for a
  full lecture-length session (hundreds to ~1200 chunks/hour).
- **Teacher verification calls SpeechBrain once per Whisper segment with no batching** — 40–60+
  sequential CPU forward passes for a typical discussion. Real overhead a busier deployment would
  feel; not incorrect, just slow.
- **`evaluation/wer.py`'s edit-distance allocates a full O(n·m) matrix** even for character-level
  CER on a whole-session transcript, and its "overall" error-rate figure re-runs the full
  computation on the concatenated corpus rather than aggregating already-computed per-pair results.
  Evaluation-script-only — never on a production request path.
- **Docker images (`Dockerfile.api`/`Dockerfile.worker`/`docker-compose.yml`) have never actually
  been built or run** in any environment this project has existed in — written to spec, validated
  only indirectly via CI's own (different) Postgres/Redis service containers.
- **`POST /transcribe`'s whole-file path assumes the API and worker processes share a filesystem**
  (it passes a file path through the Celery message, not the audio bytes themselves, unlike the WS
  chunk path which does embed bytes). Fine on one machine; breaks across genuinely separate
  API/worker hosts without a shared volume — the documented, deliberate fix would be object storage
  (S3-compatible), not yet built.

### LOW
- **`scripts/tester`** — a 6-line scratch file (`import sounddevice as sd; print(sd.query_devices());
  y=2+1; print(f"{y}")`), tracked in git since the very first backend commit, with no purpose beyond
  a one-off mic-device check. Harmless; safe to delete if it's ever confusing.
- **`integration/` and `experiments/` directories are completely empty** (confirmed this pass — not
  even a `.gitkeep`, not tracked by git at all) and have no code reference anywhere in the
  repository. Likely leftover scaffolding from early planning.
- **Duplicated `write_report()` logic across all five `evaluation/*.py` scripts** — copy-pasted
  near-identically rather than shared. Cosmetic; never refactored, lower priority than anything
  above.
- **Hardcoded default backend URLs in `android/lib/core/settings_controller.dart`**
  (`http://10.0.2.2:8000` for Android, `http://127.0.0.1:8000` otherwise) — by design (a sensible
  emulator-friendly default), always user-editable in the Settings screen, not a bug, but worth
  knowing if you're searching for "why does the app default to this address."
- **`LICENSE` at the repo root is an empty directory, not a file** — a direct, known, deliberately
  unresolved gap. What license to apply is the project owner's decision alone; do not invent
  license content on their behalf.

## What I must not change (casually)

See `docs/ARCHITECTURE.md` §Contracts for the full table with "what breaks" detail. Summary: the
WebSocket message `type` vocabulary, `PipelineOptions`' exact snake_case field names, the
`SUPPORTED_EXTENSIONS` list (duplicated in two files, must stay in sync), the `/api/v1` route
prefix, every environment variable name in `backend/core/config.py`, the `session:{id}:results`
pub/sub channel naming convention, and any change to `backend/models/*.py` that isn't paired with a
new Alembic migration.

## Safe Modification Guide

| Task | File(s) | Function/Class | What to change | What NOT to change | Test afterward |
|---|---|---|---|---|---|
| Change the Flutter UI (a screen's look) | `android/lib/screens/<screen>/*.dart`, `android/lib/widgets/*.dart` | The specific screen's `build()` method | Widget tree, styling, layout | Don't touch the `_load()`/`_handle*()` logic methods unless the data flow itself needs to change | `flutter analyze && flutter test`; manually exercise the screen |
| Change the recording chunk duration default | `android/lib/models/pipeline_config.dart` (`PipelinePresets`), `backend/core/config.py` (`min_chunk_duration_seconds`/`max_chunk_duration_seconds` bounds) | `PipelinePresets.balanced` etc. | The default value within the existing 1–10s bound | Don't change the bound itself without checking `backend/schemas/pipeline.py`'s `Field(ge=..., le=...)` stays consistent | `pytest tests/test_transcribe_api.py`; a real recording session |
| Change the ASR model | `backend/core/config.py` (`whisper_model_size` default), or set `WHISPER_MODEL_SIZE` env var at runtime | `Settings.whisper_model_size` | The model name/path | Don't hardcode a new value inside `load_whisper_model()` itself — the env-var indirection is there specifically so this doesn't need a code change | `pytest tests/`, then a real transcription call — model behavior differences won't show up in unit tests |
| Change the teacher voice threshold | `backend/core/config.py` (`teacher_verification_threshold`), or `TEACHER_VERIFICATION_THRESHOLD` env var | `Settings.teacher_verification_threshold` | The float value | Don't change `verify_segment()`'s comparison logic (`>=`) without understanding it affects every existing enrolled teacher's behavior retroactively | `pytest tests/test_teacher_id.py`; a real enrollment + verification round-trip |
| Add another language | `backend/services/glossary_service.py` + `backend/data/glossary.json` (glossary terms), `backend/services/keyword_service.py` (`_STOPWORDS`), `backend/services/minutes_service.py` (`_ACTION_TRIGGERS`, `_DEFINITION_PATTERNS`) | — | Add trigger phrases/stopwords/glossary entries for the new language | **Do not** touch `transcribe_audio()`'s language-detection call itself — Whisper's own multilingual support already covers most languages; this project's own explicit scope lock (`CLAUDE.md`'s "Language Scope (CRITICAL)") restricts the *product* to Hiligaynon/Filipino/English specifically — check with the project owner before actually widening scope, this isn't purely a technical decision | `pytest tests/test_glossary_service.py`, `tests/test_minutes_service.py` |
| Change summarization/minutes behavior | `backend/services/minutes_service.py` | `_group_into_topics()`, `_key_points()`, `_find_definitions()`, `_find_action_items()`, `generate_minutes()` | Any of the regex patterns or ranking logic | Don't change the `generate_minutes()` return dict's top-level keys without updating `backend/api/minutes.py: _render_minutes()` and `android/lib/models/minutes_models.dart` to match | `pytest tests/test_minutes_service.py`, `tests/test_minutes_api.py` |
| Change the backend URL (client default) | `android/lib/core/settings_controller.dart` | The `baseUrl` getter's default logic | The default string(s) | This is also just user-editable at runtime in Settings — usually no code change is actually needed | Manual: open Settings, confirm the field shows the expected default |
| Change the exported minutes format | `backend/api/minutes.py` | `_render_minutes()` | The formatting logic | Don't change the `format` query-parameter's accepted values (`"markdown"`/`"txt"`) without updating `android/lib/screens/minutes/minutes_screen.dart`'s export menu to match | `pytest tests/test_minutes_api.py`; a real export + share round-trip |
| Add another API endpoint | `backend/api/<relevant file>.py` | New `@router.get/post/...` function | Add the route, add its Pydantic schema in `backend/schemas/`, register the router in `backend/main.py` if it's a new file | Don't forget `Depends(get_current_user)` unless the route is deliberately public (like `/health`) | Add a `tests/test_<name>.py`; hit it via `/docs`'s interactive UI |
| Change denoise/VAD/diarization parameters | `backend/services/audio_service.py` (`DENOISE_FILTER`), `backend/services/diarization_service.py` | The filter string / model call | — | These are all explicitly `unvalidated heuristic` per their own code comments — changing them changes real behavior with no real-data feedback loop to confirm the change was actually an improvement | `pytest tests/test_audio_denoise.py`; ideally a real before/after listening comparison |

## Testing

### Existing automated tests (verified passing this pass, on this machine)

- **Backend:** `pytest tests/ -v` → **90 passed, 1 skipped** (the skip is a Postgres-only
  concurrency test — a no-op against SQLite, runs for real whenever `DATABASE_URL` points at
  Postgres, including in CI). 16 test files, one per major service/route module.
- **Flutter:** `flutter analyze` → "No issues found!"; `flutter test` → **69 passed**. 12 test
  files covering every piece of pure-Dart logic plus two widget tests (the app-wide auth gate, and
  a real swipe-to-delete crash regression).

### Manual smoke-test checklist (only functionality that actually exists)

```
[ ] Backend starts (`uvicorn backend.main:app --reload`, no errors, /health returns {"status":"ok"})
[ ] Flutter launches (`flutter run`, app opens to the Login screen on first run)
[ ] Register + log in (JWT persists across app restart — confirmed by killing/relaunching the app)
[ ] Home screen loads (empty session list on a fresh account)
[ ] Teacher voice enrollment: record a ~10-15s sample, submit, status moves pending -> ready
[ ] Microphone permission prompt appears and is handled (allow, and separately, deny)
[ ] New recording session: consent checkbox required before Start is enabled
[ ] WebSocket connects (session_started message received -> screen moves to the recording view)
[ ] Audio reaches the backend (chunk_result messages arrive; on a REAL device with real speech,
    _liveTranscript grows with actual words -- on an emulator, expect near-silence, this is
    correct behavior, not a bug, since the emulator's virtual mic is silent)
[ ] ASR produces a transcript (non-empty transcript_segments on the Transcript screen, real device only)
[ ] Teacher is identified (a segment shows the "Teacher" chip, when enable_teacher_verification
    is on and the speaker matches an enrolled voice)
[ ] Diarization labels speakers (Speaker A/B/... chips, when enable_diarization is on and HF_TOKEN
    is configured -- NOT exercised in this pass's validation, no HF_TOKEN was set)
[ ] Transcript search works (typing in the search box highlights matches)
[ ] Minutes are generated (Topics/Definitions/Action items sections populate after a session with
    real detected speech)
[ ] Export works (share menu on the Minutes screen produces the OS share sheet with readable text)
[ ] Session delete works (swipe to delete on Home, session disappears, survives a failed-delete
    retry without crashing the list -- this exact scenario has its own dedicated widget test)
[ ] Settings changes persist (change a toggle/slider, background and reopen the app, value is retained)
[ ] Logout returns to the Login screen from anywhere in the app
```

**Missing functionality — do not expect these to work, they don't exist:**
```
[ ] (N/A) Transcript export as its own document -- only minutes export exists
[ ] (N/A) Pause/resume during recording -- only Start/Stop exist
[ ] (N/A) Import an existing audio file from the Flutter UI -- backend route exists, no client UI
[ ] (N/A) Offline recording with later sync -- not built, documented as explicitly out of scope
[ ] (N/A) Font size / theme settings -- don't exist anywhere in the app
[ ] (N/A) Per-role login (teacher vs. student vs. admin) -- single undifferentiated User role
```
