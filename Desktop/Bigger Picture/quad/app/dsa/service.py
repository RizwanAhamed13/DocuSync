import datetime
import json
import os
import re
import shutil
import subprocess
import tempfile
from app.db import get_connection

# ── Language registry ────────────────────────────────────────────────────────

SUPPORTED_LANGUAGES = {
    "python":     {"ext": ".py",   "runtime": "python3"},
    "py":         {"ext": ".py",   "runtime": "python3"},
    "javascript": {"ext": ".js",   "runtime": "node"},
    "js":         {"ext": ".js",   "runtime": "node"},
    "typescript": {"ext": ".ts",   "runtime": "ts-node"},
    "ts":         {"ext": ".ts",   "runtime": "ts-node"},
    "java":       {"ext": ".java", "runtime": "java"},
    "cpp":        {"ext": ".cpp",  "runtime": "g++"},
    "c++":        {"ext": ".cpp",  "runtime": "g++"},
    "go":         {"ext": ".go",   "runtime": "go"},
}

LANG_STARTERS = {
    "python":     "starter_code_python",
    "javascript": "starter_code_js",
    "typescript": "starter_code_ts",
    "java":       "starter_code_java",
    "cpp":        "starter_code_cpp",
    "go":         "starter_code_go",
}

VALID_DIFFICULTIES = {"Easy", "Medium", "Hard"}

# ── Harness builders ─────────────────────────────────────────────────────────

def _python_harness(user_code: str, test_inputs) -> str:
    return (
        user_code
        + "\n\nimport json\n"
        + "__cases = " + json.dumps(test_inputs) + "\n"
        + "__out = []\n"
        + "for __args in __cases:\n"
        + "    __out.append(solve(*__args))\n"
        + "print(json.dumps(__out))\n"
    )


def _js_harness(user_code: str, test_inputs) -> str:
    return (
        user_code
        + "\n\nconst __cases = " + json.dumps(test_inputs) + ";\n"
        + "const __out = __cases.map((a) => solve(...a));\n"
        + "console.log(JSON.stringify(__out));\n"
    )


def _ts_harness(user_code: str, test_inputs) -> str:
    return (
        user_code
        + "\n\nconst __cases: any[] = " + json.dumps(test_inputs) + ";\n"
        + "const __out: any[] = __cases.map((a: any[]) => solve(...a));\n"
        + "console.log(JSON.stringify(__out));\n"
    )


def _ts_to_js_harness(user_code: str, test_inputs) -> str:
    """Fallback: strip TS annotations and generate plain JS harness."""
    import re as _re
    # Strip type annotations: `: Type`, `<T>`, `as Type`
    js_code = _re.sub(r':\s*[A-Za-z\[\]|<>{}]+(?=\s*[,)=\n])', '', user_code)
    js_code = _re.sub(r'\bas\s+\w+', '', js_code)
    js_code = _re.sub(r'<[^>]+>', '', js_code)
    return (
        js_code
        + "\n\nconst __cases = " + json.dumps(test_inputs) + ";\n"
        + "const __out = __cases.map((a) => solve(...a));\n"
        + "console.log(JSON.stringify(__out));\n"
    )


def _java_harness(user_code: str, test_inputs) -> str:
    """Generate a self-contained Java harness using only stdlib (no Gson).
    Args are passed as List<Object> where nested lists are int[] for convenience."""
    cases_escaped = json.dumps(test_inputs).replace("\\", "\\\\").replace('"', '\\"')
    return f"""import java.util.*;
import java.io.*;

public class Solution {{
    // ─── User code ───────────────────────────────────────────────────────
    {user_code}

    // ─── Helpers available to user code ──────────────────────────────────
    static int[] toIntArray(Object o) {{
        if (o instanceof int[]) return (int[]) o;
        @SuppressWarnings("unchecked") List<Object> list = (List<Object>) o;
        int[] arr = new int[list.size()];
        for (int i = 0; i < list.size(); i++) arr[i] = ((Number) list.get(i)).intValue();
        return arr;
    }}
    static int[][] toInt2DArray(Object o) {{
        @SuppressWarnings("unchecked") List<Object> outer = (List<Object>) o;
        int[][] arr = new int[outer.size()][];
        for (int i = 0; i < outer.size(); i++) arr[i] = toIntArray(outer.get(i));
        return arr;
    }}
    static int toInt(Object o) {{ return ((Number) o).intValue(); }}
    static long toLong(Object o) {{ return ((Number) o).longValue(); }}
    static String toStr(Object o) {{ return o == null ? null : o.toString(); }}

    // ─── Mini JSON parser (stdlib only) ──────────────────────────────────
    static Object parseJson(String s) {{
        s = s.trim();
        if (s.startsWith("[")) {{
            List<Object> list = new ArrayList<>();
            String inner = s.substring(1, s.length() - 1).trim();
            if (inner.isEmpty()) return list;
            for (String tok : splitJson(inner)) list.add(parseJson(tok.trim()));
            return list;
        }}
        if (s.startsWith("{{")) return s;
        if (s.startsWith("\\"")) return s.substring(1, s.length() - 1);
        if (s.equals("true")) return Boolean.TRUE;
        if (s.equals("false")) return Boolean.FALSE;
        if (s.equals("null")) return null;
        try {{ return Long.parseLong(s); }} catch (NumberFormatException e) {{}}
        try {{ return Double.parseDouble(s); }} catch (NumberFormatException e) {{}}
        return s;
    }}

    static List<String> splitJson(String s) {{
        List<String> parts = new ArrayList<>();
        int depth = 0; int start = 0; boolean inStr = false;
        for (int i = 0; i < s.length(); i++) {{
            char c = s.charAt(i);
            if (c == '"' && (i == 0 || s.charAt(i-1) != '\\\\')) inStr = !inStr;
            if (!inStr) {{
                if (c == '[' || c == '{{') depth++;
                else if (c == ']' || c == '}}') depth--;
                else if (c == ',' && depth == 0) {{
                    parts.add(s.substring(start, i));
                    start = i + 1;
                }}
            }}
        }}
        parts.add(s.substring(start));
        return parts;
    }}

    @SuppressWarnings("unchecked")
    public static void main(String[] argv) throws Exception {{
        String casesJson = "{cases_escaped}";
        List<Object> cases = (List<Object>) parseJson(casesJson);
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < cases.size(); i++) {{
            List<Object> args = (List<Object>) cases.get(i);
            Object result;
            try {{
                result = solve(args.toArray());
            }} catch (Exception e) {{
                result = "__ERR__" + e.getMessage();
            }}
            sb.append(toJson(result));
            if (i < cases.size() - 1) sb.append(",");
        }}
        sb.append("]");
        System.out.println(sb);
    }}

    static String toJson(Object o) {{
        if (o == null) return "null";
        if (o instanceof Boolean) return o.toString();
        if (o instanceof Number) {{
            if (o instanceof Double) {{
                double d = (Double) o;
                if (d == Math.floor(d) && !Double.isInfinite(d)) return String.valueOf((long)d);
            }}
            return o.toString();
        }}
        if (o instanceof String) {{
            String s = (String) o;
            if (s.startsWith("__ERR__")) return "\\"ERROR: " + s.substring(7).replace("\\"","'") + "\\"";
            return "\\"" + s.replace("\\\\","\\\\\\\\").replace("\\"","\\\\\\"") + "\\"";
        }}
        if (o instanceof List) {{
            @SuppressWarnings("unchecked") List<Object> list = (List<Object>) o;
            StringBuilder sb = new StringBuilder("[");
            for (int i = 0; i < list.size(); i++) {{
                sb.append(toJson(list.get(i)));
                if (i < list.size()-1) sb.append(",");
            }}
            return sb.append("]").toString();
        }}
        if (o instanceof int[]) {{
            int[] a = (int[]) o;
            StringBuilder sb = new StringBuilder("[");
            for (int i = 0; i < a.length; i++) {{ sb.append(a[i]); if(i<a.length-1)sb.append(","); }}
            return sb.append("]").toString();
        }}
        if (o instanceof long[]) {{
            long[] a = (long[]) o;
            StringBuilder sb = new StringBuilder("[");
            for (int i = 0; i < a.length; i++) {{ sb.append(a[i]); if(i<a.length-1)sb.append(","); }}
            return sb.append("]").toString();
        }}
        if (o instanceof int[][]) {{
            int[][] a = (int[][]) o;
            StringBuilder sb = new StringBuilder("[");
            for (int i = 0; i < a.length; i++) {{
                sb.append(toJson(a[i]));
                if(i<a.length-1) sb.append(",");
            }}
            return sb.append("]").toString();
        }}
        return "\\"" + o.toString().replace("\\"","'") + "\\"";
    }}
}}"""


def _cpp_harness(user_code: str, test_inputs) -> str:
    """C++ harness using only standard headers — works on macOS clang and g++."""
    cases_json = json.dumps(test_inputs).replace('\\', '\\\\').replace('"', '\\"')
    return f"""#include <iostream>
#include <vector>
#include <string>
#include <sstream>
#include <map>
#include <unordered_map>
#include <set>
#include <unordered_set>
#include <algorithm>
#include <numeric>
#include <stack>
#include <queue>
#include <climits>
#include <cmath>
#include <functional>
using namespace std;

// ── Minimal JSON value type ───────────────────────────────────────────────────
struct JVal {{
    enum Type {{ NUL, BOOL, INT, DBL, STR, ARR }} type;
    bool b; long long i; double d; string s;
    vector<JVal> a;
    JVal() : type(NUL), b(false), i(0), d(0) {{}}
    JVal(bool v) : type(BOOL), b(v), i(0), d(0) {{}}
    JVal(long long v) : type(INT), b(false), i(v), d(0) {{}}
    JVal(double v) : type(DBL), b(false), i(0), d(v) {{}}
    JVal(const string& v) : type(STR), b(false), i(0), d(0), s(v) {{}}
    JVal(vector<JVal> v) : type(ARR), b(false), i(0), d(0), a(std::move(v)) {{}}
    int asInt() const {{ return (int)i; }}
    long long asLL() const {{ return i; }}
    double asDbl() const {{ return d; }}
    string asStr() const {{ return s; }}
    vector<int> asIntVec() const {{
        vector<int> r; for (auto& x : a) r.push_back((int)x.i); return r;
    }}
    vector<vector<int>> asInt2DVec() const {{
        vector<vector<int>> r; for (auto& x : a) r.push_back(x.asIntVec()); return r;
    }}
    vector<string> asStrVec() const {{
        vector<string> r; for (auto& x : a) r.push_back(x.s); return r;
    }}
    JVal& operator[](int idx) {{ return a[idx]; }}
    size_t size() const {{ return a.size(); }}
}};

static JVal parseVal(const string& s, size_t& p);
static void skip(const string& s, size_t& p) {{
    while (p < s.size() && isspace(s[p])) p++;
}}
static vector<JVal> parseArr(const string& s, size_t& p) {{
    vector<JVal> v; p++; // skip [
    skip(s, p);
    if (p < s.size() && s[p] == ']') {{ p++; return v; }}
    while (true) {{
        v.push_back(parseVal(s, p)); skip(s, p);
        if (p < s.size() && s[p] == ',') {{ p++; skip(s, p); }} else {{ p++; break; }}
    }}
    return v;
}}
static JVal parseVal(const string& s, size_t& p) {{
    skip(s, p);
    if (s[p] == '[') return JVal(parseArr(s, p));
    if (s[p] == '"') {{
        string r; p++;
        while (p < s.size() && s[p] != '"') {{ if (s[p]=='\\\\') p++; r += s[p++]; }}
        p++; return JVal(r);
    }}
    if (s.substr(p,4) == "true")  {{ p+=4; return JVal(true); }}
    if (s.substr(p,5) == "false") {{ p+=5; return JVal(false); }}
    if (s.substr(p,4) == "null")  {{ p+=4; return JVal(); }}
    bool neg = s[p] == '-'; if (neg) p++;
    long long iv = 0; bool hasDot = false;
    size_t start = p;
    while (p < s.size() && (isdigit(s[p]) || s[p] == '.' || s[p] == 'e' || s[p] == 'E' || s[p] == '+' || s[p] == '-')) {{
        if (s[p] == '.' || s[p] == 'e' || s[p] == 'E') hasDot = true;
        p++;
    }}
    string num = (neg?"-":"") + s.substr(start, p-start);
    if (hasDot) return JVal(stod(num));
    return JVal(stoll(num));
}}
static JVal parseJson(const string& s) {{ size_t p=0; return parseVal(s,p); }}

static string toJsonStr(long long v) {{ return to_string(v); }}
static string toJsonStr(int v) {{ return to_string(v); }}
static string toJsonStr(double v) {{
    ostringstream os; os << v; return os.str();
}}
static string toJsonStr(bool v) {{ return v ? "true" : "false"; }}
static string toJsonStr(const string& v) {{ return "\\"" + v + "\\""; }}
static string toJsonStr(const vector<int>& v) {{
    string r="["; for (int i=0;i<(int)v.size();i++) {{ if(i)r+=","; r+=to_string(v[i]); }} return r+"]";
}}
static string toJsonStr(const vector<long long>& v) {{
    string r="["; for (int i=0;i<(int)v.size();i++) {{ if(i)r+=","; r+=to_string(v[i]); }} return r+"]";
}}
static string toJsonStr(const vector<vector<int>>& v) {{
    string r="["; for (int i=0;i<(int)v.size();i++) {{ if(i)r+=","; r+=toJsonStr(v[i]); }} return r+"]";
}}
static string toJsonStr(const vector<string>& v) {{
    string r="["; for (int i=0;i<(int)v.size();i++) {{ if(i)r+=","; r+="\\""+v[i]+"\\""; }} return r+"]";
}}
static string toJsonStr(const JVal& v) {{
    if (v.type==JVal::NUL) return "null";
    if (v.type==JVal::BOOL) return v.b?"true":"false";
    if (v.type==JVal::INT) return to_string(v.i);
    if (v.type==JVal::DBL) {{ ostringstream os; os<<v.d; return os.str(); }}
    if (v.type==JVal::STR) return "\\""+v.s+"\\"";
    string r="["; for (int i=0;i<(int)v.a.size();i++) {{ if(i)r+=","; r+=toJsonStr(v.a[i]); }} return r+"]";
}}

// ── User code ─────────────────────────────────────────────────────────────────
{user_code}

int main() {{
    string casesStr = "{cases_json}";
    JVal cases = parseJson(casesStr);
    cout << "[";
    for (int i = 0; i < (int)cases.size(); i++) {{
        if (i) cout << ",";
        auto result = solve(cases[i]);
        cout << toJsonStr(result);
    }}
    cout << "]" << endl;
    return 0;
}}"""


def _go_harness(user_code: str, test_inputs) -> str:
    cases_json = json.dumps(test_inputs)
    return f"""package main

import (
    "encoding/json"
    "fmt"
)

{user_code}

func main() {{
    var cases [][]interface{{}}
    json.Unmarshal([]byte(`{cases_json}`), &cases)
    out := make([]interface{{}}, len(cases))
    for i, c := range cases {{
        out[i] = solve(c...)
    }}
    b, _ := json.Marshal(out)
    fmt.Println(string(b))
}}"""


# ── Execution ─────────────────────────────────────────────────────────────────

def _run_file(path: str, language: str, timeout: int = 10) -> tuple[str, str, int]:
    """Returns (stdout, stderr, returncode)."""
    if language in ("python", "py"):
        cmd = ["python3", path]
    elif language in ("javascript", "js"):
        node = shutil.which("node") or shutil.which("nodejs")
        if not node:
            return "", "Node.js not installed", 1
        cmd = [node, path]
    elif language in ("typescript", "ts"):
        tsx = shutil.which("tsx") or shutil.which("ts-node")
        node = shutil.which("node") or shutil.which("nodejs")
        npx = shutil.which("npx")
        if tsx:
            cmd = [tsx, path]
        elif npx:
            cmd = [npx, "tsx", path]
        else:
            return "", "TypeScript runtime not available (install tsx: npm i -g tsx)", 1
    elif language in ("java",):
        # Compile then run
        javac = shutil.which("javac")
        java = shutil.which("java")
        if not javac or not java:
            return "", "Java (javac/java) not installed", 1
        dir_ = os.path.dirname(path)
        r = subprocess.run([javac, path], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return "", r.stderr[:2000], r.returncode
        cmd = [java, "-cp", dir_, "Solution"]
    elif language in ("cpp", "c++"):
        gpp = shutil.which("g++")
        if not gpp:
            return "", "g++ not installed", 1
        out_bin = path.replace(".cpp", "")
        r = subprocess.run([gpp, "-O2", "-o", out_bin, path], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return "", r.stderr[:2000], r.returncode
        cmd = [out_bin]
    elif language in ("go",):
        go = shutil.which("go")
        if not go:
            return "", "Go not installed", 1
        cmd = [go, "run", path]
    else:
        return "", f"Unsupported language: {language}", 1

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        return "", "Execution timed out (10s)", 1


def _check_runtime(language: str) -> str | None:
    """Return error message if runtime unavailable, else None."""
    lang = language.lower()
    if lang in ("python", "py"):
        return None if shutil.which("python3") else "python3 not found"
    if lang in ("javascript", "js"):
        return None if (shutil.which("node") or shutil.which("nodejs")) else "Node.js not installed"
    if lang in ("typescript", "ts"):
        if shutil.which("tsx") or shutil.which("ts-node") or shutil.which("npx"):
            return None
        return "TypeScript runtime not installed (need tsx, ts-node, or npx)"
    if lang in ("java",):
        return None if shutil.which("java") else "Java runtime not installed"
    if lang in ("cpp", "c++"):
        return None if shutil.which("g++") else "g++ compiler not installed"
    if lang in ("go",):
        return None if shutil.which("go") else "Go not installed"
    return f"Unsupported language: {language}"


# ── Question CRUD ─────────────────────────────────────────────────────────────

def list_questions(category: str | None = None, difficulty: str | None = None):
    conn = get_connection()
    try:
        query = "SELECT slug, title, difficulty, category, tags FROM dsa_questions"
        conditions, params = [], []
        if category and category != "All":
            conditions.append("category = ?")
            params.append(category)
        if difficulty and difficulty != "All":
            conditions.append("difficulty = ?")
            params.append(difficulty)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id ASC"
        cursor = conn.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            r["tags"] = json.loads(r["tags"]) if r.get("tags") else []
        return rows
    finally:
        conn.close()


def get_question(slug: str):
    conn = get_connection()
    try:
        cursor = conn.execute("SELECT * FROM dsa_questions WHERE slug = ?", (slug,))
        row = cursor.fetchone()
        if not row:
            return None
        q = dict(row)
        q["examples"] = json.loads(q["examples"]) if q["examples"] else []
        q["tags"] = json.loads(q.get("tags") or "[]")
        q["hints"] = json.loads(q.get("hints") or "[]")
        q["editorial"] = q.get("editorial") or ""
        cursor = conn.execute(
            "SELECT input, expected_output, order_index FROM dsa_test_cases "
            "WHERE question_slug = ? AND is_hidden = 0 ORDER BY order_index ASC",
            (slug,),
        )
        q["test_cases"] = [
            {"input": json.loads(r["input"]), "expected_output": json.loads(r["expected_output"])}
            for r in cursor.fetchall()
        ]
        return q
    finally:
        conn.close()


def create_question(data: dict) -> dict:
    slug = data["slug"].strip().lower()
    if not re.match(r'^[a-z0-9-]+$', slug):
        raise ValueError("slug must be lowercase letters, digits, and hyphens only")
    title = data["title"].strip()
    if not title:
        raise ValueError("title is required")
    difficulty = data["difficulty"]
    if difficulty not in VALID_DIFFICULTIES:
        raise ValueError(f"difficulty must be one of {sorted(VALID_DIFFICULTIES)}")
    category = data["category"].strip()
    if not category:
        raise ValueError("category is required")
    description = data.get("description", "").strip()
    constraints = data.get("constraints", "").strip()
    examples = data.get("examples", [])
    tags = data.get("tags", [])
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO dsa_questions
               (slug, title, difficulty, category, description, examples, constraints,
                starter_code_python, starter_code_js, starter_code_java,
                starter_code_cpp, starter_code_go, starter_code_ts, tags,
                hints, editorial, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                slug, title, difficulty, category, description,
                json.dumps(examples), constraints,
                data.get("starter_code_python", "def solve(*args):\n    pass\n"),
                data.get("starter_code_js", "function solve(...args) {\n  \n}\n"),
                data.get("starter_code_java", "static Object solve(Object... args) {\n    return null;\n}"),
                data.get("starter_code_cpp", "auto solve(auto&&... args) {\n    return 0;\n}"),
                data.get("starter_code_go", "func solve(args ...interface{}) interface{} {\n    return nil\n}"),
                data.get("starter_code_ts", "function solve(...args: any[]): any {\n  \n}\n"),
                json.dumps(tags),
                json.dumps(data.get("hints", [])),
                data.get("editorial", ""),
                now,
            ),
        )
        # Insert test cases if provided
        for i, tc in enumerate(data.get("test_cases", [])):
            conn.execute(
                "INSERT INTO dsa_test_cases (question_slug, input, expected_output, is_hidden, order_index) VALUES (?,?,?,?,?)",
                (slug, json.dumps(tc["input"]), json.dumps(tc["expected"]), int(tc.get("is_hidden", False)), i),
            )
        conn.commit()
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise ValueError(f"Question with slug '{slug}' already exists")
        raise
    finally:
        conn.close()

    return get_question(slug)


def update_question(slug: str, data: dict) -> dict:
    existing = get_question(slug)
    if not existing:
        raise ValueError("Question not found")

    allowed_fields = {
        "title", "difficulty", "category", "description", "constraints", "examples", "tags",
        "starter_code_python", "starter_code_js", "starter_code_java",
        "starter_code_cpp", "starter_code_go", "starter_code_ts",
        "hints", "editorial",
    }
    updates, params = [], []
    for k, v in data.items():
        if k not in allowed_fields:
            continue
        if k == "difficulty" and v not in VALID_DIFFICULTIES:
            raise ValueError(f"difficulty must be one of {sorted(VALID_DIFFICULTIES)}")
        if k in ("examples", "tags", "hints"):
            v = json.dumps(v)
        updates.append(f"{k} = ?")
        params.append(v)

    if not updates:
        return existing

    params.append(slug)
    conn = get_connection()
    try:
        conn.execute(f"UPDATE dsa_questions SET {', '.join(updates)} WHERE slug = ?", params)
        conn.commit()
    finally:
        conn.close()
    return get_question(slug)


def delete_question(slug: str) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM dsa_test_cases WHERE question_slug = ?", (slug,))
        conn.execute("DELETE FROM dsa_questions WHERE slug = ?", (slug,))
        conn.commit()
    finally:
        conn.close()


def add_test_case(slug: str, input_val: list, expected_val, is_hidden: bool = False) -> dict:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT COALESCE(MAX(order_index), -1) + 1 FROM dsa_test_cases WHERE question_slug = ?", (slug,)
        )
        next_idx = cursor.fetchone()[0]
        conn.execute(
            "INSERT INTO dsa_test_cases (question_slug, input, expected_output, is_hidden, order_index) VALUES (?,?,?,?,?)",
            (slug, json.dumps(input_val), json.dumps(expected_val), int(is_hidden), next_idx),
        )
        conn.commit()
        cursor = conn.execute(
            "SELECT id, input, expected_output, is_hidden, order_index FROM dsa_test_cases WHERE question_slug = ? ORDER BY order_index DESC LIMIT 1",
            (slug,)
        )
        row = dict(cursor.fetchone())
        row["input"] = json.loads(row["input"])
        row["expected_output"] = json.loads(row["expected_output"])
        return row
    finally:
        conn.close()


def delete_test_case(test_case_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM dsa_test_cases WHERE id = ?", (test_case_id,))
        conn.commit()
    finally:
        conn.close()


def list_test_cases(slug: str, include_hidden: bool = True) -> list:
    conn = get_connection()
    try:
        q = "SELECT id, input, expected_output, is_hidden, order_index FROM dsa_test_cases WHERE question_slug = ?"
        if not include_hidden:
            q += " AND is_hidden = 0"
        q += " ORDER BY order_index ASC"
        rows = [dict(r) for r in conn.execute(q, (slug,)).fetchall()]
        for r in rows:
            r["input"] = json.loads(r["input"])
            r["expected_output"] = json.loads(r["expected_output"])
        return rows
    finally:
        conn.close()


# ── Code runner ───────────────────────────────────────────────────────────────

def get_all_test_cases(slug: str):
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT input, expected_output FROM dsa_test_cases "
            "WHERE question_slug = ? ORDER BY order_index ASC",
            (slug,),
        )
        return [
            {"input": json.loads(r["input"]), "expected": json.loads(r["expected_output"])}
            for r in cursor.fetchall()
        ]
    finally:
        conn.close()


def run_code(slug: str, code: str, language: str) -> dict:
    lang = (language or "python").lower()

    runtime_err = _check_runtime(lang)
    if runtime_err:
        return {"passed": 0, "total": 0, "results": [], "error": runtime_err}

    cases = get_all_test_cases(slug)
    if not cases:
        return {"passed": 0, "total": 0, "results": [], "error": "Question not found or has no test cases"}

    inputs = [c["input"] for c in cases]

    if lang in ("python", "py"):
        src = _python_harness(code, inputs)
        suffix = ".py"
    elif lang in ("javascript", "js"):
        src = _js_harness(code, inputs)
        suffix = ".js"
    elif lang in ("typescript", "ts"):
        src = _ts_harness(code, inputs)
        suffix = ".ts"
    elif lang in ("java",):
        src = _java_harness(code, inputs)
        suffix = ".java"
    elif lang in ("cpp", "c++"):
        src = _cpp_harness(code, inputs)
        suffix = ".cpp"
    elif lang in ("go",):
        src = _go_harness(code, inputs)
        suffix = ".go"
    else:
        return {"passed": 0, "total": len(cases), "results": [], "error": f"Unsupported language: {language}"}

    # Java class must be named Solution, file must match
    if lang == "java":
        fd, path = tempfile.mkstemp(suffix="_Solution.java", dir=tempfile.gettempdir())
        path = os.path.join(os.path.dirname(path), "Solution.java")
        with open(path, "w") as f:
            f.write(src)
        os.close(fd)
    else:
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "w") as f:
            f.write(src)

    try:
        stdout, stderr, returncode = _run_file(path, lang)

        if returncode != 0:
            return {
                "passed": 0, "total": len(cases), "results": [],
                "error": (stderr or "Runtime error").strip()[:2000],
            }

        try:
            lines = [l for l in stdout.strip().splitlines() if l.strip()]
            actuals = json.loads(lines[-1])
        except (json.JSONDecodeError, IndexError):
            return {
                "passed": 0, "total": len(cases), "results": [],
                "error": "Could not parse output: " + stdout[:500],
            }

        results, passed = [], 0
        for i, c in enumerate(cases):
            actual = actuals[i] if i < len(actuals) else None
            ok = actual == c["expected"]
            if ok:
                passed += 1
            results.append({"input": c["input"], "expected": c["expected"], "actual": actual, "passed": ok})

        return {"passed": passed, "total": len(cases), "results": results, "language": lang}
    finally:
        for p in [path, path.replace(".java", ".class"), path.replace(".cpp", ""), path.replace(".ts", ".js")]:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass


# ── Submission / stats / leaderboard (unchanged logic) ───────────────────────

def log_submission(username: str, problem_slug: str, problem_title: str, difficulty: str, notes: str = None) -> dict:
    if difficulty not in VALID_DIFFICULTIES:
        raise ValueError("Difficulty must be Easy, Medium, or Hard")

    conn = get_connection()
    try:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            conn.execute(
                "INSERT INTO dsa_submissions (username, problem_slug, problem_title, difficulty, solved_at, notes) VALUES (?,?,?,?,?,?)",
                (username, problem_slug, problem_title, difficulty, now_iso, notes),
            )
        except Exception as e:
            if "UNIQUE constraint failed" in str(e):
                raise ValueError("You have already solved this problem.")
            raise ValueError(str(e))

        cursor = conn.execute(
            "SELECT dsa_streak, dsa_streak_updated, dsa_total_solved FROM users WHERE username = ?", (username,)
        )
        user = cursor.fetchone()
        if not user:
            raise ValueError("User not found.")

        current_streak = user["dsa_streak"]
        streak_updated_str = user["dsa_streak_updated"]
        total_solved = user["dsa_total_solved"] + 1
        today = datetime.datetime.now(datetime.timezone.utc).date()

        if not streak_updated_str:
            new_streak, update_streak = 1, True
        else:
            try:
                last_update_date = datetime.datetime.fromisoformat(streak_updated_str).date()
            except ValueError:
                last_update_date = today - datetime.timedelta(days=2)

            if last_update_date == today:
                new_streak, update_streak = current_streak, False
            elif last_update_date == today - datetime.timedelta(days=1):
                new_streak, update_streak = current_streak + 1, True
            else:
                new_streak, update_streak = 1, True

        if update_streak:
            conn.execute(
                "UPDATE users SET dsa_streak=?, dsa_streak_updated=?, dsa_total_solved=? WHERE username=?",
                (new_streak, now_iso, total_solved, username),
            )
        else:
            conn.execute("UPDATE users SET dsa_total_solved=? WHERE username=?", (total_solved, username))
        conn.commit()

        return {
            "problem_slug": problem_slug,
            "problem_title": problem_title,
            "difficulty": difficulty,
            "solved_at": now_iso,
            "notes": notes,
            "new_streak": new_streak,
            "total_solved": total_solved,
        }
    finally:
        conn.close()


def get_submissions(username: str, limit: int = 50, offset: int = 0):
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT id, problem_slug, problem_title, difficulty, solved_at, notes, platform FROM dsa_submissions WHERE username=? ORDER BY solved_at DESC LIMIT ? OFFSET ?",
            (username, limit, offset),
        )
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def get_dsa_stats(username: str) -> dict:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT dsa_streak, dsa_total_solved, leetcode_username FROM users WHERE username=?", (username,)
        )
        user = cursor.fetchone()
        if not user:
            raise ValueError("User not found.")
        cursor = conn.execute(
            "SELECT difficulty, COUNT(*) as cnt FROM dsa_submissions WHERE username=? GROUP BY difficulty", (username,)
        )
        counts = {"Easy": 0, "Medium": 0, "Hard": 0}
        for r in cursor.fetchall():
            counts[r["difficulty"]] = r["cnt"]
        return {
            "username": username,
            "dsa_streak": user["dsa_streak"],
            "dsa_total_solved": user["dsa_total_solved"],
            "leetcode_username": user["leetcode_username"],
            "difficulty_distribution": counts,
        }
    finally:
        conn.close()


def get_dsa_leaderboard(limit: int = 10):
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT username, display_name, avatar_initial, dsa_streak, dsa_total_solved, college, department FROM users ORDER BY dsa_streak DESC, dsa_total_solved DESC, username ASC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


# ── Custom test run ───────────────────────────────────────────────────────────

def run_custom(code: str, language: str, stdin_input: str) -> dict:
    """Run user code with arbitrary stdin, return stdout/stderr."""
    lang = (language or "python").lower()
    runtime_err = _check_runtime(lang)
    if runtime_err:
        return {"stdout": "", "stderr": runtime_err, "error": runtime_err}

    if lang in ("python", "py"):
        suffix, runner = ".py", None
        src = code + "\n"
    elif lang in ("javascript", "js"):
        suffix, runner = ".js", None
        src = code + "\n"
    elif lang in ("typescript", "ts"):
        suffix, runner = ".ts", None
        src = code + "\n"
    elif lang in ("go",):
        suffix, runner = ".go", None
        src = f"package main\nimport(\n    \"bufio\"\n    \"fmt\"\n    \"os\"\n)\n{code}\nfunc main(){{\n    scanner:=bufio.NewScanner(os.Stdin)\n    for scanner.Scan(){{ fmt.Println(scanner.Text()) }}\n}}" if "func main()" not in code else code
        src = code
    else:
        return {"stdout": "", "stderr": f"Custom run not supported for {language}", "error": f"Not supported: {language}"}

    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(src)

        # Build command (reuse runtime resolution from _run_file)
        if lang in ("python", "py"):
            cmd = ["python3", path]
        elif lang in ("javascript", "js"):
            node = shutil.which("node") or shutil.which("nodejs")
            cmd = [node, path] if node else None
        elif lang in ("typescript", "ts"):
            tsx = shutil.which("tsx") or shutil.which("ts-node")
            npx = shutil.which("npx")
            if tsx:
                cmd = [tsx, path]
            elif npx:
                cmd = [npx, "tsx", path]
            else:
                cmd = None
        elif lang in ("go",):
            go = shutil.which("go")
            cmd = [go, "run", path] if go else None
        else:
            cmd = None

        if not cmd:
            return {"stdout": "", "stderr": f"Runtime for {lang} not available", "exit_code": 1}

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10,
                input=stdin_input or "",
            )
            return {"stdout": proc.stdout, "stderr": proc.stderr, "exit_code": proc.returncode}
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": "Execution timed out (10s)", "exit_code": 1}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ── Judge0 integration (optional, kicks in when JUDGE0_API_KEY set) ───────────

JUDGE0_LANGUAGE_IDS = {
    "python": 71,       # Python 3
    "javascript": 63,   # Node.js
    "typescript": 74,   # TypeScript
    "java": 62,         # Java (OpenJDK 13)
    "cpp": 54,          # C++ (GCC 9.2)
    "go": 60,           # Go (1.13)
    "c": 50,            # C (GCC 9.2)
    "rust": 73,         # Rust
    "ruby": 72,         # Ruby
    "kotlin": 78,       # Kotlin
    "swift": 83,        # Swift
    "csharp": 51,       # C# (Mono)
    "php": 68,          # PHP
    "r": 80,            # R
    "scala": 81,        # Scala
}

def run_via_judge0(slug: str, code: str, language: str) -> dict:
    """Submit to Judge0 API for sandboxed execution. Falls back to subprocess if unavailable."""
    import urllib.request, urllib.error, base64

    api_key = os.environ.get("JUDGE0_API_KEY", "")
    api_url = os.environ.get("JUDGE0_API_URL", "https://judge0-ce.p.rapidapi.com")

    if not api_key:
        return run_code(slug, code, language)  # fallback

    lang = (language or "python").lower()
    lang_id = JUDGE0_LANGUAGE_IDS.get(lang)
    if not lang_id:
        return run_code(slug, code, language)  # fallback for unsupported langs

    cases = get_all_test_cases(slug)
    if not cases:
        return {"passed": 0, "total": 0, "results": [], "error": "No test cases found"}

    # Build batch submissions
    inputs = [c["input"] for c in cases]

    if lang in ("python", "py"):
        src = _python_harness(code, inputs)
    elif lang in ("javascript", "js"):
        src = _js_harness(code, inputs)
    elif lang in ("typescript", "ts"):
        src = _ts_harness(code, inputs)
    else:
        return run_code(slug, code, language)  # fallback for Java/C++/Go

    payload = json.dumps({
        "source_code": base64.b64encode(src.encode()).decode(),
        "language_id": lang_id,
        "stdin": "",
        "expected_output": None,
    }).encode()

    req = urllib.request.Request(
        f"{api_url}/submissions?base64_encoded=true&wait=true",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": "judge0-ce.p.rapidapi.com",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
    except Exception as e:
        return run_code(slug, code, language)  # fallback on any error

    status = result.get("status", {}).get("description", "")
    if status not in ("Accepted",):
        stderr = result.get("stderr") or result.get("compile_output") or ""
        if stderr:
            try:
                stderr = base64.b64decode(stderr).decode()
            except Exception:
                pass
        return {"passed": 0, "total": len(cases), "results": [], "error": stderr or status}

    raw_stdout = result.get("stdout") or ""
    try:
        raw_stdout = base64.b64decode(raw_stdout).decode()
    except Exception:
        pass

    try:
        actuals = json.loads(raw_stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"passed": 0, "total": len(cases), "results": [], "error": "Could not parse output"}

    results, passed = [], 0
    for i, c in enumerate(cases):
        actual = actuals[i] if i < len(actuals) else None
        ok = actual == c["expected"]
        if ok:
            passed += 1
        results.append({"input": c["input"], "expected": c["expected"], "actual": actual, "passed": ok})

    return {"passed": passed, "total": len(cases), "results": results, "language": lang, "engine": "judge0"}


# ── Per-user notes ────────────────────────────────────────────────────────────

def get_note(username: str, slug: str) -> str:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT content FROM dsa_notes WHERE username=? AND question_slug=?", (username, slug)
        ).fetchone()
        return row["content"] if row else ""
    finally:
        conn.close()


def save_note(username: str, slug: str, content: str) -> None:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO dsa_notes (username, question_slug, content, updated_at)
               VALUES (?,?,?,?)
               ON CONFLICT(username, question_slug) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at""",
            (username, slug, content[:5000], now),
        )
        conn.commit()
    finally:
        conn.close()
