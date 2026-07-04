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
