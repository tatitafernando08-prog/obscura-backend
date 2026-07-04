import subprocess
import os
import tempfile
from fastapi import APIRouter, File, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from gtts import gTTS

router = APIRouter()

MAX_AUDIO_BYTES = 5 * 1024 * 1024  # 5MB


def transcode_audio(input_mp3_path):
    """
    Uses system-level ffmpeg to transcode MP3 to raw PCM (16kHz, 16-bit, mono)
    to match ESP32 I2S register expectations.
    """
    output_wav = input_mp3_path.replace(".mp3", ".wav")

    # -f s16le: Signed 16-bit little-endian
    # -ar 16000: 16kHz
    # -ac 1: Mono
    command = [
        "ffmpeg", "-y", "-i", input_mp3_path,
        "-f", "s16le", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1", output_wav
    ]

    # Run ffmpeg as a system command
    subprocess.run(command, check=True, capture_output=True)
    return output_wav


@router.post("/ask")
async def voice_ask(request: Request, audio: UploadFile = File(...)):
    try:
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Audio file too large (max 5MB)")

        audio_bytes = await audio.read()

        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Audio file too large (max 5MB)")

        answer = "Hi, I am ready."

        # 1. Generate MP3
        tts = gTTS(text=answer, lang="en", slow=False)
        temp_mp3 = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tts.save(temp_mp3.name)
        temp_mp3.close()

        # 2. Transcode to Raw PCM
        temp_wav_path = transcode_audio(temp_mp3.name)

        # 3. Cleanup the intermediate MP3 now. The WAV is deleted only after
        # FileResponse finishes streaming it, via the background task below —
        # deleting it here would race the response trying to read it.
        os.unlink(temp_mp3.name)

        return FileResponse(
            temp_wav_path,
            media_type="audio/wav",
            background=BackgroundTask(os.unlink, temp_wav_path)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
