import os
import time
import json
import logging
from typing import Tuple, List, Dict
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

_MAX_CHARS  = 8_000
_MAX_TOKENS = 600
_RETRY_WAIT = 65


def _call_anthropic(prompt: str, max_tokens: int = _MAX_TOKENS) -> str | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        return text if len(text) > 20 else None
    except Exception as e:
        log.warning(f"[ai_service] Anthropic failed: {str(e)[:150]}")
    return None


def _call_openai(prompt: str, max_tokens: int = _MAX_TOKENS) -> str | None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        text = resp.choices[0].message.content.strip()
        return text if len(text) > 20 else None
    except Exception as e:
        log.warning(f"[ai_service] OpenAI failed: {str(e)[:150]}")
    return None


_gemini_client = None

def _get_gemini():
    global _gemini_client
    if _gemini_client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None
        try:
            from google import genai
            _gemini_client = genai.Client(api_key=api_key)
        except Exception as e:
            log.error(f"[ai_service] Gemini init failed: {e}")
    return _gemini_client

def _call_gemini(prompt: str) -> str | None:
    client = _get_gemini()
    if not client:
        return None
    for model_id in ["gemini-2.0-flash-lite", "gemini-2.0-flash"]:
        for attempt in range(1, 3):
            try:
                resp = client.models.generate_content(model=model_id, contents=prompt)
                text = resp.text.strip() if resp and resp.text else ""
                if len(text) > 20:
                    return text
                break
            except Exception as exc:
                err = str(exc)
                if "429" in err or "resource_exhausted" in err.lower():
                    if attempt < 2:
                        time.sleep(_RETRY_WAIT)
                        continue
                break
    return None


def _ai(prompt: str, max_tokens: int = _MAX_TOKENS) -> str | None:
    return _call_anthropic(prompt, max_tokens) or _call_openai(prompt, max_tokens) or _call_gemini(prompt)


# SUMMARIZE CHAPTER 
def summarize_chapter(chapter_title: str, chapter_text: str) -> Tuple[str, str]:
    snippet = chapter_text[:_MAX_CHARS].strip()
    if not snippet:
        return "No text content found in this chapter.", "none"

    prompt = (
        f"Summarize the book chapter titled '{chapter_title}'.\n"
        f"Write 2-3 paragraphs covering the main ideas, then list 3 key takeaways as bullets.\n"
        f"Be concise. No filler.\n\n{snippet}"
    )
    result = _ai(prompt)
    if result:
        model = "claude-haiku-4-5" if os.environ.get("ANTHROPIC_API_KEY") else \
                "gpt-4o-mini" if os.environ.get("OPENAI_API_KEY") else "gemini"
        return result, model

    return "Summary unavailable — all AI providers failed. Check your API keys in .env", "error"


# EXTRACT VOCABULARY 
def extract_vocabulary(chapter_title: str, chapter_text: str) -> List[Dict[str, str]]:
    """
    Extract 5-8 difficult or important words from the chapter with definitions.
    Returns a list of {"word": ..., "definition": ...} dicts.
    """
    snippet = chapter_text[:_MAX_CHARS].strip()
    if not snippet:
        return []

    prompt = (
        f"From the book chapter titled '{chapter_title}', extract 5 to 8 difficult, "
        f"technical, or important words that a student might not know.\n\n"
        f"Return ONLY a JSON array, no explanation, no markdown, like this:\n"
        f'[{{"word": "Monopoly", "definition": "A market dominated by a single company with no competition."}}]\n\n'
        f"Chapter content:\n{snippet}"
    )

    raw = _ai(prompt, max_tokens=800)
    if not raw:
        return []

    try:
        # Strip markdown code fences if present
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(clean)
        if isinstance(data, list):
            return [
                {"word": str(item.get("word", "")), "definition": str(item.get("definition", ""))}
                for item in data
                if item.get("word") and item.get("definition")
            ]
    except (json.JSONDecodeError, Exception) as e:
        log.warning(f"[ai_service] Vocabulary JSON parse failed: {e} | raw: {raw[:200]}")

    return []


# GENERATE RECOMMENDATIONS
def generate_recommendations(book_title: str, book_summary: str) -> List[Dict[str, str]]:
    """
    Generate 3 book recommendations based on a book the user just read.
    Returns a list of {"title": ..., "author": ..., "reason": ...} dicts.
    """
    prompt = (
        f"A user just read '{book_title}'.\n"
        f"Brief summary of the book: {book_summary[:500]}\n\n"
        f"Recommend 3 similar books they would enjoy.\n"
        f"Return ONLY a JSON array, no explanation, no markdown, like this:\n"
        f'[{{"title": "Book Name", "author": "Author Name", "reason": "Why it is similar."}}]\n'
    )

    raw = _ai(prompt, max_tokens=600)
    if not raw:
        return []

    try:
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(clean)
        if isinstance(data, list):
            return [
                {
                    "title":  str(item.get("title", "")),
                    "author": str(item.get("author", "")),
                    "reason": str(item.get("reason", "")),
                }
                for item in data
                if item.get("title")
            ]
    except (json.JSONDecodeError, Exception) as e:
        log.warning(f"[ai_service] Recommendations JSON parse failed: {e} | raw: {raw[:200]}")

    return []


# DETECT CATEGORY
def detect_category(book_title: str, first_chapter_text: str) -> str:
    """
    Detect the genre/category of a book from its title and first chapter.
    Returns a single category string like "Business", "Science Fiction", etc.
    """
    snippet = first_chapter_text[:2000].strip()

    prompt = (
        f"What is the genre or category of the book titled '{book_title}'?\n"
        f"Here is the beginning of the book:\n{snippet}\n\n"
        f"Reply with ONLY a single category name, nothing else. "
        f"Examples: Business, Self-Help, Science Fiction, History, Psychology, "
        f"Philosophy, Technology, Biography, Economics, Fiction."
    )

    result = _ai(prompt, max_tokens=20)
    if result:
        # Clean up — take only the first line, strip punctuation
        category = result.strip().splitlines()[0].strip(" .,!?\"'")
        return category[:100]

    return "General"