from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import whisper
from gtts import gTTS
import tempfile
import os
from services.rag_service import search_chunks_semantic, build_context
from services.ai_service import ask_nesh

router = APIRouter()

# Load Whisper model once (small = fast + accurate enough)
print("Loading Whisper model...")
whisper_model = whisper.load_model("small")
print("Whisper model loaded!")


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
    2. Convert speech to text (Whisper)
    3. Search past papers (RAG)
    4. Generate answer (Gemini)
    5. Convert answer to speech (gTTS)
    6. Return audio file to ESP32
    """
    try:
        # ── Step 1: Save uploaded audio to temp file ──
        suffix = ".wav" if audio.filename.endswith(".wav") else ".mp3"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_audio:
            content = await audio.read()
            tmp_audio.write(content)
            tmp_audio_path = tmp_audio.name

        # ── Step 2: Speech to Text (Whisper) ──
        print(f"Transcribing audio: {tmp_audio_path}")
        result = whisper_model.transcribe(tmp_audio_path)
        question = result["text"].strip()
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

        # ── Step 4: Generate Answer (Gemini via NESH) ──
        answer = ask_nesh(
            question=question,
            context=context,
            stream=stream,
            subject=subject,
            medium=medium,
            chat_history=[]
        )
        print(f"Answer: {answer[:100]}...")

        # ── Step 5: Text to Speech (gTTS) ──
        lang = "si" if medium.lower() == "sinhala" else "ta" if medium.lower() == "tamil" else "en"
        tts = gTTS(text=answer, lang=lang, slow=False)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_response:
            tts.save(tmp_response.name)
            tmp_response_path = tmp_response.name

        # ── Step 6: Return audio file ──
        return FileResponse(
            tmp_response_path,
            media_type="audio/mpeg",
            filename="nesh_response.mp3",
            headers={
                "X-Question": question,
                "X-Answer-Preview": answer[:100]
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Voice error: {e}")
        raise HTTPException(status_code=500, detail=f"Voice processing failed: {str(e)}")
    finally:
        # Cleanup temp files
        try:
            os.unlink(tmp_audio_path)
        except:
            pass


@router.get("/test")
def voice_test():
    """Test if voice endpoint is working"""
    return {
        "status": "Voice endpoint ready",
        "whisper": "loaded",
        "tts": "gTTS ready",
        "endpoints": {
            "voice_ask": "POST /voice/ask — send audio file, get audio response"
        }
    }