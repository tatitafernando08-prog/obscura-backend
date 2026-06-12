from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.rag_service import search_chunks_semantic, build_context

router = APIRouter()

class SearchRequest(BaseModel):
    query:   str
    stream:  str
    subject: str = ""

class SearchResponse(BaseModel):
    results: list[dict]
    context: str
    count:   int

@router.post("/")
async def smart_search(request: SearchRequest):
    try:
        if not request.query.strip():
            raise HTTPException(status_code=400, detail="Search query cannot be empty")

        chunks = search_chunks_semantic(
            query=   request.query,
            stream=  request.stream,
            subject= request.subject,
            limit=   8
        )

        context = build_context(chunks)

        return SearchResponse(
            results= chunks,
            context= context,
            count=   len(chunks)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))