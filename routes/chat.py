from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.rag_service import search_chunks_hybrid, build_context
from services.ai_service import ask_nesh
from supabase import create_client
import os
import traceback
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

class ChatRequest(BaseModel):
    question:     str
    stream:       str
    subject:      str
    syllabus:     str = ""
    medium:       str = "english"
    student_id:   str
    chat_history: list[dict] = []
    year:         int = None  # Optional year filter

class ChatResponse(BaseModel):
    answer:  str
    sources: list[dict] = []

@router.post("/ask")
async def ask_question(request: ChatRequest):
    try:
        if not request.question.strip():
            raise HTTPException(status_code=400, detail="Question cannot be empty")

        # Use hybrid search (semantic + keyword + reranking)
        chunks = search_chunks_hybrid(
            query=    request.question,
            stream=   request.stream,
            subject=  request.subject,
            syllabus= request.syllabus,
            limit=    5
        )

        # Build rich context from top chunks
        context = build_context(chunks, max_chars=4000)

        # Generate answer with NESH
        answer = ask_nesh(
            question=     request.question,
            context=      context,
            stream=       request.stream,
            subject=      request.subject,
            medium=       request.medium,
            chat_history= request.chat_history
        )

        # Save to chat history
        source_titles = []
        for chunk in chunks[:3]:
            paper = chunk.get("past_papers", {})
            if paper:
                source_titles.append(
                    f"{paper.get('subject', '')} {paper.get('year', '')}"
                )

        supabase.table("chat_history").insert({
            "student_id": request.student_id,
            "question":   request.question,
            "answer":     answer,
            "sources":    source_titles
        }).execute()

        return ChatResponse(answer=answer, sources=chunks[:3])

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


@router.get("/history/{student_id}")
async def get_history(student_id: str, limit: int = 50):
    try:
        result = supabase.table("chat_history")\
            .select("*")\
            .eq("student_id", student_id)\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()

        return {"history": result.data, "count": len(result.data)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/history/{student_id}")
async def clear_history(student_id: str):
    try:
        supabase.table("chat_history")\
            .delete()\
            .eq("student_id", student_id)\
            .execute()

        return {"message": "Chat history cleared"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))