"""AI-powered DSA question generator.
Given a problem title + description, generates:
  - Structured test cases (input/expected as JSON)
  - Hints (3 progressive)
  - Editorial (approach explanation)
  - Starter code for Python, JS, Java, C++, Go
  - Suggested category, difficulty, tags, constraints
"""
import json
import re


def _extract_json_block(text: str) -> dict | list | None:
    """Pull first JSON block from LLM output."""
    # Try ```json ... ``` block first
    m = re.search(r'```json\s*([\s\S]+?)```', text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try raw JSON object/array
    m = re.search(r'(\{[\s\S]+\}|\[[\s\S]+\])', text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


SYSTEM_PROMPT = """You are an expert competitive programming problem setter.
Your job is to generate structured metadata for a DSA problem given its title and description.
Always output valid JSON only — no prose outside the JSON block.
Use the exact schema provided."""


def generate_question_metadata(title: str, description: str, difficulty: str = "Medium") -> dict:
    """Call LLM to auto-generate test cases, hints, editorial, and starter code."""
    from app.ai.worker import call_llm

    prompt = f"""Generate complete metadata for this DSA problem.

Title: {title}
Description: {description}
Difficulty: {difficulty}

Output a single JSON object with this EXACT schema:
{{
  "category": "<Arrays|Strings|DP|Graph|Trees|Sorting|Math|Searching|Linked Lists|Stack/Queue|Greedy|Backtracking>",
  "tags": ["<tag1>", "<tag2>"],
  "constraints": "<e.g. 1 <= n <= 10^5>",
  "examples": [
    {{"input": "<human readable input>", "output": "<human readable output>", "explanation": "<why>"}},
    {{"input": "<second example>", "output": "<second output>"}}
  ],
  "test_cases": [
    {{"input": [<arg1>, <arg2>], "expected": <expected_return_value>, "is_hidden": false}},
    {{"input": [<arg1>, <arg2>], "expected": <expected_return_value>, "is_hidden": false}},
    {{"input": [<arg1>, <arg2>], "expected": <expected_return_value>, "is_hidden": false}},
    {{"input": [<edge_case>], "expected": <expected>, "is_hidden": true}},
    {{"input": [<edge_case>], "expected": <expected>, "is_hidden": true}}
  ],
  "hints": [
    "<first hint — vague, points to the right category of approach>",
    "<second hint — more specific, mentions data structure or technique>",
    "<third hint — almost gives the algorithm away>"
  ],
  "editorial": "<2-3 paragraph solution explanation with time and space complexity>",
  "starter_code_python": "def solve(<params>):\\n    # your code here\\n    pass\\n",
  "starter_code_js": "function solve(<params>) {{\\n  // your code here\\n}}\\n",
  "starter_code_ts": "function solve(<params>: <types>): <returnType> {{\\n  \\n}}\\n",
  "starter_code_java": "static Object solve(Object... args) {{\\n    // your code here\\n    return null;\\n}}",
  "starter_code_cpp": "auto solve(auto&&... args) {{\\n    // your code here\\n    return 0;\\n}}",
  "starter_code_go": "func solve(args ...interface{{}}) interface{{}} {{\\n    // your code here\\n    return nil\\n}}"
}}

IMPORTANT:
- test_cases.input must be a JSON array of arguments (not a string)
- test_cases.expected must be the actual return value (not a string)
- Include at least 3 visible and 2 hidden test cases
- Make test cases cover edge cases: empty input, single element, large values, duplicates
- The solve() function receives the same args as listed in test_cases.input"""

    raw = call_llm(prompt, system=SYSTEM_PROMPT, temperature=0.2)
    result = _extract_json_block(raw)

    if not result or not isinstance(result, dict):
        raise ValueError(f"AI returned invalid JSON. Raw output:\n{raw[:500]}")

    # Validate required fields
    required = ["test_cases", "hints", "editorial", "starter_code_python", "starter_code_js"]
    missing = [k for k in required if k not in result]
    if missing:
        raise ValueError(f"AI response missing fields: {missing}")

    # Ensure test_cases have correct structure
    valid_tcs = []
    for tc in result.get("test_cases", []):
        if not isinstance(tc.get("input"), list):
            continue  # skip malformed
        valid_tcs.append({
            "input": tc["input"],
            "expected": tc.get("expected"),
            "is_hidden": bool(tc.get("is_hidden", False)),
        })
    result["test_cases"] = valid_tcs

    return result


def auto_generate_test_cases_only(slug: str, description: str, existing_code_python: str = "") -> list:
    """Given a slug and description, generate just test cases — for adding to an existing question."""
    from app.ai.worker import call_llm
    from app.dsa.service import get_question

    q = get_question(slug)
    desc_text = description or (q["description"] if q else "")
    existing_tests = q.get("test_cases", []) if q else []

    prompt = f"""Generate 5 additional test cases for this DSA problem.

Problem description: {desc_text}

Existing test cases (do NOT duplicate these): {json.dumps(existing_tests[:3])}

Output a JSON array of test case objects:
[
  {{"input": [<arg1>, <arg2>], "expected": <return_value>, "is_hidden": false}},
  ...
]

Rules:
- input must be a JSON array of function arguments
- expected must be the actual return value
- Cover edge cases: empty, single element, all same, negatives, large values
- Generate exactly 5 test cases, mix of visible (is_hidden: false) and hidden (is_hidden: true)"""

    raw = call_llm(prompt, system=SYSTEM_PROMPT, temperature=0.3)
    result = _extract_json_block(raw)

    if not isinstance(result, list):
        raise ValueError(f"Expected a JSON array. Got: {raw[:300]}")

    valid = []
    for tc in result:
        if isinstance(tc.get("input"), list):
            valid.append({
                "input": tc["input"],
                "expected": tc.get("expected"),
                "is_hidden": bool(tc.get("is_hidden", False)),
            })
    return valid
