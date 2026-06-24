from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from gtts import gTTS
import tempfile
import os
import base64
import requests
from services.rag_service import search_chunks_semantic, build_context
from services.ai_service import ask_nesh

router = APIRouter()


def transcribe_with_gemini(audio_bytes: bytes) -> str:
    """Use Gemini API directly to transcribe audio via base64."""
    api_key = os.getenv("GEMINI_API_KEY")
    
    # Encode audio to base64
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "audio/wav",
                            "data": audio_b64
                        }
                    },
                    {
                        "text": "Transcribe exactly what is said in this audio. Return only the transcription, nothing else."
                    }
                ]
            }
        ]
    }
    
    response = requests.post(url, json=payload, timeout=30)
    
    if response.status_code != 200:
        raise Exception(f"Gemini STT failed: {response.text}")
    
    result = response.json()
    transcript = result["candidates"][0]["content"]["parts"][0]["text"].strip()
    return transcript


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
    4. Gemini generates answer via NESH
    5. gTTS converts answer to audio
    6. Return MP3 to ESP32
    """
    tmp_response_path = None

    try:
        # ── Step 1: Read audio ──
        audio_bytes = await audio.read()
        if len(audio_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty audio file")

        print(f"Received audio: {len(audio_bytes)} bytes")

        # ── Step 2: Transcribe ──
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
                "X-Question": question[:100].encode('ascii', 'ignore').decode(),
                "X-Answer-Preview": answer[:100].replace('\n', ' ').encode('ascii', 'ignore').decode()
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Voice error: {e}")
        raise HTTPException(status_code=500, detail=f"Voice processing failed: {str(e)}")
    finally:
        pass


@router.get("/test")
def voice_test():
    return {
        "status": "Voice endpoint ready",
        "stt": "Gemini 2.5 Flash (inline audio)",
        "tts": "gTTS",
        "llm": "Gemini 2.5 Flash",
        "endpoint": "POST /voice/ask"
    }