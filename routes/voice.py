from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from gtts import gTTS
import tempfile
import os
import base64
import google.generativeai as genai
from services.rag_service import search_chunks_semantic, build_context
from services.ai_service import ask_nesh

router = APIRouter()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


def transcribe_with_gemini(audio_bytes: bytes) -> str:
    """Use Gemini to transcribe audio directly."""
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        audio_file = genai.upload_file(tmp_path, mime_type="audio/wav")
        
        response = model.generate_content([
            audio_file,
            "Transcribe exactly what is said in this audio. Return only the transcription text, nothing else."
        ])
        
        return response.text.strip()
    finally:
        try:
            os.unlink(tmp_path)
        except:
            pass


@router.post("/ask")
async def voice_ask(
    audio: UploadFile = File(...),
    stream: str = "Commerce",
    subject: str = "Economics",
    medium: str = "english",
    student_id: str = "esp32-robot"
):
    """
    Full voice pipeline:
    1. Receive audio from ESP32
    2. Gemini transcribes audio to text
    3. RAG search past papers
    4. Gemini generates answer
    5. gTTS converts to audio
    6. Return MP3 to ESP32
    """
    tmp_response_path = None

    try:
        # ── Step 1: Read audio ──
        audio_bytes = await audio.read()
        if len(audio_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty audio file")

        print(f"Received audio: {len(audio_bytes)} bytes")

        # ── Step 2: Transcribe with Gemini ──
        question = transcribe_with_gemini(audio_bytes)
        print(f"Transcribed: {question}")

        if not question:
            raise HTTPException(status_code=400, detail="Could not transcribe audio")

        # ── Step 3: RAG Search ──
        chunks = search_chunks_semantic(
            query=question,
            stream=stream,
            subject=subject,
            limit=5
        )
        context = build_context(chunks, max_chars=3000)

        # ── Step 4: Generate Answer ──
        answer = ask_nesh(
            question=question,
            context=context,
            stream=stream,
            subject=subject,
            medium=medium,
            chat_history=[]
        )
        print(f"Answer: {answer[:100]}...")

        # ── Step 5: Text to Speech ──
        tts_lang_map = {
            "sinhala": "si",
            "tamil": "ta",
            "english": "en"
        }
        tts_lang = tts_lang_map.get(medium.lower(), "en")

        tts = gTTS(text=answer, lang=tts_lang, slow=False)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_out:
            tts.save(tmp_out.name)
            tmp_response_path = tmp_out.name

        # ── Step 6: Return MP3 ──
        return FileResponse(
            tmp_response_path,
            media_type="audio/mpeg",
            filename="nesh_response.mp3",
            headers={
                "X-Question": question,
                "X-Answer-Preview": answer[:200]
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Voice error: {e}")
        raise HTTPException(status_code=500, detail=f"Voice processing failed: {str(e)}")
    finally:
        if tmp_response_path:
            try:
                os.unlink(tmp_response_path)
            except:
                pass


@router.get("/test")
def voice_test():
    return {
        "status": "Voice endpoint ready",
        "stt": "Gemini 2.5 Flash (multimodal)",
        "tts": "gTTS",
        "llm": "Gemini 2.5 Flash",
        "endpoint": "POST /voice/ask"
    }