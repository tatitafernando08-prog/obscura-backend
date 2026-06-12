import os
import voyageai
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

# Voyage AI client for embeddings
voyage = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))


def get_embedding(text: str) -> list[float]:
    """
    Convert text to a vector embedding using Voyage AI.
    voyage-2 produces 1536-dimensional vectors.
    """
    result = voyage.embed(
        texts=[text],
        model="voyage-2",
        input_type="query"
    )
    return result.embeddings[0]


def get_document_embedding(text: str) -> list[float]:
    """
    Embedding for documents being stored (different input_type).
    """
    result = voyage.embed(
        texts=[text],
        model="voyage-2",
        input_type="document"
    )
    return result.embeddings[0]


def search_chunks_semantic(
    query:   str,
    stream:  str,
    subject: str = "",
    limit:   int = 5
) -> list[dict]:
    """
    Semantic vector search — finds conceptually similar content
    even if exact words don't match.
    """
    try:
        # Convert query to embedding
        query_embedding = get_embedding(query)

        # Search using pgvector cosine similarity
        result = supabase.rpc(
            'match_paper_chunks',
            {
                'query_embedding': query_embedding,
                'filter_stream':   stream   if stream   else None,
                'filter_subject':  subject  if subject  else None,
                'match_count':     limit,
            }
        ).execute()

        return result.data if result.data else []

    except Exception as e:
        print(f"Semantic search error: {e}")
        # Fall back to keyword search if embeddings fail
        return search_chunks_keyword(query, stream, subject, limit)


def search_chunks_keyword(
    query:   str,
    stream:  str,
    subject: str = "",
    limit:   int = 5
) -> list[dict]:
    """
    Keyword fallback search using ilike.
    Used when embeddings aren't available yet for a paper.
    """
    try:
        db_query = supabase\
            .table("paper_chunks")\
            .select("*, past_papers(title, subject, year, stream, syllabus, file_url)")\
            .ilike("content", f"%{query}%")

        result = db_query.limit(limit).execute()
        return result.data if result.data else []

    except Exception as e:
        print(f"Keyword search error: {e}")
        return []


def build_context(chunks: list[dict], max_chars: int = 3000) -> str:
    """
    Build a RAG context string from retrieved chunks.
    """
    if not chunks:
        return ""

    context = ""
    total   = 0

    for i, chunk in enumerate(chunks):
        paper = chunk.get("past_papers", {}) or {}
        source = (
            f"{paper.get('subject', 'Unknown')} "
            f"{paper.get('year', '')} "
            f"({paper.get('syllabus', '')})"
        ).strip()

        chunk_text = f"[{source}]\n{chunk.get('content', '')}\n\n"

        if total + len(chunk_text) > max_chars:
            break

        context += chunk_text
        total   += len(chunk_text)

    return context.strip()


def save_chunks_with_embeddings(
    paper_id: str,
    chunks:   list[str]
) -> int:
    """
    Save chunks with their vector embeddings.
    Called after PDF upload and text extraction.
    """
    if not chunks:
        return 0

    saved = 0
    batch_size = 20  # Voyage API rate limit friendly

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]

        try:
            # Get embeddings for this batch
            result = voyage.embed(
                texts=batch,
                model="voyage-2",
                input_type="document"
            )
            embeddings = result.embeddings

            # Build records with embeddings
            records = [
                {
                    "paper_id":    paper_id,
                    "content":     batch[j],
                    "chunk_index": i + j,
                    "embedding":   embeddings[j],
                }
                for j in range(len(batch))
            ]

            supabase.table("paper_chunks").insert(records).execute()
            saved += len(batch)

        except Exception as e:
            print(f"Embedding batch {i} error: {e}")
            # Save without embeddings as fallback
            fallback = [
                {
                    "paper_id":    paper_id,
                    "content":     batch[j],
                    "chunk_index": i + j,
                }
                for j in range(len(batch))
            ]
            supabase.table("paper_chunks").insert(fallback).execute()
            saved += len(batch)

    return saved