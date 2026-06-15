from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from routes import papers, chat, search, voice
import os


# Load .env file first thing
load_dotenv()

# Import route modules
from routes import papers, chat, search

# ── Create FastAPI app ────────────────────────────────────────────────────────
app = FastAPI(
    title="Obscura Backend",
    description="AI-powered study assistant backend for Sri Lankan students",
    version="1.0.0"
)

# ── CORS Middleware ───────────────────────────────────────────────────────────
# This allows your Flutter app (and browser) to talk to this API.
# In production, replace "*" with your actual domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register Routes ───────────────────────────────────────────────────────────
app.include_router(papers.router, prefix="/papers", tags=["Past Papers"])
app.include_router(chat.router,   prefix="/chat",   tags=["NESH AI Chat"])
app.include_router(search.router, prefix="/search", tags=["RAG Search"])
app.include_router(voice.router, prefix="/voice", tags=["Voice IoT"])

# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "status":  "running",
        "message": "Obscura Backend ✅",
        "version": "1.0.0"
    }

@app.get("/health")
def health():
    return {"status": "healthy"}