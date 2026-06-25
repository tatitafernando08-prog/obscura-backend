from pydub import AudioSegment
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
        # Read the incoming microphone payload to keep the connection intact
        await audio.read()
        
        # Keep the response extremely brief to minimize power spikes during the demo
        answer = "Hi, I am ready."
        
        # 1. Generate the base MP3 audio using Google TTS
        tts = gTTS(text=answer, lang="en", slow=False)
        
        temp_mp3 = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tts.save(temp_mp3.name)
        temp_mp3.close()
        
        # 2. TRANSCODE THE MP3 TO UNCOMPRESSED WAV MATCHING HER ESP32 SETTINGS
        # This breaks the audio file down into the raw PCM samples her code expects
        sound = AudioSegment.from_mp3(temp_mp3.name)
        
        # Force the track to 16000Hz, Mono channel, and 16-bit sample width (2 bytes)
        sound = sound.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        
        # Write out to a temporary WAV file format path
        temp_wav_path = temp_mp3.name.replace(".mp3", ".wav")
        sound.export(temp_wav_path, format="wav")
        
        # Delete the intermediate compressed file
        os.unlink(temp_mp3.name)
        
        # 3. Return the raw uncompressed WAV payload to her stream client
        return FileResponse(
            temp_wav_path,
            media_type="audio/wav",
            filename="nesh_response.wav"
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