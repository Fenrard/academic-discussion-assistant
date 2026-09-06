# Future Ideas

Deferred features and enhancements — not in scope, not scheduled. Ideas go
here, not into CLAUDE.md's scope sections.

## Flutter: "Import audio file" flow

`POST /transcribe` (backend/api/transcribe.py) is a fully built, tested
whole-file transcription endpoint — multipart upload, 202 + poll — but it
isn't wired into the Flutter client. It was deliberately descoped from the
initial client build (see `docs/paper-vs-implementation.md` and the client's
own build plan) because it isn't one of CLAUDE.md's six required screens and
would need a new `file_picker` dependency neither screen currently pulls in.

A natural home for it: a secondary action on the Home screen (e.g. next to
the "New session" FAB) that opens a file picker, uploads the selected
recording, and polls `GET /sessions/{id}` the same way the Teacher
Enrollment screen already polls `GET /teachers/{id}` — `core/polling.dart`'s
`pollUntil()` helper is already generic enough to reuse as-is.

## Per-role access (Teacher / Student / Researcher-Administrator)

The thesis manuscript's Context Diagram (Fig. 2) names three external
entities; the backend's actual auth model has one undifferentiated `User`
role. `docs/paper-vs-implementation.md` argues this is fine for the
prototype's actual functional requirements (no requirement anywhere calls
for separate student logins), but if a real multi-teacher deployment ever
needs per-role permissions, `sessions.owner_id`/`teacher_enrollments.owner_id`
already scope every query by account — adding a `role` column and
per-role checks on top of that would be additive, not a rearchitecture.
