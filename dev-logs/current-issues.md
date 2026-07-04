# Current Issues & Suggested Improvements

Snapshot of the codebase as of 2026-07-04. This is a working list for engineering follow-up, not a bug tracker — update or remove items as they're resolved.

---

## 🔴 Functional Bugs

### 1. `/voice/ask` ignores the uploaded audio entirely
`routes/voice.py` reads the uploaded audio (`await audio.read()`) but never uses the result. It always returns the hardcoded string `"Hi, I am ready."` converted to speech. There is no STT (speech-to-text) call and no connection to `ai_service.ask_nesh`.

Git history (`Emergency demo bypass for competition`, `Final stable demo bypass`) confirms this was a deliberate shortcut to guarantee a working demo, not a design decision. Earlier commits (`Fix voice STT using Gemini inline base64 audio`, `Voice endpoint using Gemini multimodal STT`) show a real STT integration existed before being ripped out. The physical ESP32 device is effectively non-functional as an AI assistant right now — it just plays a canned greeting.

**Fix**: restore/re-wire Gemini multimodal (or a dedicated STT) to transcribe `audio`, feed the transcript through the same RAG + `ask_nesh` pipeline used by `/chat/ask`, and speak back the real answer.

### 2. `year` filter in chat requests is dead code
`ChatRequest` in `routes/chat.py` accepts a `year` field, but `ask_question()` never passes it to `search_chunks_hybrid`, and `search_chunks_hybrid` in `services/rag_service.py` doesn't even accept a `year` parameter (only `search_chunks_semantic` does, unused here). Clients think they can filter chat answers by year; they can't.

**Fix**: either thread `year` through `search_chunks_hybrid` → `search_chunks_semantic`, or remove the field from the request model to stop the false affordance.

### 3. Temp WAV file from `/voice/ask` is never deleted
`transcode_audio()` in `routes/voice.py` creates `temp_wav_path`, and only the source MP3 (`temp_mp3.name`) is cleaned up with `os.unlink`. Every voice request leaks one `.wav` file into the container's temp directory. On a long-lived Railway instance this is a slow disk leak.

**Fix**: delete `temp_wav_path` after `FileResponse` has sent it (e.g. via a `BackgroundTask`), not before — `FileResponse` streams the file after the handler returns, so it can't be deleted synchronously in the handler body.

### 4. Semantic search filters *after* limiting results
`search_chunks_semantic()` fetches `limit` (e.g. 8) rows from the `match_paper_chunks` RPC, then filters by `syllabus`/`year` in Python afterward. If the true best matches for a given syllabus/year aren't in the initial top-N returned by the RPC, they're silently dropped — search can return fewer results than expected, or miss relevant chunks entirely.

**Fix**: push `syllabus`/`year` filtering into the RPC call itself (extend `match_paper_chunks` to accept these as SQL filter params) so filtering happens before the top-K cutoff.

### 5. Duplicate/confusing imports in `main.py`
Line 4 imports `papers, chat, search, voice` from `routes`, then line 12 re-imports `papers, chat, search` again (missing `voice`, redundant with line 4). Harmless today since Python caches modules, but confusing and a likely source of future bugs if someone edits one import line and not the other.

**Fix**: keep a single import block.

---

## 🟠 Security Gaps

### 6. No authentication or authorization on any endpoint
Every route — including `DELETE /papers/{paper_id}`, `DELETE /chat/history/{student_id}`, and `POST /papers/upload` — is open to anyone who can reach the API. `student_id` is a client-supplied string with no verification, so any caller can read or wipe any other student's chat history.

**Fix**: add an auth layer (API key, JWT via Supabase Auth, or at minimum a shared secret header) before this goes further into production use.

### 7. CORS config is both too permissive and internally inconsistent
`main.py` sets `allow_origins=["*"]` together with `allow_credentials=True`. Per the CORS spec, browsers reject credentialed requests against a wildcard origin — so this combination doesn't even work as intended, and simultaneously signals "anything goes" to anyone reading the config.

**Fix**: set explicit allowed origins (the Flutter app's domain(s)) once known, and drop `allow_credentials` if cookies/credentials aren't actually used.

### 8. No file size limits on PDF upload or audio upload
`/papers/upload` and `/voice/ask` accept files of unbounded size, with no validation before reading the full body into memory (`await file.read()`). A large upload can exhaust memory on the (likely small) Railway instance.

**Fix**: enforce a max content length (e.g. via a request size limit at the proxy/ASGI level, or checking `Content-Length` before reading).

### 9. Unauthenticated endpoints call paid external APIs
`/chat/ask` and `/search/` call Gemini and Voyage AI on every request with no rate limiting or auth. Combined with issue #6, this is an open door for API cost abuse.

**Fix**: add per-IP or per-student rate limiting (e.g. `slowapi`) at minimum.

---

## 🟡 Missing Infrastructure / Environment Docs

### 10. No `.env.example`
`SUPABASE_URL`, `SUPABASE_KEY`, `VOYAGE_API_KEY`, `GEMINI_API_KEY`, `TESSERACT_PATH` are all read via `os.getenv` with no documented defaults or example file. New contributors have to read all of `services/` to reconstruct the required environment.

**Fix**: add a `.env.example` with placeholder values (this is now partially covered in the new README).

### 11. `tesseract-ocr` is not installed anywhere in the deploy config
`services/pdf_service.py` falls back to `pytesseract` (which shells out to a system `tesseract` binary) when a PDF looks scanned. `Aptfile` and `nixpacks.toml` only install `ffmpeg`. Unless Railway's Nixpacks Python image bundles Tesseract by default (it doesn't, by default), OCR fallback will throw at runtime on any scanned PDF upload in production.

**Fix**: add `tesseract-ocr` to `Aptfile` (and/or `nixPkgs` in `nixpacks.toml`), and verify with a real scanned-PDF upload against the deployed instance.

### 12. No database schema / migrations in the repo
The tables `past_papers`, `paper_chunks`, `chat_history`, and the RPC function `match_paper_chunks` all live only in the Supabase project — there's no SQL migration file, no schema doc, nothing checked into version control. If the Supabase project is ever lost, recreated, or needs a second environment (staging), the schema has to be reverse-engineered from application code.

**Fix**: add a `supabase/migrations/` folder (or plain `.sql` file) capturing table definitions, indexes (especially the pgvector index on `paper_chunks.embedding`), and the `match_paper_chunks` function.

### 13. No tests
There is no test suite anywhere in the repo (no `tests/`, no `pytest` in `requirements.txt`). Given how much of the logic (chunking, reranking, hybrid search dedup) is pure and easily unit-testable, this is a straightforward gap to close incrementally.

### 14. No structured logging
Error handling relies on `print()` and `traceback.print_exc()` (only in `chat.py`). On Railway this ends up in the platform log stream with no structure, levels, or correlation IDs — hard to search once traffic grows.

**Fix**: adopt Python's `logging` module (or `structlog`) consistently across `routes/` and `services/`.

### 15. Leftover artifact in repo root
`verify_upload.wav` is sitting untracked in the project root (visible in `git status`). Looks like a manual test artifact from debugging the voice endpoint. Should be deleted or moved into a `.gitignore`d scratch folder so it doesn't get accidentally committed.

---

## 🐳 Dockerization

The project currently deploys via Railway's Nixpacks auto-detection (`nixpacks.toml` + `Aptfile`), with no `Dockerfile`. This works but has downsides worth fixing:

- **No reproducible local dev environment** — a contributor needs to manually install `ffmpeg` (and, per issue #11, `tesseract-ocr`) on their own machine to match production behavior.
- **Coupled to Railway's build system** — harder to run the exact same artifact on another host (Fly.io, a VPS, GCP Cloud Run, etc.) or in CI.
- **No pinned OS/base image** — Nixpacks picks a Python version/base image on your behalf; a Dockerfile pins it explicitly.

### Suggested `Dockerfile` sketch

```dockerfile
FROM python:3.11-slim

# System deps: ffmpeg (audio transcode) + tesseract-ocr (scanned PDF OCR)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Plus a `docker-compose.yml` for local dev that mounts `.env` and exposes port 8000, so `docker compose up` is a one-command local environment matching production.

Railway supports deploying directly from a `Dockerfile` if one is present, so this migration doesn't require leaving Railway — it just replaces Nixpacks' inference with an explicit, versioned build definition. `nixpacks.toml` and `Aptfile` could then be retired.

---

## Summary Priority Order

1. **Fix `/voice/ask`** (#1) — the core "AI voice assistant" feature is currently fake.
2. **Add authentication** (#6) before any wider rollout — right now anyone can delete any student's data.
3. **Add `tesseract-ocr` to the deploy config** (#11) — silent production failure waiting to happen on scanned PDFs.
4. **Dockerize** — improves reproducibility and unblocks easier multi-host / CI deployment.
5. Everything else (dead `year` field, temp file leak, schema docs, tests, logging) — incremental cleanup.
