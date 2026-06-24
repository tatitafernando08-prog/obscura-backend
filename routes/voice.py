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
    api_key = os.getenv("GEMINI_API_KEY")
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inlineData": {  # MUST be camelCase
                            "mimeType": "audio/wav",
                            "data": audio_b64
                        }
                    },
                    {
                        "text": "Transcribe exactly what is said in this audio. Return only the transcription."
                    }
                ]
            }
        ]
    }
    
    response = requests.post(url, json=payload, timeout=60)
    
    if response.status_code != 200:
        raise Exception(f"Gemini STT failed: {response.text}")
    
    result = response.json()
    # Safely navigate the response
    return result["candidates"][0]["content"]["parts"][0]["text"].strip()
    return transcript


@router.post("/ask")
async def voice_ask(
    audio: UploadFile = File(...),
    stream: str = "Commerce",
    subject: str = "Economics",
    medium: str = "english",
    student_id: str = "esp32-robot"
):
    try:
        # 1. Read input
        await audio.read()
        
        # 2. EMERGENCY BYPASS: Extremely short text
        # "Hi" draws less power than a full sentence.
        answer = "Hi."
        
        # 3. TTS setup (slow=True makes it speak slower, which spreads the power draw over time)
        tts = gTTS(text=answer, lang="en", slow=True)
        
        # 4. Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_out:
            tts.save(tmp_out.name)
            tmp_response_path = tmp_out.name
        
        # 5. Return the file
        return FileResponse(
            tmp_response_path,
            media_type="audio/mpeg",
            filename="nesh_response.mp3"
        )
    except Exception as e:
        print(f"Voice error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
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