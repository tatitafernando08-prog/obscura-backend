# Obscura Backend

AI-powered study assistant backend for **Obscura**, a study platform aimed primarily at Sri Lankan O/L and A/L students (also supports Edexcel and Cambridge syllabuses). It provides:

- **RAG-based Q&A over past exam papers** (semantic + keyword hybrid search)
- **NESH**, a Gemini-powered AI tutor chat with conversation memory
- **Past paper management** (PDF upload, text extraction/OCR, chunking, embedding)
- **Voice interface** for an ESP32-based "NESH AI Voice Robot" IoT device

Deployed on Railway using Nixpacks.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API framework | FastAPI + Uvicorn |
| Database / Storage | Supabase (Postgres + pgvector + file storage) |
| Embeddings | Voyage AI (`voyage-2`) |
| LLM | Google Gemini (`gemini-2.5-flash`) |
| PDF text extraction | PyMuPDF (`fitz`) |
| OCR fallback | Tesseract (`pytesseract`) |
| Text-to-speech | gTTS |
| Audio transcoding | ffmpeg (system binary, via subprocess) |
| Hosting | Railway (Nixpacks build) |
| IoT client | ESP32 (Arduino/C++, `obscura_nesh_IOT.ino`) |

---

## Project Structure

```
obscura-backend/
├── main.py                  # FastAPI app entrypoint, CORS, route registration
├── routes/
│   ├── papers.py            # Past paper upload/list/get/delete
│   ├── chat.py               # NESH AI chat + history
│   ├── search.py              # Standalone RAG search endpoint
│   └── voice.py               # ESP32 voice endpoint (STT/TTS)
├── services/
│   ├── pdf_service.py         # PDF text extraction, OCR fallback, chunking
│   ├── rag_service.py          # Embeddings, semantic/keyword/hybrid search, reranking
│   └── ai_service.py           # Gemini prompt/response logic (NESH persona)
├── obscura_nesh_IOT.ino        # ESP32 firmware for the physical voice assistant device
├── requirements.txt
├── nixpacks.toml               # Railway build config (installs ffmpeg)
├── Aptfile                     # Apt package list for build (ffmpeg)
└── dev-logs/                   # Engineering notes, known issues, roadmap
```

---

## How It Works

### 1. Past Paper Ingestion (`/papers/upload`)
1. Client uploads a PDF with metadata (`title`, `subject`, `stream`, `syllabus`, `medium`, `year`).
2. File is stored in Supabase Storage (bucket `past-papers`), and a row is created in the `past_papers` table.
3. Text is extracted with PyMuPDF; if fewer than 100 characters come back (i.e. a scanned PDF), it falls back to Tesseract OCR page-by-page.
4. Extracted text is split into overlapping ~400-word chunks (80-word overlap) via `chunk_text`.
5. Each chunk is embedded with Voyage AI (`voyage-2`, `input_type="document"`) and stored in the `paper_chunks` table (in batches of 20).

### 2. RAG Search (`/search`, and internally by `/chat/ask`)
- **Semantic search**: embeds the query and calls a Supabase RPC function `match_paper_chunks` (pgvector similarity search), with optional post-filtering by `syllabus`/`year`.
- **Keyword search**: fallback using Postgres `ilike` on the first meaningful query word.
- **Hybrid search** (`search_chunks_hybrid`, used by chat): runs both, deduplicates by chunk id, and reranks combined results.
- **Reranking**: manual scoring — vector similarity (50%) + keyword overlap (30%) + source bonus (10%, semantic > keyword) + recency bonus (10%, newer papers score higher).
- **Context building**: top chunks are assembled into a citation-friendly context string (`build_context`), capped at `max_chars`.

### 3. NESH AI Chat (`/chat/ask`)
1. Runs hybrid search to retrieve relevant past-paper chunks for the student's `stream`/`subject`/`syllabus`.
2. Builds a RAG context (max 4000 chars).
3. Sends the question + context + last 6 turns of `chat_history` + student profile (stream/subject/medium) to Gemini, using a detailed NESH system prompt (persona: friendly Sri Lankan senior-student tutor, multilingual — replies in English/Sinhala/Tamil matching the student's input language).
4. Saves the Q&A (plus up to 3 source titles) to the `chat_history` table.
5. Returns the answer and the top 3 source chunks.

Chat history can also be fetched (`GET /chat/history/{student_id}`) or cleared (`DELETE /chat/history/{student_id}`).

### 4. Voice IoT (`/voice/ask`)
Designed for the ESP32 "NESH AI Voice Robot": the device records ~6 seconds of audio via an INMP441 I2S microphone, POSTs it to `/voice/ask`, and expects a raw PCM WAV response to play through a MAX98357 I2S amplifier.

Current server-side flow:
1. Receives the uploaded audio file.
2. Generates a fixed response ("Hi, I am ready.") via gTTS → MP3.
3. Transcodes the MP3 to 16kHz mono 16-bit PCM WAV using `ffmpeg` (to match the ESP32 I2S expectations).
4. Returns the WAV file.

> ⚠️ See `dev-logs/current-issues.md` — the uploaded audio is currently **not transcribed or sent to the AI**; this endpoint is a hardcoded demo response left over from a competition deadline.

### 5. Additional AI Service Utilities (in `services/ai_service.py`, not yet wired to routes)
- `generate_flashcards(topic, subject, stream, count)` — Gemini-generated Q/A flashcards.
- `summarize_topic(content, subject, stream)` — structured exam revision summary.
- `generate_study_plan(subjects, exam_date, hours_per_day)` — week-by-week study plan.
- `analyze_past_paper_question(question, subject, marks)` — examiner-style breakdown of a past paper question.

---

## API Endpoints

### Health
| Method | Path | Description |
|---|---|---|
| GET | `/` | Root health/status check |
| GET | `/health` | Simple health check (`{"status": "healthy"}`) |

### Past Papers — `/papers`
| Method | Path | Body/Params | Description |
|---|---|---|---|
| POST | `/papers/upload` | multipart form: `file` (PDF), `title`, `subject`, `stream`, `syllabus`, `medium`, `year` | Upload a past paper PDF, extract text, chunk, embed, and store |
| GET | `/papers/list` | query: `stream?`, `subject?`, `syllabus?`, `year?` | List papers with optional filters (sorted by year desc) |
| GET | `/papers/{paper_id}` | — | Get a single paper's metadata |
| DELETE | `/papers/{paper_id}` | — | Delete a paper record |

### Chat — `/chat`
| Method | Path | Body/Params | Description |
|---|---|---|---|
| POST | `/chat/ask` | JSON: `question`, `stream`, `subject`, `syllabus?`, `medium?`, `student_id`, `chat_history?`, `year?` | Ask NESH AI a question with RAG context + conversation memory |
| GET | `/chat/history/{student_id}` | query: `limit?` (default 50) | Get a student's chat history |
| DELETE | `/chat/history/{student_id}` | — | Clear a student's chat history |

### Search — `/search`
| Method | Path | Body/Params | Description |
|---|---|---|---|
| POST | `/search/` | JSON: `query`, `stream`, `subject?` | Standalone RAG search (semantic, top 8) returning results + built context |

### Voice — `/voice`
| Method | Path | Body/Params | Description |
|---|---|---|---|
| POST | `/voice/ask` | multipart form: `audio` (file) | ESP32 voice endpoint. Returns a WAV audio response |

---

## Environment Variables

No `.env.example` currently exists in the repo (see dev-logs). Based on the code, the following are required:

| Variable | Used by | Purpose |
|---|---|---|
| `SUPABASE_URL` | papers, chat, rag services | Supabase project URL |
| `SUPABASE_KEY` | papers, chat, rag services | Supabase API key (service role, since it inserts/deletes freely) |
| `VOYAGE_API_KEY` | rag_service | Voyage AI embeddings API key |
| `GEMINI_API_KEY` | ai_service | Google Gemini API key |
| `TESSERACT_PATH` | pdf_service | Optional path to a local Tesseract binary (for OCR fallback in dev) |

## Required External Setup

- **Supabase tables**: `past_papers`, `paper_chunks`, `chat_history` (schema not present in this repo — inferred from code).
- **Supabase RPC function**: `match_paper_chunks(query_embedding, filter_stream, filter_subject, match_count)` — a pgvector similarity search function, must exist in the Supabase Postgres instance.
- **Supabase Storage bucket**: `past-papers` (public read, for serving uploaded PDFs).
- **System binaries**: `ffmpeg` (declared in `Aptfile`/`nixpacks.toml`), and `tesseract-ocr` (**not currently declared** — see dev-logs).

---

## Running Locally

```bash
pip install -r requirements.txt
# create a .env file with the variables listed above
uvicorn main:app --reload
```

API docs (Swagger UI) available at `http://localhost:8000/docs` once running.

---

## Further Reading

See [`dev-logs/current-issues.md`](dev-logs/current-issues.md) for known issues, gaps, and suggested improvements (including Dockerization).
