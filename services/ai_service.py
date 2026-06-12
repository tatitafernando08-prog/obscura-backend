import anthropic
import os
from dotenv import load_dotenv

load_dotenv()

# Create one client — reused for all requests
client = anthropic.Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

# ── NESH system prompt ────────────────────────────────────────────────────────
NESH_SYSTEM_PROMPT = """
You are NESH, a friendly and intelligent AI study assistant built into 
the Obscura Student Learning Platform for Sri Lankan students.

Your students may be studying:
- Local Sri Lanka syllabus (O/L or A/L)
- Edexcel International (O/L or A/L)
- Cambridge IGCSE / A Level

Streams: Science, Commerce, Arts, Technology
Languages: English, Sinhala (සිංහල), Tamil (தமிழ்)

Your responsibilities:
1. Answer subject questions clearly and accurately
2. Explain concepts in simple language with real examples
3. Help students understand past paper questions and mark schemes
4. Break down math and science problems step by step
5. Be encouraging — many students are stressed about exams

Rules:
- Always respond in the SAME language the student writes in
- If the student writes in Sinhala, reply in Sinhala
- If the student writes in Tamil, reply in Tamil
- For math/science: always show full working, not just the answer
- When using past paper content, say which paper it's from
- If you genuinely don't know, say so — never make up facts
- Keep answers focused and not too long unless the student asks for detail
- Use simple Sri Lankan examples where possible (e.g. rupees for economics)
"""

def ask_nesh(
    question:     str,
    context:      str,
    stream:       str,
    subject:      str,
    medium:       str = "english",
    chat_history: list[dict] = []
) -> str:
    """
    Ask NESH AI a question.

    question:     the student's question
    context:      relevant text retrieved from past papers (RAG)
    stream:       science / commerce / arts / technology
    subject:      e.g. Physics, Accounting
    medium:       english / sinhala / tamil
    chat_history: previous messages for conversation memory
                  format: [{"role": "user", "content": "..."}, ...]
    """

    # Build message list — start with recent history
    messages = []

    # Only keep last 6 messages to avoid token limits
    for msg in chat_history[-6:]:
        messages.append({
            "role":    msg.get("role",    "user"),
            "content": msg.get("content", "")
        })

    # Build the current user message
    # If we have RAG context, include it
    if context and context.strip():
        user_content = f"""
I found these relevant sections from past papers for you:

---
{context}
---

Student's question: {question}

Additional context:
- Student's stream: {stream}
- Subject: {subject}
- Preferred language: {medium}

Please answer the question using the past paper content above where relevant.
If the past paper content isn't directly relevant, answer from your knowledge.
"""
    else:
        # No RAG context — answer from general knowledge
        user_content = f"""
{question}

(Stream: {stream} | Subject: {subject} | Language: {medium})
"""

    messages.append({
        "role":    "user",
        "content": user_content
    })

    # Call Claude
    response = client.messages.create(
        model=      "claude-sonnet-4-20250514",
        max_tokens= 1500,
        system=     NESH_SYSTEM_PROMPT,
        messages=   messages
    )

    return response.content[0].text


def generate_flashcards(
    topic:   str,
    subject: str,
    stream:  str,
    count:   int = 10
) -> list[dict]:
    """
    Auto-generate flashcards for a topic using Claude.
    Returns a list of {"question": ..., "answer": ...} dicts.
    """
    prompt = f"""
Generate {count} flashcard question-answer pairs for:
- Subject: {subject}
- Stream: {stream}
- Topic: {topic}

Format your response as a numbered list exactly like this:
1. Q: [question here]
   A: [answer here]

2. Q: [question here]
   A: [answer here]

Make questions exam-focused. Answers should be concise but complete.
For formulas, include the formula in the answer.
"""

    response = client.messages.create(
        model=      "claude-sonnet-4-20250514",
        max_tokens= 2000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text

    # Parse the response into structured flashcards
    flashcards = []
    lines = raw.strip().split('\n')
    current_q = None

    for line in lines:
        line = line.strip()
        if line.startswith('Q:') or ('Q:' in line and line[0].isdigit()):
            current_q = line.split('Q:', 1)[-1].strip()
        elif line.startswith('A:') and current_q:
            answer = line.split('A:', 1)[-1].strip()
            flashcards.append({
                "question": current_q,
                "answer":   answer
            })
            current_q = None

    return flashcards


def summarize_topic(
    content: str,
    subject: str,
    stream:  str
) -> str:
    """
    Generate a concise summary of a topic from extracted PDF content.
    Used when a student clicks 'Summarize' on a past paper.
    """
    prompt = f"""
Summarize the following content from a {subject} past paper ({stream} stream).

Content:
{content[:3000]}  

Create a clear, structured summary with:
1. Main topics covered
2. Key formulas or definitions (if any)
3. Important points to remember for the exam

Keep it concise and student-friendly.
"""

    response = client.messages.create(
        model=      "claude-sonnet-4-20250514",
        max_tokens= 800,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text