# Getting the Backend Running — Manual Setup Steps

This is a step-by-step checklist for getting `obscura-backend` running from a
fresh clone, including the Supabase-side setup that isn't captured anywhere
in code. Follow these in order.

---

## 1. Prerequisites

- **Python 3.11** recommended. (Note: Python 3.14 currently fails to install
  `pymupdf==1.24.0` from `requirements.txt` because no prebuilt wheel exists
  for it and building from source requires Visual Studio Build Tools on
  Windows. Use 3.11 or 3.12 to avoid this.)
- **ffmpeg** installed and on your `PATH` (used by `/voice/ask` to transcode
  audio). Check with `ffmpeg -version`.
- **Tesseract OCR** installed and on your `PATH` (used as a fallback when a
  PDF upload looks like a scanned document with no extractable text). Check
  with `tesseract --version`. This is **not yet part of the deploy config**
  (see `dev-logs/current-issues.md` issue #11) — install it locally if you
  need to test scanned-PDF uploads.
- A **Supabase project** you have admin access to (for the SQL setup in step 3).
- API keys for **Voyage AI** and **Google Gemini** (see step 2).

---

## 2. Install dependencies and configure environment

```bash
git clone <this-repo>
cd obscura-backend
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and fill in the real values:

| Variable | Where to get it |
|---|---|
| `SUPABASE_URL` | Supabase project → Settings → API → Project URL |
| `SUPABASE_KEY` | Supabase project → Settings → API → `service_role` key (not the `anon` key — this backend inserts/deletes freely) |
| `VOYAGE_API_KEY` | [voyageai.com](https://www.voyageai.com/) → API keys |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) → Get API key |
| `TESSERACT_PATH` | Optional. Only set this if `tesseract` isn't on your `PATH` and you need to point at the binary directly (e.g. `C:\Program Files\Tesseract-OCR\tesseract.exe` on Windows) |

---

## 3. Set up the Supabase database (one-time, per environment)

Nothing in this repo creates your Supabase tables automatically — this has
to be done manually in the Supabase SQL editor.

### 3a. If this is a brand-new Supabase project (no tables yet)

Run `dev-logs/sql/schema_reference.sql` in the Supabase SQL editor. It creates:
- `past_papers`, `paper_chunks`, `chat_history` tables
- the `vector` extension and an `ivfflat` index on `paper_chunks.embedding`

Read the disclaimer comment at the top of that file first — it's a
best-effort reconstruction from how the application code uses these tables,
not a verified export of a real schema. Check column types match what you
actually want before relying on it.

### 3b. Create the `match_paper_chunks` RPC function

Run `dev-logs/sql/update_match_paper_chunks.sql` in the Supabase SQL editor.
This creates (or replaces, if it already exists) the `match_paper_chunks`
function that `services/rag_service.py` calls for semantic search — including
the `filter_syllabus`/`filter_year` parameters added in the round-1 fixes. If
you already have an older 4-parameter version of this function and
`CREATE OR REPLACE` errors out on a signature conflict, drop it first:

```sql
drop function if exists match_paper_chunks(vector, text, text, int);
```

then re-run `update_match_paper_chunks.sql`.

### 3c. Create the storage bucket

In Supabase → Storage, create a bucket named **`past-papers`** with public
read access (uploaded PDFs are served via public URLs from
`routes/papers.py`).

---

## 4. Run the backend locally

```bash
uvicorn main:app --reload
```

Visit `http://localhost:8000/health` — you should get `{"status": "healthy"}`.

Swagger UI (interactive API docs) is at `http://localhost:8000/docs`.

---

## 5. Sanity-check the main flows

1. **Upload a past paper** — `POST /papers/upload` with a PDF file and the
   required form fields (`title`, `subject`, `stream`, `syllabus`, `medium`,
   `year`). Confirm it returns a `paper_id` and `chunks_created > 0`.
2. **Ask a question** — `POST /chat/ask` with a `question`, `stream`,
   `subject`, and a `student_id`. Confirm you get an `answer` back citing the
   paper you just uploaded (if the topic matches).
3. **Voice endpoint** — `POST /voice/ask` with any small audio file attached
   as `audio`. You should get a `.wav` file back. Note: as of this round, the
   response is a hardcoded greeting, not a real answer to what was said —
   see `dev-logs/current-issues.md` issue #1, this is tracked, unresolved
   work.

If step 1 or 2 fails with a Supabase error, double check step 3 was done
correctly (tables/RPC/bucket all exist) and that `SUPABASE_KEY` in `.env` is
the `service_role` key, not `anon`.

---

## 6. Deploying (Railway)

The project deploys via Railway's Nixpacks build (`nixpacks.toml` +
`Aptfile`), which currently only installs `ffmpeg` as a system package. If
you need OCR fallback to work in production, add `tesseract-ocr` to
`Aptfile` — it is not there yet (tracked in `dev-logs/current-issues.md`
issue #11). Set the same environment variables from step 2 in Railway's
project settings (Variables tab) — `.env` is gitignored and never deployed.

---

## Known gaps after following this guide

Even with everything above done, some things are intentionally still broken
or missing — see `dev-logs/current-issues.md` for the full list, including:
- No authentication on any endpoint
- `/voice/ask` doesn't actually understand what's said (hardcoded response)
- No Dockerfile (Nixpacks/Railway only)
- No automated tests
