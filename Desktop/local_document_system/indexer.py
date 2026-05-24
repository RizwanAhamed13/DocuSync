import asyncio
import json
import sqlite3

import httpx

from embeddings import EMBEDDING_MODEL_NAME, get_chroma_collection, get_embedding_model

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_BASE_URL = "http://localhost:11434"

ollama_lock = asyncio.Lock()

_DEFAULT_METADATA = {
    "summary": "AI summary unavailable (is Ollama running?)",
    "tags": ["Uncategorized"],
    "key_findings": ["Could not extract findings automatically."],
    "entities": {"Companies": [], "Dates": [], "Project_Names": []},
}


def get_db_connection():
    # timeout=30: SQLite will retry for up to 30 s on "database is locked" instead of failing fast
    conn = sqlite3.connect("document_metadata.db", timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def chunk_document(
    pages_content: list[dict], chunk_size: int = 1000, chunk_overlap: int = 150
) -> list[dict]:
    """Splits page text into overlapping chunks preserving page numbers."""
    chunks = []
    for page in pages_content:
        text = page["text"]
        page_num = page["page"]
        start = 0
        while start < len(text):
            chunk_text = text[start : start + chunk_size].strip()
            if chunk_text:
                chunks.append({"page": page_num, "text": chunk_text})
            start += chunk_size - chunk_overlap
    return chunks


async def check_ollama_availability() -> dict:
    """Checks if Ollama is running and which models are available."""
    supported_prefixes = ("llama3", "phi3", "llama2", "mistral", "gemma", "qwen")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if response.status_code == 200:
                models = [m["name"] for m in response.json().get("models", [])]
                has_supported = any(
                    m.startswith(p) for m in models for p in supported_prefixes
                )
                return {
                    "available": True,
                    "models": models,
                    "has_supported_model": has_supported,
                    "warning": (
                        None
                        if has_supported
                        else "No supported model found. Run: ollama pull llama3"
                    ),
                }
    except Exception:
        pass
    return {
        "available": False,
        "models": [],
        "has_supported_model": False,
        "warning": (
            "Ollama unreachable at localhost:11434. "
            "Install from https://ollama.ai then run: ollama pull llama3"
        ),
    }


def check_model_version_match() -> bool:
    """
    Returns True if the configured embedding model matches what was used for
    existing vectors.  Saves the model name on first run.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            row = cursor.execute(
                "SELECT value FROM db_meta WHERE key = 'embedding_model'"
            ).fetchone()
        except sqlite3.OperationalError:
            # db_meta not yet created (init_db hasn't run yet)
            return True
        stored = row["value"] if row else None
        if stored is None:
            cursor.execute(
                "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('embedding_model', ?)",
                (EMBEDDING_MODEL_NAME,),
            )
            conn.commit()
            return True
        return stored == EMBEDDING_MODEL_NAME
    finally:
        conn.close()


def save_model_version():
    """Persists the current model name into db_meta. Call after /reset."""
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO db_meta (key, value) VALUES ('embedding_model', ?)",
        (EMBEDDING_MODEL_NAME,),
    )
    conn.commit()
    conn.close()


async def _call_ollama(model: str, payload: dict) -> dict | None:
    """Single Ollama call with up to 3 retries on timeout (exponential backoff)."""
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(OLLAMA_URL, json=payload)
                if response.status_code == 200:
                    return json.loads(response.json().get("response", "{}"))
                print(f"Ollama {model} returned HTTP {response.status_code}")
                return None
        except httpx.TimeoutException:
            wait = 2**attempt  # 1 s, 2 s, 4 s
            print(
                f"Ollama {model} timeout (attempt {attempt + 1}/3). "
                f"Retrying in {wait}s…"
            )
            if attempt < 2:
                await asyncio.sleep(wait)
        except json.JSONDecodeError as exc:
            print(f"Ollama {model} returned invalid JSON: {exc}")
            return None
        except Exception as exc:
            print(f"Ollama {model} unexpected error: {exc}")
            return None
    return None


async def extract_ai_metadata(text_sample: str) -> dict:
    """
    Calls Ollama (llama3 → phi3 fallback) under a global asyncio lock so
    concurrent uploads queue rather than overloading local hardware.

    Acquiring the lock itself is capped at 5 minutes — if more than one
    upload is queued and Ollama is very slow, later uploads return the
    default schema rather than blocking indefinitely.
    """
    prompt = f"""
You are an expert document cataloger. Analyze the document below and return a JSON object.

Generate 3-5 specific tags: the academic/professional field, core topics covered, and any distinctive features (e.g., policies, requirements).

Return ONLY this JSON schema with no extra text or markdown:
{{
  "summary": "A concise 2-sentence summary.",
  "tags": ["Tag1", "Tag2", "Tag3"],
  "key_findings": ["Takeaway 1", "Takeaway 2", "Takeaway 3"],
  "entities": {{
    "Companies": [],
    "Dates": [],
    "Project_Names": []
  }}
}}

Document:
{text_sample[:4000]}
"""
    base_payload = {"prompt": prompt, "format": "json", "stream": False}

    # Acquire lock with a 5-minute deadline to prevent indefinite queuing
    try:
        await asyncio.wait_for(ollama_lock.acquire(), timeout=300.0)
    except asyncio.TimeoutError:
        print(
            "Timed out waiting for Ollama lock (too many concurrent uploads). "
            "Using default metadata."
        )
        return _DEFAULT_METADATA

    try:
        for model in ["llama3", "phi3"]:
            result = await _call_ollama(model, {**base_payload, "model": model})
            if result and isinstance(result, dict) and "summary" in result:
                return result
            print(f"Model {model} returned unusable result, trying next…")
    finally:
        ollama_lock.release()

    return _DEFAULT_METADATA
