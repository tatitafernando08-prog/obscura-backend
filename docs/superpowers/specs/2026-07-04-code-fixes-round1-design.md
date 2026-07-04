# Round 1: Code-Level Bug Fixes & Config Hygiene — Design

Status: Approved (Section 1 auto-proceeded after no user response within timeout; Sections 2-3 unopposed)
Date: 2026-07-04
Source: `dev-logs/current-issues.md`

## Scope

This round covers the subset of `dev-logs/current-issues.md` that is safely fixable
without a new auth system, without rewriting the voice AI pipeline, and without
Dockerizing. Deferred to later rounds: authentication, `/voice/ask` real STT/AI
wiring, Dockerization, rate limiting, structured logging, tests.

Included:
1. Application code bug fixes (issues #2, #3, #4, #5, #7, #8 in current-issues.md)
2. Config/deploy hygiene (issue #10, #15)
3. Supabase-side SQL deliverables, provided as files for manual execution since
   this session has no DB credentials (issues #4, #12)

## Section 1 — Application Code Bug Fixes

**main.py**
- Remove the duplicate import block (`papers, chat, search, voice` imported once;
  the second `from routes import papers, chat, search` is redundant and missing
  `voice`).
- Change `allow_credentials=True` → `False`. Rationale: no cookies/auth headers
  are used by this API today, and `allow_origins=["*"]` + `allow_credentials=True`
  is a combination browsers reject anyway. Keeping wildcard origins since the
  frontend's final domain isn't locked in yet (per user).

**routes/chat.py**
- `ChatRequest.year` (already present) gets threaded into the
  `search_chunks_hybrid(...)` call.

**services/rag_service.py**
- `search_chunks_hybrid` gains a `year: int = None` parameter, passed through to
  `search_chunks_semantic`.
- `search_chunks_semantic` passes `year` into the RPC call as `filter_year`
  instead of (only) filtering client-side after retrieval — this depends on the
  updated SQL function in Section 3. Client-side syllabus/year filtering is
  removed once the RPC does it, to fix the "filters after top-K cutoff" bug
  (issue #4).

**routes/voice.py**
- Fix the temp-WAV leak: `FileResponse` streams the file *after* the handler
  returns, so the file can't be deleted synchronously inside the handler. Use
  `FileResponse(..., background=BackgroundTask(os.unlink, temp_wav_path))` so
  cleanup happens once the response has been sent.

**routes/papers.py & routes/voice.py**
- Add upload size guards:
  - PDFs: reject if `Content-Length` header indicates >20MB, or if the actually
    read body exceeds 20MB (header can be absent/spoofed, so both checks apply).
  - Voice audio: same pattern, 5MB cap (6 seconds of 16-bit 16kHz mono raw audio
    is ~192KB, so 5MB is a generous ceiling for compressed/uncompressed clips).
  - Both return `HTTPException(413, "File too large")`.

## Section 2 — Config / Deploy Hygiene

- Add `.env.example` at repo root documenting the 5 environment variables
  already listed in `README.md`, with placeholder values and one-line comments.
- Delete `verify_upload.wav` (untracked leftover debugging artifact from the
  voice endpoint work).
- Add `*.wav` to `.gitignore` to stop future stray audio artifacts from
  appearing in `git status`.

## Section 3 — Supabase SQL Deliverables (manual apply)

Two new files under `dev-logs/sql/`, **not executed by me** — the user runs
these in the Supabase SQL editor.

**`update_match_paper_chunks.sql`**
- Redefines `match_paper_chunks(query_embedding, filter_stream, filter_subject,
  match_count)` to additionally accept `filter_syllabus text default null` and
  `filter_year int default null`, applying them as `WHERE` clauses (joined
  against `past_papers`) *before* the vector similarity `ORDER BY ... LIMIT`,
  fixing the "filter after top-K" bug at its root.
- Includes a comment noting this replaces the existing function (uses
  `CREATE OR REPLACE FUNCTION`) and that the old 4-arg call signature from
  application code must be updated in lockstep with `rag_service.py`
  (already covered in Section 1).

**`schema_reference.sql`**
- `CREATE TABLE IF NOT EXISTS` statements for `past_papers`, `paper_chunks`,
  `chat_history`, reconstructed from how the application code reads/writes
  these tables (column names and inferred types only — no access to the live
  DB to confirm exact types, defaults, or constraints).
- Clearly commented as a **disaster-recovery reference**, not a migration to
  run against the existing (already-populated) database — running `CREATE
  TABLE IF NOT EXISTS` against live tables is a no-op if they already exist, so
  it's safe, but column types should be manually diffed against the real schema
  before relying on this file to recreate the DB elsewhere.

## Testing / Verification

No automated test suite exists yet (tracked separately in current-issues.md
issue #13, out of scope here). Verification for this round:
- `python -c "import main"` — confirms no import errors after the main.py cleanup.
- Manual review of the BackgroundTask usage against FastAPI's documented pattern.
- The two `.sql` files are inert until the user runs them; no live verification
  possible from this session.

## Out of Scope (explicitly deferred)

- Authentication/authorization (issue #6)
- `/voice/ask` real STT → RAG → TTS wiring (issue #1)
- Dockerization (Dockerization section)
- Rate limiting (issue #9)
- Structured logging (issue #14)
- Automated tests (issue #13)
