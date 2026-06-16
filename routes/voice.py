from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from gtts import gTTS
import tempfile
import os
import subprocess
from services.rag_service import search_chunks_semantic, build_context
from services.ai_service import ask_nesh

router = APIRouter()


def transcribe_audio(audio_bytes: bytes) -> str:
    """
    Convert audio to text using OpenAI Whisper CLI.
    Uses tiny model to minimize memory usage.
    """
    tmp_path = None
    try:
        # Save audio to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        # Run whisper as subprocess to avoid memory issues
        result = subprocess.run(
            ["whisper", tmp_path, "--model", "tiny", "--output_format", "txt", "--output_dir", "/tmp"],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            raise Exception(f"Whisper failed: {result.stderr}")

        # Read the output txt file
        txt_path = tmp_path.replace(".wav", ".txt")
        txt_path = f"/tmp/{os.path.basename(tmp_path).replace('.wav', '.txt')}"
        
        if os.path.exists(txt_path):
            with open(txt_path, "r") as f:
                transcript = f.read().strip()
            os.unlink(txt_path)
            return transcript
        else:
            raise Exception("Whisper output file not found")

    finally:
        if tmp_path and os.path.exists(tmp_path):
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
    2. Convert speech to text (Whisper CLI)
    3. Search past papers (RAG)
    4. Generate answer (Gemini)
    5. Convert answer to speech (gTTS)
    6. Return audio file to ESP32
    """
    tmp_response_path = None

    try:
        # ── Step 1: Read audio ──
        audio_bytes = await audio.read()

        if len(audio_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty audio file")

        print(f"Received audio: {len(audio_bytes)} bytes")

        # ── Step 2: Speech to Text ──
        question = transcribe_audio(audio_bytes)
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

        # ── Step 5: Text to Speech ──
        tts_lang_map = {
            "sinhala": "si",
            "tamil": "ta",
            "english": "en"
        }
        tts_lang = tts_lang_map.get(medium.lower(), "en")

        tts = gTTS(text=answer, lang=tts_lang, slow=False)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_response:
            tts.save(tmp_response.name)
            tmp_response_path = tmp_response.name

        print(f"TTS saved: {tmp_response_path}")

        # ── Step 6: Return audio ──
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
        "stt": "OpenAI Whisper (tiny)",
        "tts": "gTTS ready",
        "llm": "Gemini 2.5 Flash",
        "endpoints": {
            "voice_ask": "POST /voice/ask — send audio file, get audio response"
        }
    }