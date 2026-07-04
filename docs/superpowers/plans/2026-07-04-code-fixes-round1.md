# Round 1 Code Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the safely-scoped subset of `dev-logs/current-issues.md` — application code bugs, config hygiene, and Supabase SQL deliverables — without touching auth, the voice AI pipeline, or Dockerization (deferred to later rounds).

**Architecture:** Small, independent edits to existing FastAPI route/service files, plus two new standalone `.sql` files under `dev-logs/sql/` that the user runs manually in Supabase (this session has no DB credentials). No new files or abstractions beyond what's needed.

**Tech Stack:** FastAPI, Supabase (Postgres + pgvector), Voyage AI, Google Gemini — all pre-existing. No new dependencies introduced.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-04-code-fixes-round1-design.md` — follow it exactly.
- Out of scope this round: authentication, `/voice/ask` real STT/AI wiring, Dockerization, rate limiting, structured logging, automated test suite (tracked separately in `current-issues.md`).
- No pytest suite exists and none is being added this round. Verification uses small ad hoc scripts (created, run, then deleted — never committed) plus manual checks, per the spec's Testing/Verification section.
- CORS: `allow_origins=["*"]` stays as-is; `allow_credentials` must become `False`.
- Upload size caps: PDFs 20MB (`routes/papers.py`), voice audio 5MB (`routes/voice.py`), both returning HTTP 413.
- The two SQL files in `dev-logs/sql/` are deliverables only — nothing in this plan executes them against a live database.
- Commit after every task with a focused message; never bundle unrelated tasks into one commit.

---

### Task 1: Clean up `main.py` (imports + CORS)

**Files:**
- Modify: `main.py`

**Interfaces:** None (no other task depends on this one).

- [ ] **Step 1: Edit the file**

Replace the top of `main.py` (through the CORS middleware block) with:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

# Load .env file first thing
load_dotenv()

# Import route modules
from routes import papers, chat, search, voice

# ── Create FastAPI app ────────────────────────────────────────────────────────
app = FastAPI(
    title="Obscura Backend",
    description="AI-powered study assistant backend for Sri Lankan students",
    version="1.0.0"
)

# ── CORS Middleware ───────────────────────────────────────────────────────────
# Wildcard origins since the frontend's final domain isn't locked in yet.
# allow_credentials must stay False: browsers reject allow_origins=["*"]
# combined with allow_credentials=True, and this API doesn't use
# cookies/credentialed requests anyway.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Leave everything from `# ── Register Routes ──` onward unchanged.

- [ ] **Step 2: Verify it imports cleanly**

Run (Git Bash):
```bash
SUPABASE_URL=http://localhost SUPABASE_KEY=test VOYAGE_API_KEY=test GEMINI_API_KEY=test python -c "import main; print('ok')"
```
Expected: `ok` printed, no traceback.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "Clean up duplicate imports and fix CORS credentials mismatch"
```

---

### Task 2: Config hygiene — `.env.example`, `.gitignore`, remove leftover WAV

**Files:**
- Create: `.env.example`
- Modify: `.gitignore`
- Delete: `verify_upload.wav`

**Interfaces:** None.

- [ ] **Step 1: Create `.env.example`**

```
# Supabase project URL and API key (service role — this backend inserts/deletes freely)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-service-role-key

# Voyage AI embeddings (voyage-2 model)
VOYAGE_API_KEY=your-voyage-api-key

# Google Gemini (gemini-2.5-flash)
GEMINI_API_KEY=your-gemini-api-key

# Optional: path to a local Tesseract binary, used for OCR fallback on scanned PDFs in dev
TESSERACT_PATH=
```

- [ ] **Step 2: Add `*.wav` to `.gitignore`**

Current `.gitignore`:
```
.env
venv/
__pycache__/
*.pyc
*.pyo
.DS_Store
```

Append a line so it reads:
```
.env
venv/
__pycache__/
*.pyc
*.pyo
.DS_Store
*.wav
```

- [ ] **Step 3: Delete the leftover test artifact**

```bash
rm /d/Github/obscura-backend/verify_upload.wav
```

- [ ] **Step 4: Verify**

```bash
ls /d/Github/obscura-backend/.env.example
git status
```
Expected: `.env.example` exists; `verify_upload.wav` no longer appears in `git status` output (it was untracked, so its removal needs no `git rm`).

- [ ] **Step 5: Commit**

```bash
git add .env.example .gitignore
git commit -m "Add .env.example, gitignore *.wav, remove leftover test artifact"
```

---

### Task 3: Write Supabase SQL deliverables

**Files:**
- Create: `dev-logs/sql/update_match_paper_chunks.sql`
- Create: `dev-logs/sql/schema_reference.sql`

**Interfaces:**
- Produces: the RPC contract `match_paper_chunks(query_embedding, filter_stream, filter_subject, filter_syllabus, filter_year, match_count)` that Task 4 must call with matching parameter names.

- [ ] **Step 1: Create `dev-logs/sql/update_match_paper_chunks.sql`**

```sql
-- Updates match_paper_chunks to filter by syllabus and year INSIDE the SQL
-- query, before the similarity ORDER BY / LIMIT — fixes the bug where the
-- Python layer filtered syllabus/year *after* the top-K cutoff, silently
-- dropping relevant results that weren't in the initial top-K.
--
-- IMPORTANT: this assumes the existing function's column list and types
-- based on how routes/chat.py, routes/search.py and services/rag_service.py
-- consume its results (id, paper_id, content, chunk_index, similarity, and a
-- nested `past_papers` jsonb object with title/subject/year/stream/syllabus/
-- file_url). Verify this against your actual function definition in the
-- Supabase dashboard (Database > Functions > match_paper_chunks) before
-- running, and adjust column names/types if they differ.
--
-- CREATE OR REPLACE FUNCTION can add new trailing parameters with defaults
-- safely. If Postgres rejects this as a signature conflict, drop the old
-- function first:
--   drop function if exists match_paper_chunks(vector, text, text, int);

create or replace function match_paper_chunks(
  query_embedding vector(1024),
  filter_stream text default null,
  filter_subject text default null,
  filter_syllabus text default null,
  filter_year int default null,
  match_count int default 5
)
returns table (
  id uuid,
  paper_id uuid,
  content text,
  chunk_index int,
  similarity float,
  past_papers jsonb
)
language sql stable
as $$
  select
    pc.id,
    pc.paper_id,
    pc.content,
    pc.chunk_index,
    1 - (pc.embedding <=> query_embedding) as similarity,
    jsonb_build_object(
      'title',    pp.title,
      'subject',  pp.subject,
      'year',     pp.year,
      'stream',   pp.stream,
      'syllabus', pp.syllabus,
      'file_url', pp.file_url
    ) as past_papers
  from paper_chunks pc
  join past_papers pp on pp.id = pc.paper_id
  where (filter_stream   is null or pp.stream   = filter_stream)
    and (filter_subject  is null or pp.subject  = filter_subject)
    and (filter_syllabus is null or pp.syllabus = filter_syllabus)
    and (filter_year     is null or pp.year     = filter_year)
  order by pc.embedding <=> query_embedding
  limit match_count;
$$;
```

- [ ] **Step 2: Create `dev-logs/sql/schema_reference.sql`**

```sql
-- Disaster-recovery reference schema for the Obscura backend's Supabase
-- tables, reconstructed from how the application code reads/writes them
-- (routes/papers.py, routes/chat.py, services/rag_service.py). Column types
-- and constraints are best-effort inferences, NOT a verified export of the
-- live schema. Diff this against the real Supabase schema before relying on
-- it to recreate the database elsewhere.
--
-- Safe to run as-is against the existing database: CREATE TABLE IF NOT
-- EXISTS is a no-op on tables that already exist. This is NOT a migration
-- to apply routinely — it's a reference snapshot.

create extension if not exists vector;

create table if not exists past_papers (
  id          uuid primary key default gen_random_uuid(),
  title       text not null,
  subject     text not null,
  stream      text not null,
  syllabus    text not null,
  medium      text not null,
  year        int not null,
  file_url    text not null,
  page_count  int,
  created_at  timestamptz not null default now()
);

create table if not exists paper_chunks (
  id           uuid primary key default gen_random_uuid(),
  paper_id     uuid not null references past_papers(id) on delete cascade,
  content      text not null,
  chunk_index  int not null,
  embedding    vector(1024),
  created_at   timestamptz not null default now()
);

create index if not exists paper_chunks_embedding_idx
  on paper_chunks using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

create table if not exists chat_history (
  id          uuid primary key default gen_random_uuid(),
  student_id  text not null,
  question    text not null,
  answer      text not null,
  sources     jsonb,
  created_at  timestamptz not null default now()
);

create index if not exists chat_history_student_id_idx
  on chat_history (student_id);
```

- [ ] **Step 3: Review for placeholders**

Read both files back and confirm neither contains `TBD`/`TODO` — only the intentional disclaimer comments explaining these are best-effort references requiring manual verification against the live DB.

- [ ] **Step 4: Commit**

```bash
git add dev-logs/sql/update_match_paper_chunks.sql dev-logs/sql/schema_reference.sql
git commit -m "Add SQL deliverables: updated match_paper_chunks RPC and schema reference"
```

---

### Task 4: Thread `year` through `services/rag_service.py`

**Files:**
- Modify: `services/rag_service.py`

**Interfaces:**
- Consumes: the RPC contract from Task 3 — `match_paper_chunks` now accepts `filter_syllabus` and `filter_year`.
- Produces: `search_chunks_semantic(query, stream, subject="", syllabus="", year=None, limit=8)` (unchanged signature, changed internals) and `search_chunks_hybrid(query, stream, subject="", syllabus="", year=None, limit=5)` (new `year` parameter) — Task 5 calls `search_chunks_hybrid` with this exact signature.

- [ ] **Step 1: Replace `search_chunks_semantic`**

Replace the whole function (currently lines ~41-88) with:

```python
def search_chunks_semantic(
    query:    str,
    stream:   str,
    subject:  str = "",
    syllabus: str = "",
    year:     int = None,
    limit:    int = 8
) -> list[dict]:
    """
    Semantic vector search with metadata filtering.
    Finds conceptually similar content even if exact words don't match.
    Returns more results (8) so re-ranking can pick the best.
    """
    try:
        query_embedding = get_embedding(query)

        result = supabase.rpc(
            'match_paper_chunks',
            {
                'query_embedding': query_embedding,
                'filter_stream':   stream   if stream   else None,
                'filter_subject':  subject  if subject  else None,
                'filter_syllabus': syllabus if syllabus else None,
                'filter_year':     year,
                'match_count':     limit,
            }
        ).execute()

        return result.data if result.data else []

    except Exception as e:
        print(f"Semantic search error: {e}")
        return search_chunks_keyword(query, stream, subject, limit)
```

This removes the old post-retrieval Python filtering for `syllabus`/`year` — the SQL function now does it before the `LIMIT`, which is the actual bug fix (issue #4 in `current-issues.md`).

- [ ] **Step 2: Update `search_chunks_hybrid`**

Replace the function signature and its call to `search_chunks_semantic` (currently around lines ~125-144):

```python
def search_chunks_hybrid(
    query:    str,
    stream:   str,
    subject:  str = "",
    syllabus: str = "",
    year:     int = None,
    limit:    int = 5
) -> list[dict]:
    """
    Hybrid search — combines semantic + keyword search results.
    Deduplicates and re-ranks for best results.
    This gives much better results than either method alone.
    """
    # Get results from both methods
    semantic_results = search_chunks_semantic(
        query, stream, subject, syllabus, year, limit=8
    )
    keyword_results = search_chunks_keyword(
        query, stream, subject, limit=5
    )
```

Leave the rest of the function (dedup/rerank logic) unchanged.

- [ ] **Step 3: Write and run a verification script (not committed)**

Create `D:\Github\obscura-backend\_verify_task4.py`:

```python
import os
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_KEY", "test")
os.environ.setdefault("VOYAGE_API_KEY", "test")

import services.rag_service as rag

captured = {}

class FakeResult:
    data = []

def fake_rpc(name, payload):
    captured["name"] = name
    captured["payload"] = payload
    class R:
        def execute(self):
            return FakeResult()
    return R()

rag.supabase.rpc = fake_rpc
rag.get_embedding = lambda q: [0.0]

rag.search_chunks_semantic(
    "test query", "Science", subject="Physics", syllabus="Local", year=2022, limit=5
)

assert captured["payload"]["filter_syllabus"] == "Local", captured["payload"]
assert captured["payload"]["filter_year"] == 2022, captured["payload"]
print("OK: filter_syllabus and filter_year reach the RPC payload")
```

Run:
```bash
cd /d/Github/obscura-backend && python _verify_task4.py
```
Expected: `OK: filter_syllabus and filter_year reach the RPC payload` with no assertion errors.

- [ ] **Step 4: Delete the verification script**

```bash
rm /d/Github/obscura-backend/_verify_task4.py
```

- [ ] **Step 5: Commit**

```bash
git add services/rag_service.py
git commit -m "Push syllabus/year filtering into the match_paper_chunks RPC call"
```

---

### Task 5: Thread `year` through `routes/chat.py`

**Files:**
- Modify: `routes/chat.py`

**Interfaces:**
- Consumes: `search_chunks_hybrid(query, stream, subject="", syllabus="", year=None, limit=5)` from Task 4.

- [ ] **Step 1: Update the `search_chunks_hybrid` call**

In `ask_question()`, replace:

```python
        chunks = search_chunks_hybrid(
            query=    request.question,
            stream=   request.stream,
            subject=  request.subject,
            syllabus= request.syllabus,
            limit=    5
        )
```

with:

```python
        chunks = search_chunks_hybrid(
            query=    request.question,
            stream=   request.stream,
            subject=  request.subject,
            syllabus= request.syllabus,
            year=     request.year,
            limit=    5
        )
```

- [ ] **Step 2: Write and run a verification script (not committed)**

Create `D:\Github\obscura-backend\_verify_task5.py`:

```python
import os
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_KEY", "test")
os.environ.setdefault("VOYAGE_API_KEY", "test")
os.environ.setdefault("GEMINI_API_KEY", "test")

import asyncio
import routes.chat as chat_module

captured = {}

def fake_hybrid(query, stream, subject, syllabus, year, limit):
    captured["year"] = year
    return []

def fake_ask_nesh(**kwargs):
    return "test answer"

class FakeTable:
    def insert(self, data):
        return self
    def execute(self):
        return None

class FakeSupabase:
    def table(self, name):
        return FakeTable()

chat_module.search_chunks_hybrid = fake_hybrid
chat_module.ask_nesh = fake_ask_nesh
chat_module.supabase = FakeSupabase()

req = chat_module.ChatRequest(
    question="test?",
    stream="Science",
    subject="Physics",
    student_id="abc",
    year=2023,
)

asyncio.run(chat_module.ask_question(req))

assert captured["year"] == 2023, captured
print("OK: ChatRequest.year reaches search_chunks_hybrid")
```

Run:
```bash
cd /d/Github/obscura-backend && python _verify_task5.py
```
Expected: `OK: ChatRequest.year reaches search_chunks_hybrid` with no assertion errors.

- [ ] **Step 3: Delete the verification script**

```bash
rm /d/Github/obscura-backend/_verify_task5.py
```

- [ ] **Step 4: Commit**

```bash
git add routes/chat.py
git commit -m "Thread ChatRequest.year through to hybrid search"
```

---

### Task 6: Fix temp-WAV leak and add audio size limit in `routes/voice.py`

**Files:**
- Modify: `routes/voice.py`

**Interfaces:** None (leaf change).

- [ ] **Step 1: Replace the file contents**

```python
import subprocess
import os
import tempfile
from fastapi import APIRouter, File, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from gtts import gTTS

router = APIRouter()

MAX_AUDIO_BYTES = 5 * 1024 * 1024  # 5MB


def transcode_audio(input_mp3_path):
    """
    Uses system-level ffmpeg to transcode MP3 to raw PCM (16kHz, 16-bit, mono)
    to match ESP32 I2S register expectations.
    """
    output_wav = input_mp3_path.replace(".mp3", ".wav")

    # -f s16le: Signed 16-bit little-endian
    # -ar 16000: 16kHz
    # -ac 1: Mono
    command = [
        "ffmpeg", "-y", "-i", input_mp3_path,
        "-f", "s16le", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1", output_wav
    ]

    # Run ffmpeg as a system command
    subprocess.run(command, check=True, capture_output=True)
    return output_wav


@router.post("/ask")
async def voice_ask(request: Request, audio: UploadFile = File(...)):
    try:
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Audio file too large (max 5MB)")

        audio_bytes = await audio.read()

        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Audio file too large (max 5MB)")

        answer = "Hi, I am ready."

        # 1. Generate MP3
        tts = gTTS(text=answer, lang="en", slow=False)
        temp_mp3 = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tts.save(temp_mp3.name)
        temp_mp3.close()

        # 2. Transcode to Raw PCM
        temp_wav_path = transcode_audio(temp_mp3.name)

        # 3. Cleanup the intermediate MP3 now. The WAV is deleted only after
        # FileResponse finishes streaming it, via the background task below —
        # deleting it here would race the response trying to read it.
        os.unlink(temp_mp3.name)

        return FileResponse(
            temp_wav_path,
            media_type="audio/wav",
            background=BackgroundTask(os.unlink, temp_wav_path)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 2: Write and run a verification script (not committed)**

Create `D:\Github\obscura-backend\_verify_task6.py`:

```python
import os
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_KEY", "test")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from routes.voice import router

app = FastAPI()
app.include_router(router, prefix="/voice")
client = TestClient(app)

oversized = b"0" * (6 * 1024 * 1024)  # 6MB > 5MB cap
response = client.post(
    "/voice/ask",
    files={"audio": ("big.wav", oversized, "audio/wav")},
)

assert response.status_code == 413, response.status_code
print("OK: oversized audio rejected with 413")
```

Run:
```bash
cd /d/Github/obscura-backend && python _verify_task6.py
```
Expected: `OK: oversized audio rejected with 413` with no assertion errors.

- [ ] **Step 3: Delete the verification script**

```bash
rm /d/Github/obscura-backend/_verify_task6.py
```

- [ ] **Step 4: Commit**

```bash
git add routes/voice.py
git commit -m "Fix temp WAV file leak and add 5MB audio size limit in /voice/ask"
```

---

### Task 7: Add PDF upload size limit in `routes/papers.py`

**Files:**
- Modify: `routes/papers.py`

**Interfaces:** None (leaf change).

- [ ] **Step 1: Update imports and add the size constant**

Replace:
```python
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
```
with:
```python
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
```

Add directly below the `router = APIRouter()` line:
```python
MAX_PDF_BYTES = 20 * 1024 * 1024  # 20MB
```

- [ ] **Step 2: Add `request: Request` and the size checks to `upload_paper`**

Replace:
```python
@router.post("/upload")
async def upload_paper(
    file: UploadFile = File(...),
    title: str = Form(...),
    subject: str = Form(...),
    stream: str = Form(...),
    syllabus: str = Form(...),
    medium: str = Form(...),
    year: int = Form(...),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files accepted")

    try:
        pdf_bytes = await file.read()

        if len(pdf_bytes) == 0:
            raise HTTPException(status_code=400, detail="File is empty")
```

with:
```python
@router.post("/upload")
async def upload_paper(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    subject: str = Form(...),
    stream: str = Form(...),
    syllabus: str = Form(...),
    medium: str = Form(...),
    year: int = Form(...),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files accepted")

    content_length = request.headers.get("content-length")
    if content_length is not None and int(content_length) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 20MB)")

    try:
        pdf_bytes = await file.read()

        if len(pdf_bytes) == 0:
            raise HTTPException(status_code=400, detail="File is empty")

        if len(pdf_bytes) > MAX_PDF_BYTES:
            raise HTTPException(status_code=413, detail="File too large (max 20MB)")
```

Leave the rest of the function body (Supabase upload, chunking, embedding) unchanged.

- [ ] **Step 3: Write and run a verification script (not committed)**

Create `D:\Github\obscura-backend\_verify_task7.py`:

```python
import os
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_KEY", "test")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from routes.papers import router

app = FastAPI()
app.include_router(router, prefix="/papers")
client = TestClient(app)

oversized = b"0" * (21 * 1024 * 1024)  # 21MB > 20MB cap
response = client.post(
    "/papers/upload",
    files={"file": ("big.pdf", oversized, "application/pdf")},
    data={
        "title": "Test",
        "subject": "Physics",
        "stream": "Science",
        "syllabus": "Local",
        "medium": "english",
        "year": "2022",
    },
)

assert response.status_code == 413, response.status_code
print("OK: oversized PDF rejected with 413")
```

Run:
```bash
cd /d/Github/obscura-backend && python _verify_task7.py
```
Expected: `OK: oversized PDF rejected with 413` with no assertion errors.

- [ ] **Step 4: Delete the verification script**

```bash
rm /d/Github/obscura-backend/_verify_task7.py
```

- [ ] **Step 5: Commit**

```bash
git add routes/papers.py
git commit -m "Add 20MB upload size limit to /papers/upload"
```

---

## Self-Review Notes

- **Spec coverage:** Section 1 (main.py, chat.py, rag_service.py, voice.py, size limits) → Tasks 1, 4, 5, 6, 7. Section 2 (.env.example, leftover wav, gitignore) → Task 2. Section 3 (SQL deliverables) → Task 3. All spec items have a task.
- **Placeholder scan:** no `TBD`/`TODO`/vague instructions — every step has literal code or a literal command with expected output.
- **Type/signature consistency:** `search_chunks_hybrid(query, stream, subject="", syllabus="", year=None, limit=5)` defined in Task 4 matches the call in Task 5 exactly (positional/keyword names line up). `match_paper_chunks` RPC parameter names in Task 3 (`filter_syllabus`, `filter_year`) match the payload keys used in Task 4.
