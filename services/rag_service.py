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


# ── Embeddings ────────────────────────────────────────────────────────────────

def get_embedding(text: str) -> list[float]:
    """Convert query text to vector embedding using Voyage AI."""
    result = voyage.embed(
        texts=[text],
        model="voyage-2",
        input_type="query"
    )
    return result.embeddings[0]


def get_document_embedding(text: str) -> list[float]:
    """Convert document text to vector embedding."""
    result = voyage.embed(
        texts=[text],
        model="voyage-2",
        input_type="document"
    )
    return result.embeddings[0]


# ── Semantic Search ───────────────────────────────────────────────────────────

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


# ── Keyword Search ────────────────────────────────────────────────────────────

def search_chunks_keyword(
    query:   str,
    stream:  str,
    subject: str = "",
    limit:   int = 8
) -> list[dict]:
    """
    Keyword fallback search using ilike.
    Used when embeddings aren't available or semantic search fails.
    """
    try:
        keywords = query.split()[:5]  # Use first 5 words
        db_query = supabase \
            .table("paper_chunks") \
            .select("*, past_papers(title, subject, year, stream, syllabus, file_url)")

        # Search for any of the keywords
        for keyword in keywords:
            if len(keyword) > 3:  # Skip short words
                db_query = db_query.ilike("content", f"%{keyword}%")
                break  # Use first meaningful keyword

        result = db_query.limit(limit).execute()
        return result.data if result.data else []

    except Exception as e:
        print(f"Keyword search error: {e}")
        return []


# ── Hybrid Search ─────────────────────────────────────────────────────────────

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

    # Combine and deduplicate by chunk id
    seen_ids = set()
    combined = []

    # Semantic results get priority
    for chunk in semantic_results:
        chunk_id = chunk.get("id")
        if chunk_id not in seen_ids:
            seen_ids.add(chunk_id)
            chunk["_source"] = "semantic"
            combined.append(chunk)

    # Add keyword results not already in semantic
    for chunk in keyword_results:
        chunk_id = chunk.get("id")
        if chunk_id not in seen_ids:
            seen_ids.add(chunk_id)
            chunk["_source"] = "keyword"
            combined.append(chunk)

    # Re-rank combined results
    reranked = rerank_chunks(query, combined)

    return reranked[:limit]


# ── Re-ranking ────────────────────────────────────────────────────────────────

def rerank_chunks(query: str, chunks: list[dict]) -> list[dict]:
    """
    Re-rank chunks by relevance to query.
    Uses a simple scoring system:
    - Similarity score from pgvector (if available)
    - Keyword overlap with query
    - Recency (newer papers score higher)
    - Source bonus (semantic > keyword)
    """
    if not chunks:
        return []

    query_words = set(query.lower().split())

    scored = []
    for chunk in chunks:
        score = 0.0

        # 1. Similarity score from vector search (0-1)
        similarity = chunk.get("similarity", 0)
        score += similarity * 0.5

        # 2. Keyword overlap score
        content = chunk.get("content", "").lower()
        content_words = set(content.split())
        overlap = len(query_words & content_words)
        keyword_score = min(overlap / max(len(query_words), 1), 1.0)
        score += keyword_score * 0.3

        # 3. Source bonus
        if chunk.get("_source") == "semantic":
            score += 0.1

        # 4. Recency bonus (newer papers are slightly preferred)
        paper = chunk.get("past_papers", {}) or {}
        year = paper.get("year", 2015)
        recency = min((year - 2010) / 15, 1.0)  # Normalize 2010-2025
        score += recency * 0.1

        chunk["_score"] = score
        scored.append(chunk)

    # Sort by score descending
    scored.sort(key=lambda x: x.get("_score", 0), reverse=True)

    return scored


# ── Context Builder ───────────────────────────────────────────────────────────

def build_context(chunks: list[dict], max_chars: int = 4000) -> str:
    """
    Build a rich RAG context string from retrieved chunks.
    Includes source information for citation.
    Improved: avoids duplicate content, better formatting.
    """
    if not chunks:
        return ""

    context = "RELEVANT PAST PAPER CONTENT:\n\n"
    total = len(context)
    seen_content = set()

    for i, chunk in enumerate(chunks):
        paper = chunk.get("past_papers", {}) or {}
        subject  = paper.get("subject", "Unknown Subject")
        year     = paper.get("year", "")
        syllabus = paper.get("syllabus", "")
        score    = chunk.get("_score", chunk.get("similarity", 0))

        # Build source label
        source = f"{subject} {year} {syllabus}".strip()

        content = chunk.get("content", "").strip()

        # Skip duplicate or near-duplicate content
        content_key = content[:100]
        if content_key in seen_content:
            continue
        seen_content.add(content_key)

        chunk_text = f"[Source {i+1}: {source}]\n{content}\n\n"

        if total + len(chunk_text) > max_chars:
            break

        context += chunk_text
        total += len(chunk_text)

    return context.strip()


# ── Save Chunks ───────────────────────────────────────────────────────────────

def save_chunks_with_embeddings(
    paper_id: str,
    chunks:   list[str]
) -> int:
    """
    Save chunks with their vector embeddings to Supabase.
    Called after PDF upload and text extraction.
    Uses batching for Voyage API rate limit compliance.
    """
    if not chunks:
        return 0

    saved = 0
    batch_size = 20

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]

        try:
            result = voyage.embed(
                texts=batch,
                model="voyage-2",
                input_type="document"
            )
            embeddings = result.embeddings

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