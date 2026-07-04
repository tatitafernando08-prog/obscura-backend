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
