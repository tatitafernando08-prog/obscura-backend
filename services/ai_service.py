import google.generativeai as genai
import os
import re
from dotenv import load_dotenv

load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Use Gemini Flash 2.5 — free and fast
MODEL = "gemini-2.5-flash-preview-05-20"

# ── NESH System Prompt ────────────────────────────────────────────────────────

NESH_SYSTEM_PROMPT = """
You are NESH (Neural Education Study Helper), an advanced AI study assistant 
built into the Obscura Student Learning Platform.

ABOUT OBSCURA:
Obscura is a comprehensive study platform designed for students worldwide,
with a strong focus on Sri Lankan O/L and A/L students. It supports:
- Local Sri Lanka syllabus (O/L and A/L)
- Edexcel International (IGCSE and IAL)
- Cambridge Assessment (IGCSE and A Level)
- Streams: Science, Commerce, Arts, Technology
- Languages: English, Sinhala (සිංහල), Tamil (தமிழ்)

YOUR PERSONALITY:
- Friendly, encouraging, and patient — like a brilliant senior student
- Never condescending — you understand exam stress
- Honest — if you don't know something, say so clearly
- Precise — especially for formulas, dates, and definitions
- Culturally aware — use Sri Lankan examples where relevant (rupees, local context)

YOUR CORE RESPONSIBILITIES:
1. Answer subject questions clearly using past paper context when available
2. Explain complex concepts with simple language and real-world examples
3. Break down problems step-by-step — never skip steps in math or science
4. Help students understand mark scheme expectations
5. Provide exam tips and study strategies when asked
6. Generate practice questions when requested
7. Support multilingual students — always respond in their language

LANGUAGE RULES (CRITICAL):
- Detect the language the student writes in and ALWAYS reply in that same language
- If they write in Sinhala → reply fully in Sinhala
- If they write in Tamil → reply fully in Tamil
- If they write in English → reply in English

PAST PAPER CONTEXT RULES:
- When past paper content is provided, prioritize it in your answer
- Always cite which paper you're referencing
- If the context isn't directly relevant, answer from your general knowledge

FORMATTING RULES:
- Use bullet points and numbered lists for multi-step explanations
- Use **bold** for key terms and formulas
- For math: show every step on a new line
- Keep answers focused and not too long unless the student asks for detail

WHAT YOU CAN ANSWER:
- Any subject question (not just the student's stream)
- General knowledge questions
- Study tips, time management, exam strategies
- Career guidance and university advice
"""

# ── Main NESH Function ────────────────────────────────────────────────────────

def ask_nesh(
    question:     str,
    context:      str,
    stream:       str,
    subject:      str,
    medium:       str = "english",
    chat_history: list[dict] = []
) -> str:
    """
    Ask NESH AI a question with RAG context and conversation memory.
    Uses Gemini Flash 2.5 — free tier.
    """
    model = genai.GenerativeModel(
        model_name=MODEL,
        system_instruction=NESH_SYSTEM_PROMPT
    )

    # Build conversation history for Gemini format
    history = []
    for msg in chat_history[-6:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if content:
            # Gemini uses 'user' and 'model' (not 'assistant')
            gemini_role = "model" if role == "assistant" else "user"
            history.append({
                "role": gemini_role,
                "parts": [content]
            })

    # Build the current message
    if context and context.strip():
        user_message = f"""Here is relevant content retrieved from past papers:

{context}

---

Student Profile:
- Stream: {stream}
- Subject Focus: {subject}
- Preferred Language: {medium}

Student's Question: {question}

Please use the past paper content above where relevant and cite the source."""
    else:
        user_message = f"""Student Profile:
- Stream: {stream}
- Subject Focus: {subject}
- Preferred Language: {medium}

Student's Question: {question}

Note: No specific past paper content found. Please answer from general knowledge."""

    # Start chat with history
    chat = model.start_chat(history=history)
    response = chat.send_message(user_message)

    return response.text


# ── Flashcard Generator ───────────────────────────────────────────────────────

def generate_flashcards(
    topic:   str,
    subject: str,
    stream:  str,
    count:   int = 10
) -> list[dict]:
    """Auto-generate exam-focused flashcards using Gemini."""
    model = genai.GenerativeModel(model_name=MODEL)

    prompt = f"""Generate exactly {count} flashcard question-answer pairs for exam preparation.

Subject: {subject}
Stream: {stream}
Topic: {topic}

Format EXACTLY like this:
1. Q: [question]
   A: [answer]

2. Q: [question]
   A: [answer]"""

    response = model.generate_content(prompt)
    raw = response.text

    flashcards = []
    lines = raw.strip().split('\n')
    current_q = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        q_match = re.search(r'Q:\s*(.+)', line)
        a_match = re.search(r'A:\s*(.+)', line)
        if q_match:
            current_q = q_match.group(1).strip()
        elif a_match and current_q:
            flashcards.append({
                "question": current_q,
                "answer": a_match.group(1).strip()
            })
            current_q = None

    return flashcards


# ── Topic Summarizer ──────────────────────────────────────────────────────────

def summarize_topic(content: str, subject: str, stream: str) -> str:
    """Generate a structured exam-ready summary."""
    model = genai.GenerativeModel(model_name=MODEL)

    prompt = f"""Create a comprehensive exam revision summary from this {subject} content ({stream} stream).

Content:
{content[:3000]}

Structure:
## Key Concepts
## Important Definitions
## Formulas & Rules
## Exam Tips"""

    response = model.generate_content(prompt)
    return response.text


# ── Study Plan Generator ──────────────────────────────────────────────────────

def generate_study_plan(
    subjects: list[str],
    exam_date: str,
    hours_per_day: int = 4
) -> str:
    """Generate a personalised study plan."""
    model = genai.GenerativeModel(model_name=MODEL)

    prompt = f"""Create a structured study plan.

Subjects: {', '.join(subjects)}
Exam Date: {exam_date}
Hours Per Day: {hours_per_day}

Create a week-by-week realistic plan with past paper practice included."""

    response = model.generate_content(prompt)
    return response.text


# ── Question Analyzer ─────────────────────────────────────────────────────────

def analyze_past_paper_question(
    question: str,
    subject: str,
    marks: int = None
) -> str:
    """Analyze a past paper question with model answer."""
    model = genai.GenerativeModel(model_name=MODEL)

    marks_info = f" ({marks} marks)" if marks else ""

    prompt = f"""Analyze this {subject} past paper question{marks_info}:

Question: {question}

Provide:
1. What the examiner wants
2. Model Answer
3. Common Mistakes
4. Examiner Tips
5. Key Terms to include"""

    response = model.generate_content(prompt)
    return response.text