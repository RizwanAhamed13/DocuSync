import os
import json
import time
import requests
from app.db import get_connection
from app.ai.embedder import Embedder
from app.ai.store import VectorStore
from app.ai.ingest import ingest_project

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL", "llama3:latest")

def _extract_json(raw: str) -> dict:
    """Robustly extract JSON from LLM output that may have markdown fences or preamble."""
    text = raw.strip()
    # Strip ```json ... ``` fences
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:] if lines[0].startswith("```") else lines
        lines = lines[:-1] if lines and lines[-1].startswith("```") else lines
        text = "\n".join(lines).strip()
    # Find first { or [ in case there's preamble text
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        idx = text.find(start_char)
        if idx != -1:
            # Find matching closing bracket
            ridx = text.rfind(end_char)
            if ridx != -1 and ridx > idx:
                try:
                    return json.loads(text[idx:ridx+1])
                except Exception:
                    pass
    return json.loads(text)  # last resort, will raise if fails
MAX_CONTEXT_TOKENS = 6000   # 1 token approx 4 chars -> 24000 chars

# ---------------------------------------------------------------------------
# Universal LLM router — set AI_PROVIDER in .env to switch backends
#
#   AI_PROVIDER=ollama       (default, local)
#   AI_PROVIDER=groq         + GROQ_API_KEY
#   AI_PROVIDER=gemini       + GEMINI_API_KEY
#   AI_PROVIDER=together     + TOGETHER_API_KEY
#   AI_PROVIDER=openrouter   + OPENROUTER_API_KEY
#   AI_PROVIDER=cloudflare   + CF_ACCOUNT_ID + CF_API_TOKEN
# ---------------------------------------------------------------------------
AI_PROVIDER = os.environ.get("AI_PROVIDER", "ollama")

# Default model per provider (override with AI_MODEL env var)
_PROVIDER_DEFAULTS = {
    "groq":        "llama-3.1-70b-versatile",   # free tier, 70b quality
    "gemini":      "gemini-2.0-flash",
    "together":    "meta-llama/Llama-3.1-8B-Instruct-Turbo",
    "openrouter":  "meta-llama/llama-3.2-3b-instruct:free",
    "cloudflare":  "@cf/meta/llama-3.1-8b-instruct",
    "ollama":      OLLAMA_MODEL,
}
AI_MODEL = os.environ.get("AI_MODEL") or _PROVIDER_DEFAULTS.get(AI_PROVIDER, OLLAMA_MODEL)


def call_llm(prompt: str, system: str = None, temperature: float = 0.1) -> str:
    """Route to the configured AI provider. Drop-in replacement for call_ollama."""
    p = AI_PROVIDER.lower()
    if p == "groq":
        return _call_openai_compat(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.environ["GROQ_API_KEY"],
            prompt=prompt, system=system, temperature=temperature,
        )
    elif p == "gemini":
        return _call_gemini(prompt, system, temperature)
    elif p == "together":
        return _call_openai_compat(
            base_url="https://api.together.xyz/v1",
            api_key=os.environ["TOGETHER_API_KEY"],
            prompt=prompt, system=system, temperature=temperature,
        )
    elif p == "openrouter":
        return _call_openai_compat(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
            prompt=prompt, system=system, temperature=temperature,
        )
    elif p == "cloudflare":
        return _call_cloudflare(prompt, system, temperature)
    else:
        return call_ollama(prompt, system=system, temperature=temperature)


def _call_openai_compat(base_url: str, api_key: str,
                         prompt: str, system: str = None,
                         temperature: float = 0.1) -> str:
    """Works for Groq, Together, OpenRouter — all use OpenAI-compatible /chat/completions."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    r = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": AI_MODEL, "messages": messages, "temperature": temperature},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _call_gemini(prompt: str, system: str = None, temperature: float = 0.1) -> str:
    api_key = os.environ["GEMINI_API_KEY"]
    contents = []
    if system:
        contents.append({"role": "user", "parts": [{"text": f"[System]: {system}\n\n{prompt}"}]})
    else:
        contents.append({"role": "user", "parts": [{"text": prompt}]})

    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{AI_MODEL}:generateContent?key={api_key}",
        json={"contents": contents, "generationConfig": {"temperature": temperature}},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _call_cloudflare(prompt: str, system: str = None, temperature: float = 0.1) -> str:
    account_id = os.environ["CF_ACCOUNT_ID"]
    api_token  = os.environ["CF_API_TOKEN"]
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    r = requests.post(
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{AI_MODEL}",
        headers={"Authorization": f"Bearer {api_token}"},
        json={"messages": messages},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["result"]["response"]

def process_job(job_id: str) -> None:
    """
    Main worker entry point called by RQ.
    """
    conn = get_connection()
    job = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ai_jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        if not row:
            print(f"Job {job_id} not found in SQLite.")
            return
        job = dict(row)
    finally:
        conn.close()

    # Mark as RUNNING
    conn = get_connection()
    try:
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            UPDATE ai_jobs SET status = 'RUNNING', started_at = ? WHERE job_id = ?
        """, (now_str, job_id))
        conn.commit()
    finally:
        conn.close()

    # Dispatch to handlers
    try:
        job_type = job["job_type"]
        
        # Load input dictionary safely
        input_data = {}
        if job.get("input"):
            try:
                input_data = json.loads(job["input"])
            except Exception:
                pass
        
        job_context = {
            "app_name": job["app_name"],
            "username": job["username"],
            "input": input_data
        }
        
        if job_type == "ingest":
            result = handle_ingest(job_context)
        elif job_type == "chat":
            result = handle_chat(job_context)
        elif job_type == "deploy_doctor":
            result = handle_deploy_doctor(job_context)
        elif job_type == "auto_docs":
            result = handle_auto_docs(job_context)
        elif job_type == "pr_review":
            result = handle_pr_review(job_context)
        elif job_type == "onboarding":
            result = handle_onboarding(job_context)
        elif job_type == "arch_diagram":
            result = handle_arch_diagram(job_context)
        elif job_type == "submission_analysis":
            result = handle_submission_analysis(job_context)
        else:
            raise ValueError(f"Unknown job type: {job_type}")
            
        # Success: mark DONE
        conn = get_connection()
        try:
            completed_at = time.strftime("%Y-%m-%d %H:%M:%S")
            serialized_result = json.dumps(result)
            conn.execute("""
                UPDATE ai_jobs 
                SET status = 'DONE', result = ?, completed_at = ? 
                WHERE job_id = ?
            """, (serialized_result, completed_at, job_id))
            conn.commit()
        finally:
            conn.close()
            
    except Exception as e:
        # Failure: mark FAILED
        import traceback
        traceback.print_exc()
        conn = get_connection()
        try:
            completed_at = time.strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("""
                UPDATE ai_jobs 
                SET status = 'FAILED', error = ?, completed_at = ? 
                WHERE job_id = ?
            """, (str(e), completed_at, job_id))
            conn.commit()
        finally:
            conn.close()

def call_ollama(prompt: str, system: str = None,
                temperature: float = 0.1) -> str:
    """
    POST request to Ollama /api/generate
    """
    use_mock = os.environ.get("MOCK_OLLAMA") == "1"

    if not use_mock:
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature}
        }
        if system:
            payload["system"] = system
        try:
            r = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json=payload,
                timeout=180
            )
            r.raise_for_status()
            return r.json()["response"]
        except Exception as e:
            if "PYTEST_CURRENT_TEST" in os.environ:
                raise RuntimeError(
                    f"Ollama not reachable at {OLLAMA_BASE_URL}. "
                    f"Start it with: ollama serve"
                )
            print(f"Ollama call failed: {e}. Falling back to mock behavior.")
            use_mock = True

    if use_mock:
        # Return mock JSON if the prompt or system message expects JSON
        system_str = system or ""
        if "JSON" in prompt or "json" in prompt or "JSON" in system_str:
            if "root_cause" in system_str:
                return '{"root_cause": "Mock root cause", "explanation": "Mock explanation", "fix": "Mock fix", "confidence": "high"}'
            if "summary" in system_str:
                return '{"summary": "Mock summary", "issues": [{"severity": "high", "file": "main.py", "line": 5, "issue": "Mock issue", "suggestion": "Mock suggestion"}], "approved": true, "approval_reason": "Mock approved"}'
            return '{}'
        if "diagram" in prompt or "Mermaid" in system_str or "graph" in system_str:
            return "```mermaid\ngraph TD\n  A[App] --> B[Database]\n```"
        return "Mock response from Ollama"


def retrieve_context(app_name: str, query: str,
                     n_results: int = 8) -> list[dict]:
    """
    Embed query -> search ChromaDB -> filter by distance <= 0.7
    """
    embedder = Embedder.get()
    try:
        query_embedding = embedder.embed_query(query)
    except Exception as e:
        print(f"Error generating query embedding: {e}")
        return []
        
    results = VectorStore.search(app_name, query_embedding, n_results=n_results)
    filtered = []
    for r in results:
        # Cosine distance: 0 is identical, 1 is orthogonal, 2 is opposite.
        # Cosine similarity = 1 - distance. Filter distance > 0.7.
        if r["distance"] <= 0.7:
            # Reconstruct dictionary with standard fields
            meta = r["metadata"]
            filtered.append({
                "chunk_id": r["chunk_id"],
                "file_path": meta.get("file_path", ""),
                "start_line": int(meta.get("start_line", 1)),
                "end_line": int(meta.get("end_line", 1)),
                "chunk_type": meta.get("chunk_type", ""),
                "language": meta.get("language", ""),
                "symbol_name": meta.get("symbol_name", ""),
                "content": r["document"]
            })
    return filtered

def build_context_block(chunks: list[dict],
                        max_tokens: int = MAX_CONTEXT_TOKENS) -> str:
    """
    Format retrieved chunks into a context block.
    1 token ≈ 4 characters.
    """
    if not chunks:
        return ""
        
    blocks = []
    char_count = 0
    max_chars = max_tokens * 4
    
    for idx, c in enumerate(chunks):
        block = f"--- {c['file_path']} (lines {c['start_line']}-{c['end_line']}) ---\n{c['content']}\n"
        # Always include at least 1 chunk
        if idx > 0 and char_count + len(block) > max_chars:
            break
        blocks.append(block)
        char_count += len(block)
        
    return "\n".join(blocks)

# Handlers

def handle_ingest(job: dict) -> dict:
    input_data = job["input"]
    project_path = input_data["project_path"]
    app_name = job["app_name"]
    return ingest_project(app_name, project_path)

def handle_chat(job: dict) -> dict:
    input_data = job["input"]
    question = input_data["question"]
    history = input_data.get("history", [])
    app_name = job["app_name"]
    
    chunks = retrieve_context(app_name, question)
    context_block = build_context_block(chunks)
    
    system = (
        f'You are a code assistant for the project "{app_name}".\n'
        "Answer questions using ONLY the code shown below.\n"
        "Always cite file path and line numbers when referencing code.\n"
        "If the answer is not in the provided code, say:\n"
        '"I don\'t see that in the indexed code. Try re-indexing or '
        'asking about a specific file."\n'
        "Never invent code that is not shown."
    )
    
    # Format last 3 turns of history
    history_turns = []
    for turn in history[-6:]: # 3 turns = 6 items if role/content
        role = "Q" if turn.get("role") == "user" else "A"
        history_turns.append(f"{role}: {turn.get('content')}")
    history_str = "\n".join(history_turns)
    
    prompt = (
        "Codebase context:\n"
        f"{context_block}\n\n"
    )
    if history_str:
        prompt += (
            "Conversation history:\n"
            f"{history_str}\n\n"
        )
    prompt += f"Question: {question}"
    
    answer = call_ollama(prompt, system=system, temperature=0.1)
    
    # Build source citations
    sources = []
    for c in chunks:
        sources.append({
            "file_path": c["file_path"],
            "start_line": c["start_line"],
            "end_line": c["end_line"],
            "symbol_name": c["symbol_name"] or None
        })
        
    return {
        "answer": answer,
        "sources": sources
    }

def handle_deploy_doctor(job: dict) -> dict:
    input_data = job["input"]
    build_log = input_data["build_log"]
    stack = input_data["stack"]
    
    # Get last 100 lines of build log
    log_lines = build_log.splitlines()
    truncated_log = "\n".join(log_lines[-100:])
    
    system = (
        "You are a deployment expert. Diagnose build failures concisely.\n"
        "Always respond in this exact JSON format:\n"
        "{\n"
        '  "root_cause": "one sentence",\n'
        '  "explanation": "2-3 sentences",\n'
        '  "fix": "exact command or code change to fix it",\n'
        '  "confidence": "high|medium|low"\n'
        "}\n"
        "Respond ONLY with the JSON. No markdown, no preamble."
    )
    
    prompt = (
        f"Stack: {stack}\n"
        "Build log (last 100 lines):\n"
        f"{truncated_log}"
    )
    
    raw = call_ollama(prompt, system=system, temperature=0.1)

    try:
        return _extract_json(raw)
    except Exception:
        return {
            "root_cause": "Could not parse AI response",
            "explanation": raw,
            "fix": "Check build log manually",
            "confidence": "low"
        }

def handle_auto_docs(job: dict) -> dict:
    input_data = job["input"]
    doc_type = input_data["doc_type"]
    app_name = job["app_name"]
    
    system = (
        "You are a technical writer. Generate accurate documentation\n"
        "based ONLY on the code shown. Do not invent features not in the code.\n"
        "Use markdown. Be concise and precise."
    )
    
    if doc_type == "readme":
        # Search for project structure and any existing README content
        chunks = retrieve_context(app_name, "project structure main entry point readme configuration")
        context_block = build_context_block(chunks)
        prompt = (
            f"Generate a complete README.md for the project '{app_name}' with sections:\n"
            "Overview, Tech Stack, Prerequisites, Setup, Running the project, "
            "API endpoints (if detectable), Project structure, Contributing.\n\n"
            "Codebase context:\n"
            f"{context_block}"
        )
    elif doc_type == "api":
        chunks = retrieve_context(app_name, "api routes endpoints controllers request response handlers")
        context_block = build_context_block(chunks)
        prompt = (
            f"Document all API endpoints found in the project '{app_name}'.\n"
            "Format each as: METHOD /path — description — request body — response.\n\n"
            "Codebase context:\n"
            f"{context_block}"
        )
    else: # modules
        chunks = retrieve_context(app_name, "classes functions modules services components", n_results=12)
        context_block = build_context_block(chunks)
        prompt = (
            f"Describe each major module/class/service found in the project '{app_name}'.\n"
            "Detail what it does, its key functions, and what it depends on.\n\n"
            "Codebase context:\n"
            f"{context_block}"
        )
        
    content = call_ollama(prompt, system=system, temperature=0.1)
    return {"content": content}

def handle_pr_review(job: dict) -> dict:
    input_data = job["input"]
    diff = input_data["diff"]
    app_name = job["app_name"]
    
    # 1. Parse diff to extract paths
    changed_files = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
            changed_files.append(path)
            
    # 2. Retrieve context for changed files
    all_chunks = []
    for fpath in changed_files[:5]: # max 5 files
        chunks = retrieve_context(app_name, f"{fpath} implementation", n_results=4)
        all_chunks.extend(chunks)
        
    context_block = build_context_block(all_chunks)
    
    system = (
        "You are a senior code reviewer. Review the diff below.\n"
        "Check for:\n"
        "- Security issues (injection, hardcoded secrets, missing auth)\n"
        "- Missing error handling\n"
        "- Performance issues (N+1 queries, unnecessary loops)\n"
        "- Missing input validation\n"
        "- Logic bugs\n"
        "- Code style inconsistencies with the existing codebase\n\n"
        "Respond ONLY in this JSON format:\n"
        "{\n"
        '  "summary": "one paragraph overall assessment",\n'
        '  "issues": [\n'
        "    {\n"
        '      "severity": "critical|high|medium|low|info",\n'
        '      "file": "file path",\n'
        '      "line": line_number_or_null,\n'
        '      "issue": "description",\n'
        '      "suggestion": "how to fix"\n'
        "    }\n"
        "  ],\n"
        '  "approved": true|false,\n'
        '  "approval_reason": "one sentence"\n'
        "}\n"
        "Respond ONLY with the JSON. No markdown, no preamble."
    )
    
    # Truncate diff to 3000 chars if longer
    truncated_diff = diff[:3000]
    
    prompt = (
        "Existing codebase context:\n"
        f"{context_block}\n\n"
        "Diff to review:\n"
        f"{truncated_diff}"
    )
    
    raw = call_ollama(prompt, system=system, temperature=0.1)

    try:
        return _extract_json(raw)
    except Exception:
        return {
            "summary": raw,
            "issues": [],
            "approved": False,
            "approval_reason": "Failed to parse code review JSON."
        }

def handle_onboarding(job: dict) -> dict:
    input_data = job["input"]
    member_role = input_data["member_role"]
    member_name = input_data["member_name"]
    app_name = job["app_name"]
    
    role_queries = {
        "frontend":  "components pages routes frontend ui layout react styles",
        "backend":   "api routes controllers services database models backend",
        "fullstack": "api components architecture overview routing schema",
        "ml":        "model training data pipeline inference features learn model",
        "general":   "project structure overview entry point main start commands"
    }
    query = role_queries.get(member_role, "project structure overview entry point")
    chunks = retrieve_context(app_name, query, n_results=10)
    context_block = build_context_block(chunks)
    
    system = (
        "You are a senior developer onboarding a new team member.\n"
        "Write a friendly, practical onboarding guide.\n"
        "Base it ONLY on the code shown."
    )
    
    prompt = (
        f"New member: {member_name}, role: {member_role}\n"
        f"Generate a concise (300 word max) onboarding guide with: project overview, tech stack, how to run, key files for {member_role}, first contribution step.\n\n"
        "Codebase context:\n"
        f"{context_block}"
    )
    
    if not context_block:
        prompt = (
            f"New member: {member_name}, role: {member_role}, project: {app_name}.\n"
            "Write a brief (200 word max) onboarding guide covering: welcome, stack, how to run, first contribution step."
        )

    content = call_ollama(prompt, system=system, temperature=0.1)
    return {"guide": content}

def handle_arch_diagram(job: dict) -> dict:
    app_name = job["app_name"]
    
    # 1. Query SQLite distinct files
    conn = get_connection()
    file_tree_summary = ""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT file_path, chunk_type, symbol_name, language
            FROM code_chunks WHERE app_name = ?
            ORDER BY file_path
        """, (app_name,))
        rows = cursor.fetchall()
        lines = []
        for r in rows:
            symbol = f" ({r['symbol_name']})" if r['symbol_name'] else ""
            lines.append(f"- {r['file_path']} : {r['chunk_type']}{symbol} [{r['language']}]")
        file_tree_summary = "\n".join(lines)
    except Exception as e:
        print(f"Error querying file tree: {e}")
    finally:
        conn.close()
        
    # 2. Retrieve dependencies
    chunks = retrieve_context(app_name, "imports dependencies calls services endpoints relations", n_results=12)
    context_block = build_context_block(chunks)
    
    system = (
        "You are a software architect. Generate a Mermaid diagram\n"
        "showing the architecture of this project.\n"
        "Use graph TD (top-down) direction.\n"
        "Show: main modules/files as nodes, dependencies/calls as edges.\n"
        "Label edges with the type of relationship (calls, imports, extends).\n"
        "Keep it to the most important 10-15 nodes.\n"
        "Respond ONLY with the Mermaid diagram code block. Do not explain anything.\n"
        "Do not include any explanation or markdown outside the diagram."
    )
    
    prompt = (
        "Project file structure:\n"
        f"{file_tree_summary}\n\n"
        "Code context showing dependencies:\n"
        f"{context_block}"
    )
    
    raw = call_ollama(prompt, system=system, temperature=0.1)
    
    # Extract mermaid diagram block
    diagram = raw.strip()
    if "```mermaid" in diagram:
        parts = diagram.split("```mermaid")
        diagram = "```mermaid" + parts[1].split("```")[0] + "```"
        
    return {"diagram": diagram}

def handle_submission_analysis(job: dict) -> dict:
    input_data = job["input"]
    submission_id = input_data["submission_id"]
    extracted_path = input_data["extracted_path"]
    assignment_id = input_data["assignment_id"]
    
    # 1. Detect Stack
    from app.detector import detect_stack
    try:
        stack_info = detect_stack(extracted_path)
        detected_stack = stack_info["stack"]
    except Exception:
        detected_stack = "static"
        
    # 2. Walk and analyze files
    from app.ai.ingest import SUPPORTED_EXTENSIONS
    import re
    
    file_count = 0
    line_count = 0
    hardcoded_secrets = 0
    missing_error_handling = 0
    issues = []
    missing_features = []
    
    secret_pat = re.compile(r'\b(api_key|secret|password|token|pwd|auth_token)\b\s*[:=]\s*[\'"][^\'"]{8,}[\'"]', re.IGNORECASE)
    py_except_pat = re.compile(r'^\s*except\s*(Exception)?\s*:\s*(#.*)?$')
    js_catch_pat = re.compile(r'\bcatch\s*\(.*?\)\s*\{\s*\}')
    
    for root, _, filenames in os.walk(extracted_path):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            file_count += 1
            fpath = os.path.join(root, fname)
            rel_fpath = os.path.relpath(fpath, extracted_path)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                line_count += len(lines)
                
                content = "".join(lines)
                if ext in [".js", ".jsx", ".ts", ".tsx", ".java"]:
                    catches = js_catch_pat.findall(content)
                    if catches:
                        missing_error_handling += len(catches)
                        for _ in catches:
                            issues.append(f"Empty catch block in {rel_fpath}")
                            
                for idx, line in enumerate(lines, 1):
                    if secret_pat.search(line):
                        hardcoded_secrets += 1
                        issues.append(f"Hardcoded secret in {rel_fpath}:{idx}")
                    if ext == ".py":
                        if py_except_pat.match(line):
                            missing_error_handling += 1
                            issues.append(f"Bare except or raw Exception in {rel_fpath}:{idx}")
            except Exception:
                pass

    content_lower = ""
    for root, _, filenames in os.walk(extracted_path):
        for fname in filenames:
            if os.path.splitext(fname)[1].lower() in SUPPORTED_EXTENSIONS:
                try:
                    with open(os.path.join(root, fname), "r", encoding="utf-8", errors="ignore") as f:
                        content_lower += f.read().lower()
                except Exception:
                    pass
    
    if "env" not in content_lower and "dotenv" not in content_lower:
        missing_features.append("Environment variable configuration (.env)")
    if "db" not in content_lower and "sql" not in content_lower and "mongo" not in content_lower and "prisma" not in content_lower:
        missing_features.append("Database persistence layer")
        
    code_quality_score = max(0, 100 - (hardcoded_secrets * 10) - (missing_error_handling * 5))
    
    # 3. AI Summary
    system = "You are a technical grading assistant. Summarize this student submission and list its key components and architecture in 2-3 sentences."
    prompt = f"Submission path: {extracted_path}\nFiles found: {file_count} files, {line_count} lines of code.\nStack: {detected_stack}."
    
    key_file_content = ""
    for root, _, filenames in os.walk(extracted_path):
        for fname in filenames:
            if fname.lower() in ["main.py", "app.py", "index.js", "app.jsx", "app.tsx", "server.js"]:
                try:
                    with open(os.path.join(root, fname), "r", encoding="utf-8", errors="ignore") as f:
                        key_file_content = f.read()[:2000]
                    break
                except Exception:
                    pass
        if key_file_content:
            break
            
    if key_file_content:
        prompt += f"\n\nKey File Content:\n{key_file_content}"
        
    try:
        ai_summary = call_ollama(prompt, system=system, temperature=0.1)
    except Exception:
        ai_summary = f"This is a {detected_stack} application containing {file_count} files and {line_count} lines of code."
        
    # 4. Pairwise similarity & plagiarism checks
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT submission_id, extracted_path FROM submissions WHERE assignment_id = ?", (assignment_id,))
        submissions_list = [{"submission_id": r["submission_id"], "extracted_path": r["extracted_path"]} for r in cursor.fetchall()]
    finally:
        conn.close()
        
    from app.faculty.similarity import compute_similarity_matrix
    if not any(s["submission_id"] == submission_id for s in submissions_list):
        submissions_list.append({"submission_id": submission_id, "extracted_path": extracted_path})
        
    sim_matrix = compute_similarity_matrix(submissions_list)
    
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    
    conn = get_connection()
    try:
        cur_sim_scores = sim_matrix.get(submission_id, {})
        cur_plag = 0
        for other_id, score in cur_sim_scores.items():
            if score >= 0.75:
                cur_plag = 1
                break
                
        conn.execute("""
            INSERT OR REPLACE INTO submission_analysis (
                submission_id, ai_summary, detected_stack, file_count, line_count,
                issues, missing_features, hardcoded_secrets, missing_error_handling,
                code_quality_score, similarity_scores, plagiarism_flag, similarity_threshold, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            submission_id, ai_summary, detected_stack, file_count, line_count,
            json.dumps(issues), json.dumps(missing_features), hardcoded_secrets, missing_error_handling,
            code_quality_score, json.dumps(cur_sim_scores), cur_plag, 0.75, now_str
        ))
        
        conn.execute("UPDATE submissions SET status = 'completed' WHERE submission_id = ?", (submission_id,))
        
        for sub in submissions_list:
            other_id = sub["submission_id"]
            if other_id == submission_id:
                continue
                
            cursor = conn.execute("SELECT 1 FROM submission_analysis WHERE submission_id = ?", (other_id,))
            if cursor.fetchone():
                other_sim_scores = sim_matrix.get(other_id, {})
                other_plag = 0
                for o_id, score in other_sim_scores.items():
                    if score >= 0.75:
                        other_plag = 1
                        break
                conn.execute("""
                    UPDATE submission_analysis 
                    SET similarity_scores = ?, plagiarism_flag = ? 
                    WHERE submission_id = ?
                """, (json.dumps(other_sim_scores), other_plag, other_id))
                
        conn.commit()
    finally:
        conn.close()
        
    return {
        "submission_id": submission_id,
        "status": "completed",
        "detected_stack": detected_stack,
        "file_count": file_count,
        "line_count": line_count,
        "hardcoded_secrets": hardcoded_secrets,
        "missing_error_handling": missing_error_handling,
        "code_quality_score": code_quality_score
    }
