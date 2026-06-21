import os
import re
import datetime
import json
import uuid
from app.ai.ingest import SUPPORTED_EXTENSIONS

def calculate_grade(score: float) -> str:
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    else:
        return "F"

def analyze_code_health(app_name: str) -> dict:
    project_path = os.path.join("projects_source", app_name)
    if not os.path.exists(project_path):
        raise ValueError(f"Application codebase folder '{project_path}' not found.")
        
    file_reports = []
    total_loc = 0
    total_files = 0
    secrets_count = 0
    functions_over_50_lines = 0
    bare_excepts_count = 0
    empty_catches_count = 0
    
    secret_pat = re.compile(r'\b(api_key|secret|password|token|pwd|auth_token)\b\s*[:=]\s*[\'"][^\'"]{8,}[\'"]', re.IGNORECASE)
    py_except_pat = re.compile(r'^\s*except\s*(Exception)?\s*:\s*(#.*)?$')
    js_catch_pat = re.compile(r'\bcatch\s*\(.*?\)\s*\{\s*\}')
    
    # Walk directory
    for root, _, filenames in os.walk(project_path):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
                
            fpath = os.path.join(root, fname)
            rel_fpath = os.path.relpath(fpath, project_path)
            total_files += 1
            
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except Exception:
                continue
                
            loc = len(lines)
            total_loc += loc
            content = "".join(lines)
            
            # 1. Complexity & Maintainability Metrics
            complexity = 1.0
            maintainability = 100.0
            
            if ext == ".py":
                # Use Radon
                from radon.complexity import cc_visit
                from radon.metrics import mi_visit
                try:
                    blocks = cc_visit(content)
                    if blocks:
                        complexity = float(sum(b.complexity for b in blocks)) / len(blocks)
                        # Count functions over 50 lines (Radon blocks represent functions/classes)
                        for b in blocks:
                            # Estimate lines: endline - startline
                            if hasattr(b, 'endline') and hasattr(b, 'lineno'):
                                if b.endline - b.lineno > 50:
                                    functions_over_50_lines += 1
                    maintainability = mi_visit(content, multi=True)
                except Exception:
                    pass
            else:
                # Custom heuristic for JS/TS/Java
                # Complexity proxy: control flow tokens
                control_tokens = content.count("if ") + content.count("if(") + \
                                 content.count("for ") + content.count("for(") + \
                                 content.count("while ") + content.count("while(") + \
                                 content.count("catch ") + content.count("catch(") + \
                                 content.count("case ") + content.count("&&") + content.count("||")
                complexity = 1.0 + float(control_tokens)
                
                # Maintainability Index estimate
                # Start at 100, deduct based on LOC and complexity
                deduct_loc = min(30.0, float(loc) * 0.05)
                deduct_comp = min(30.0, complexity * 1.5)
                maintainability = max(20.0, 100.0 - deduct_loc - deduct_comp)
                
                # Estimate functions over 50 lines for JS/TS/Java:
                # Look for function block length by counting braces
                # A simple line regex check
                func_starts = []
                for idx, line in enumerate(lines):
                    if "function " in line or "=>" in line or "public class" in line or "public void" in line:
                        func_starts.append(idx)
                # Count distances
                for idx, start_idx in enumerate(func_starts[:-1]):
                    if func_starts[idx+1] - start_idx > 50:
                        functions_over_50_lines += 1
            
            # 2. Issues scanning
            issues = []
            
            # Python bare excepts
            if ext == ".py":
                for idx, line in enumerate(lines, 1):
                    if py_except_pat.match(line):
                        bare_excepts_count += 1
                        issues.append({
                            "line": idx,
                            "type": "bare_except",
                            "message": "Bare except or raw Exception block",
                            "severity": "medium"
                        })
                        
            # JS/TS/Java empty catches
            if ext in [".js", ".jsx", ".ts", ".tsx", ".java"]:
                catches = js_catch_pat.findall(content)
                if catches:
                    empty_catches_count += len(catches)
                    # Find lines for catches
                    for idx, line in enumerate(lines, 1):
                        if js_catch_pat.search(line):
                            issues.append({
                                "line": idx,
                                "type": "empty_catch",
                                "message": "Empty catch block",
                                "severity": "medium"
                            })
                            
            # Secrets, TODOs, logs
            for idx, line in enumerate(lines, 1):
                if secret_pat.search(line):
                    secrets_count += 1
                    issues.append({
                        "line": idx,
                        "type": "hardcoded_secret",
                        "message": f"Hardcoded secret/credential detected: {line.strip()[:20]}...",
                        "severity": "high"
                    })
                if "TODO" in line:
                    issues.append({
                        "line": idx,
                        "type": "todo",
                        "message": "TODO comment found",
                        "severity": "info"
                    })
                if "console.log" in line or "System.out.print" in line:
                    issues.append({
                        "line": idx,
                        "type": "console_log",
                        "message": "Debugging print/console statement found",
                        "severity": "low"
                    })
                    
            # Deduct points from file score for issues
            file_score = maintainability
            for issue in issues:
                if issue["severity"] == "high":
                    file_score -= 15.0
                elif issue["severity"] == "medium":
                    file_score -= 10.0
                elif issue["severity"] == "low":
                    file_score -= 2.0
            file_score = max(0.0, min(100.0, file_score))
            
            file_reports.append({
                "file_path": rel_fpath,
                "loc": loc,
                "complexity": round(complexity, 2),
                "maintainability": round(maintainability, 2),
                "score": int(file_score),
                "grade": calculate_grade(file_score),
                "issues": issues,
                "issues_count": len(issues)
            })
            
    # Project aggregate score
    if file_reports:
        # Weighted average by LOC or simple average. Standard is simple average of files.
        avg_score = sum(f["score"] for f in file_reports) / len(file_reports)
    else:
        avg_score = 100.0
        
    # Deduct further for global issues like hardcoded secrets
    avg_score = max(0.0, min(100.0, avg_score))
    overall_score = int(avg_score)
    
    summary = {
        "total_files": total_files,
        "total_loc": total_loc,
        "secrets_count": secrets_count,
        "functions_over_50_lines": functions_over_50_lines,
        "bare_excepts_count": bare_excepts_count,
        "empty_catches_count": empty_catches_count
    }
    
    return {
        "report_id": str(uuid.uuid4()),
        "app_name": app_name,
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "summary": summary,
        "file_reports": file_reports,
        "overall_score": overall_score,
        "grade": calculate_grade(overall_score)
    }
