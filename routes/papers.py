from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from supabase import create_client
from services.pdf_service import extract_text_from_pdf, chunk_text, get_pdf_page_count
from services.rag_service import save_chunks_with_embeddings
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)


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

        safe_filename = file.filename.replace(" ", "_")
        file_path = f"{stream}/{subject}/{year}/{safe_filename}"

        supabase.storage.from_("past-papers").upload(
            file_path,
            pdf_bytes,
            {"content-type": "application/pdf", "upsert": "true"}
        )

        url_result = supabase.storage.from_("past-papers").get_public_url(file_path)
        file_url = url_result if isinstance(url_result, str) else url_result.get("publicUrl") or url_result.get("publicURL") or str(url_result)

        page_count = get_pdf_page_count(pdf_bytes)

        paper_result = supabase.table("past_papers").insert({
            "title":      title,
            "subject":    subject,
            "stream":     stream,
            "syllabus":   syllabus,
            "medium":     medium,
            "year":       year,
            "file_url":   file_url,
            "page_count": page_count,
        }).execute()

        if not paper_result.data:
            raise HTTPException(status_code=500, detail="Failed to save paper")

        paper_id = paper_result.data[0]["id"]

        text = extract_text_from_pdf(pdf_bytes)

        if not text.strip():
            return {
                "message":        "Paper uploaded — no text extracted (scanned PDF)",
                "paper_id":       paper_id,
                "chunks_created": 0,
                "file_url":       file_url,
                "pages":          page_count,
            }

        chunks = chunk_text(text, chunk_size=400, overlap=80)
        saved_count = save_chunks_with_embeddings(paper_id, chunks)

        return {
            "message":        "Paper uploaded successfully",
            "paper_id":       paper_id,
            "chunks_created": saved_count,
            "file_url":       file_url,
            "pages":          page_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/list")
async def list_papers(
    stream: str = None,
    subject: str = None,
    syllabus: str = None,
    year: int = None,
):
    try:
        query = supabase.table("past_papers").select("*")

        if stream:
            query = query.eq("stream", stream)
        if subject:
            query = query.eq("subject", subject)
        if syllabus:
            query = query.eq("syllabus", syllabus)
        if year:
            query = query.eq("year", year)

        result = query.order("year", desc=True).execute()
        return {"papers": result.data, "count": len(result.data)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{paper_id}")
async def get_paper(paper_id: str):
    try:
        result = supabase.table("past_papers")\
            .select("*")\
            .eq("id", paper_id)\
            .single()\
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Paper not found")

        return result.data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{paper_id}")
async def delete_paper(paper_id: str):
    try:
        supabase.table("past_papers").delete().eq("id", paper_id).execute()
        return {"message": "Paper deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))