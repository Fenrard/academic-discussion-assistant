# Paper vs. Implementation

A read of the manuscript (`THESIS_ Development and Evaluation of a
Noise-Aware Code-Switching Multilingual Speech Recognition and Automated
Summarization System for Hiligaynon Classroom Discourse (4).docx`)
Chapter 1 (Research Questions, Objectives, Conceptual Framework,
Theoretical Framework) and Chapter 3 (Methodology — Requirement
Analysis, Context Diagram, Level 1 DFD, Pseudocode, Software Stack,
Testing and Evaluation), checked line-by-line against the actual code
in this repo.

**Verdict up front: yes, directly relevant.** Every Research Question
and every Specific Objective maps onto something concretely built (see
§1). Three real discrepancies surfaced (§3) — none of them mean the
paper and the system have drifted apart; all three are the ordinary
kind of gap between a proposal-stage design and a finished
implementation. For each one, this file recommends keeping the code as
built and says exactly what to change in the manuscript text, per
Nathan's instruction to keep the current approach where it's already
good and document the difference rather than force the code to match
old pseudocode. One place the paper was actually right and the code
was missing something is called out in §3.3, and has already been
fixed here (not left as a to-do).

---

## 1. Research Questions / Objectives → what's built

| # | Research Question (Ch. 1) | Specific Objective (Ch. 1) | Built as |
|---|---|---|---|
| 1 | Process noisy multilingual classroom audio? | Capture/process audio in noisy real-world environments | `backend/services/audio_service.py` — FFmpeg normalize+loudnorm (always on) → FFmpeg `afftdn` denoise (toggle) → Silero VAD (toggle) |
| 2 | Identify and prioritize teacher speech? | Teacher voice recognition via speaker embeddings | `teacher_verification_service.py` (SpeechBrain ECAPA, cosine similarity) = identification; `keyword_service.build_weighted_text()` + `minutes_service.py`'s teacher-first ranking = prioritization |
| 3 | Transcribe Hiligaynon/Filipino/English code-switched speech? | Multilingual ASR + Hiligaynon fine-tuning + low-resource eval | Faster-Whisper `small` int8 multilingual; `ai/finetuning/` LoRA/PEFT scaffold (untrained, no corpus yet); `evaluation/wer.py` has a by-group breakdown hook for exactly this |
| 4 | Generate structured draft classroom minutes? | Key points, topics, definitions, tasks | `minutes_service.py` — all four, `definitions` via trilingual regex patterns |
| 5 | WER/CER/teacher-ID accuracy/latency? | Evaluate technical performance | `evaluation/wer.py`, `evaluation/teacher_id.py`, `evaluation/latency.py` — all built, all unrun against real data |
| 6 | Usability, perceived usefulness, comprehension support? | Evaluate usability | `evaluation/sus.py` — scoring math only, no respondents, no Flutter app to test yet |

No objective is unaddressed in the code. The gaps that remain (real
classroom corpus, a trained fine-tune, real evaluation numbers, the
Flutter app, real SUS respondents) are exactly the ones CLAUDE.md's
"Current Build Priority" section already lists as blocked on real-world
data/people, not on more backend code — this read of the manuscript
doesn't change that list, it confirms it.

## 2. Conceptual Framework (Fig. 1) → what's built

The manuscript's two-phase framework maps cleanly onto the actual
build/deploy split:

- **Phase 1 (Model Building and Development)** — inputs (classroom
  audio, teacher voice samples, reference transcripts, glossary,
  Hiligaynon adaptation dataset) → process (preprocessing, speech
  detection, teacher-ID, transcription, code-switch post-processing,
  minutes generation) → outputs (fine-tuned model, labeled segments,
  transcripts, technical evaluation results). This is `backend/` +
  `ai/finetuning/` + `evaluation/` — built and tested, minus the actual
  fine-tuning run and minus real evaluation numbers (both blocked on the
  corpus, per §1).
- **Phase 2 (Deployment and User Evaluation)** — teacher enrolls, mobile
  app streams audio, near-real-time subtitles during the session,
  transcript + teacher-prioritized transcript + minutes after. This is
  the WS streaming API (`WS /ws/transcribe`) plus the still-unbuilt
  Flutter client — the API side is done and tested via
  `scripts/ws_smoke_test.py`; the client side is Nathan's next piece,
  per CLAUDE.md.

No conflict here — the framework describes the system this repo builds
toward, not a different one.

## 3. Real discrepancies found

### 3.1 Context Diagram entities — conceptual vs. implementation diagram

**Paper (Fig. 2, Ch. 3):** three external entities — **Teacher**
(provides voice enrollment + instructional speech), **Student**
(receives subtitles/transcripts/minutes), **Researcher/System
Administrator** (provides config/glossary/testing params, receives
logs/results/exports).

**This repo's `docs/DFD.md`:** one generic **User** plus **Hugging Face
Hub** as a second external entity (the diarization model download).

This is not a bug — it's two diagrams answering two different
questions. The paper's diagram documents the *conceptual, user-facing*
system (who in the real world does what). `docs/DFD.md` documents the
*implementation* (what the actual code's auth boundary looks like
today), which is why it includes an infra dependency (Hugging Face)
the paper's conceptual diagram correctly leaves out — the paper isn't
wrong to omit it, and `docs/DFD.md` isn't wrong to include it; they're
diagramming different boundaries.

The more important finding underneath the two diagrams: **the actual
backend auth model has no role field.** There is one `users` table and
one JWT type — anyone who registers can enroll a teacher voice, start
sessions, and read/export minutes. There's no `role: teacher | student
| admin` distinction anywhere in `backend/models/user.py`.

**Is this a real gap? No — checked against the paper's own Requirement
Analysis, and it isn't.** Nothing in the manuscript's functional
requirements calls for the Student to have their own login or account.
Phase 2's own process description has the *teacher's* device do the
capturing and streaming; the Student's role in the data flow is purely
receiving — near-real-time subtitles, transcripts, minutes — which a
single-teacher-operated session can satisfy by displaying/sharing
those outputs to the room (projected subtitles, a shared transcript
link, an exported minutes file) without every student needing their
own account. That's a legitimate, common classroom deployment pattern,
not a shortcut around the requirement. Similarly, "Researcher/System
Administrator" in the paper's diagram (glossary edits, config,
`HF_TOKEN`, testing params) maps onto direct file/env access on the
same machine the backend runs on, or the same authenticated `User`
account acting in an admin capacity (pulling `/metrics`, running
`evaluation/` scripts) — not a distinct login tier.

**Recommendation: keep the single-role backend as-is.** It's simpler,
it's tested, and it doesn't contradict any actual functional
requirement in the manuscript. What changed here is documentation, not
code: `docs/DFD.md` now carries a note pointing at this section so a
reader doesn't mistake "one User" for a missed requirement, and this
file gives the entity mapping for whoever revises Chapter 3's narrative
text — the paper's diagram itself needs no change, since it was never
describing the backend's auth model to begin with. If a future version
of this project ever needs actual per-role access control (e.g. a
school deploying this for multiple teachers who shouldn't see each
other's sessions), `sessions.owner_id` already scopes every query by
account, so adding a `role` column and per-role permission checks on
top of that is additive, not a rearchitecture.

### 3.2 Pipeline order — teacher-ID before transcription (paper) vs. after (code)

**Paper says this three separate times, consistently:**
- Conceptual Framework, Phase 1: "...audio preprocessing, speech
  detection, **teacher voice identification**, multilingual
  transcription, code-switch post-processing..."
- Level 1 DFD narrative (Fig. 3): "Each speech chunk is then compared
  with the stored teacher voice profile... The speech chunks are then
  transcribed..."
- Integration Testing sequence (Ch. 3): "audio input -> preprocessing
  -> speech detection -> segmentation -> **teacher voice identification**
  -> transcription -> code-switch post-processing -> ..."

**Code does it the other way:** `run_pipeline()` in
`backend/services/audio_service.py` transcribes first (Faster-Whisper
on the VAD segments), then runs diarization + speaker-label merge, then
runs SpeechBrain teacher verification — scored per *Whisper segment*,
not per raw VAD chunk. See CLAUDE.md's "Pipeline Order (Locked)"
section for the exact, current order.

**This was a deliberate implementation choice, and it should stay.**
Three concrete reasons:

1. **Segment-boundary alignment.** Whisper's own segmentation doesn't
   line up 1:1 with Silero VAD's chunk boundaries — Whisper can merge,
   split, or shift boundaries relative to the VAD segments it was given.
   If teacher-ID ran on raw VAD chunks first (as the paper describes),
   the resulting `is_teacher` labels would need a second alignment step
   to map onto Whisper's own segments before they could be attached to
   the transcribed text — which is exactly what
   `keyword_service.build_weighted_text()` and `minutes_service.py`
   need (text + label on the same object). Running verification
   *after* transcription, directly on Whisper's segments, means the
   label lands on the exact object that carries the text — no
   alignment step, no boundary-mismatch bugs to chase.
2. **No efficiency case for doing it first.** The paper's own Objective
   4 / RQ 4 need a *full* transcript (teacher and student speech both)
   to generate structured minutes with real classroom context — nothing
   in the paper proposes skipping transcription of non-teacher speech.
   So running teacher-ID first buys no compute savings; it's purely an
   ordering choice with no downstream gating behavior either way.
3. **The independence-from-diarization property is preserved either
   way.** The paper explicitly frames teacher-ID as working "without
   requiring full multi-speaker diarization" — and the actual code
   honors that exactly: `enable_teacher_verification` and
   `enable_diarization` are independent toggles: teacher verification
   slices `whisper_segments` directly using each segment's own
   `start`/`end`, and never reads a diarization-assigned `speaker`
   label. Diarization stays optional and orthogonal, same as the paper
   intends.

**Recommendation: keep the code's order.** For the manuscript, revise
the Pseudocode (Scripts 3–4), the Level 1 DFD narrative, and the
Integration Testing sequence to read: preprocessing → speech
detection/segmentation → **transcription** → **teacher voice
identification (scored per transcribed segment)** → code-switch
post-processing → structured minutes generation. This is the normal,
expected kind of refinement between proposal-stage pseudocode and a
working system — the manuscript's own stated methodology (Hybrid
Iterative SDLC) explicitly allows for exactly this during
Implementation, so it doesn't need to be framed as a deviation, just an
update.

### 3.3 Noise suppression: `arnndn` (paper) → `pyrnnoise` → FFmpeg `afftdn` (code, current)

**Paper (Software Stack, Ch. 3):** "Audio preprocessing relies on
FFmpeg for format conversion and RNNoise for noise suppression, applied
through FFmpeg's `arnndn` filter."

**History:** the backend first used the `pyrnnoise` Python library with a
48kHz round-trip (RNNoise's model runs at 48kHz; the rest of the pipeline
is 16kHz) — a deliberate deviation from `arnndn`, chosen for portability
(a plain `pip install`, no external `.rnnn` model file to manage). That
choice broke: `pyrnnoise` 0.4.3 (the last release) is incompatible with
every `audiolab`/`PyAV` combination that still installs on Python 3.11
(the required PyAV downgrade is `ResolutionImpossible` against
`faster-whisper`). It also had zero test coverage, so the breakage sat
unnoticed until a full-pipeline stress test with `enable_denoise=True`.

**Current (PM decision):** `backend/services/audio_service.py: clean_audio()`
now applies **FFmpeg's `afftdn`** (FFT-based broadband denoiser),
in place at 16kHz — no resample round-trip, no Python dependency, one
subprocess call, `~0.1s` per chunk vs. the old round-trip's three FFmpeg
subprocesses. Filter string `afftdn=nr=12:nf=-25:tn=1` (`nf` raised from
the -50 default because classroom ambient sits above near-silence; `tn=1`
tracks non-stationary noise) — an unvalidated starting point, same caveat
as `teacher_verification_threshold`, to tune against real noisy classroom
recordings once they exist. Covered by `tests/test_audio_denoise.py`.

**Paper wording:** change the Software Stack paragraph to "noise
suppression via FFmpeg's `afftdn` (FFT denoise) filter" — this is closer
to the paper's original "applied through FFmpeg" framing than `pyrnnoise`
ever was, just a different FFmpeg filter than `arnndn`. Note it is not
RNNoise; if the RNNoise name must be kept, `arnndn` + a committed `.rnnn`
model file is the fallback (PM chose `afftdn` for zero-setup portability).

### 3.4 Teacher-ID accuracy metric — paper named it, code was missing it (fixed)

### 3.4 Teacher-ID accuracy metric — paper named it, code was missing it (fixed)

**Paper's Table 1** lists **Accuracy** as its own row for teacher voice
identification, separate from Precision/Recall/F1-score. RQ5/Objective
5 also say "teacher identification accuracy" by name.
`evaluation/teacher_id.py`'s `compute_teacher_id_metrics()` computed
precision/recall/F1/FAR/FRR but never accuracy.

Unlike §3.1–3.3, this isn't a case of "the code's approach is
defensible, update the paper" — the paper explicitly names a metric the
code just didn't compute, and accuracy is trivial to derive from the
confusion counts the function was already building. **Fixed directly in
this pass:** `compute_teacher_id_metrics()` now returns an `"accuracy"`
key (`(TP+TN)/total`) alongside the existing metrics, with matching
test coverage in `tests/test_teacher_id.py`. No manuscript change
needed here — the paper was right, the code now matches it.

## 4. ISO/IEC 25010 mapping (Theoretical Framework, Ch. 1)

The manuscript anchors its evaluation on ISO/IEC 25010. Concrete,
already-built evidence for each characteristic it names:

| Characteristic | What in this repo addresses it |
|---|---|
| Functional suitability | Every pipeline stage independently toggleable (`enable_denoise`/`enable_vad`/`enable_diarization`/`enable_teacher_verification`) — the system can be configured to exactly the functional scope a given evaluation run needs |
| Performance efficiency | Per-stage latency recorded on every pipeline call (`stage_latencies`), `evaluation/latency.py` computes RTF; `evaluation/resources.py` samples CPU/memory via `psutil` |
| Compatibility / Portability | SQLite-by-default / Postgres-when-configured, Celery eager-mode / real-broker — same code path either way; Windows dev environment + Linux-targeted Docker images |
| Usability | `evaluation/sus.py` (standard SUS scoring), pending the Flutter app + real respondents |
| Reliability | Every ML dependency (pyannote, SpeechBrain) is lazy-imported and degrades gracefully — a missing/failed optional model disables its own toggle rather than crashing the worker (see `backend/worker/celery_app.py: _load_models()`); denoise is a plain FFmpeg filter with no Python dependency to fail |
| Security | JWT auth on every route, `bcrypt` password hashing, rate limiting on login/transcribe/enroll, `consent_confirmed` required at session creation, full purge on `DELETE /sessions/{id}`, raw audio never persisted past processing |
| Maintainability | Service-per-concern under `backend/services/`, each independently unit-tested in `tests/` without needing model weights |

This is a genuinely strong fit — worth citing directly in a revised
Chapter 3 as evidence the architecture was built with this quality
model in mind, not retrofitted to justify it after the fact.

## 5. Recommendation summary

| Finding | Keep code / Revise paper text | Why |
|---|---|---|
| Thesis title | Paper is ground truth | README.md's title has now been corrected to match exactly |
| Context Diagram entities (Teacher/Student/Researcher-Admin vs. generic User) | Keep code (single-role auth); paper's diagram needs no change; add explanatory text | Paper's diagram is conceptual, not a literal auth spec; no functional requirement calls for per-role login |
| Pipeline order (teacher-ID before vs. after transcription) | Keep code; revise paper's Pseudocode/DFD narrative/Integration Testing text | Code's order avoids a segment-boundary alignment problem the paper's order would require; no efficiency loss since full transcription is needed either way |
| Noise suppression (`arnndn` → `pyrnnoise` → `afftdn`) | Code now uses FFmpeg `afftdn`; revise paper's Software Stack paragraph to name it | `pyrnnoise` broke irreparably against current deps; `afftdn` needs no package and no model file, and stays within the paper's "applied through FFmpeg" framing |
| Teacher-ID accuracy metric | Code was missing it — now added | Paper named it explicitly (Table 1); trivial, safe fix from data already computed |

## 6. What this doesn't change

Nothing above suggests the paper and the built system are pursuing
different projects — every Research Question and Objective in Chapter 1
is answered by something real in this repo (§1), the Conceptual
Framework's two phases map directly onto build/deploy (§2), and the
ISO/IEC 25010 framing fits what was actually built without forcing it
(§4). The four discrepancies are all at the level of Chapter 3's
implementation detail — pseudocode, a diagram's chosen abstraction
level, one library name, one missing metric — not at the level of what
the system is for or whether it does it. Three of the four are
recommended to stay as built; write the paper to match. The fourth
(accuracy) is already fixed in code to match the paper.
