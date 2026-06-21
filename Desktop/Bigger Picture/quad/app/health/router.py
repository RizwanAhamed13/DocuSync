import json
import time
from fastapi import APIRouter, Depends, HTTPException, Response, status
from app.auth.dependencies import get_current_user
from app.db import get_connection
from app.health.analyzer import analyze_code_health

router = APIRouter(tags=["health"])

@router.post("/health-check/{app_name}")
def run_health_check_endpoint(
    app_name: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        report = analyze_code_health(app_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Code health scan failed: {e}")
        
    # Save to database
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO health_reports (
                report_id, app_name, generated_at, summary, file_reports, overall_score, grade
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            report["report_id"],
            report["app_name"],
            report["generated_at"],
            json.dumps(report["summary"]),
            json.dumps(report["file_reports"]),
            report["overall_score"],
            report["grade"]
        ))
        conn.commit()
    finally:
        conn.close()
        
    return report

@router.get("/health-check/{app_name}")
def get_latest_health_check(
    app_name: str,
    current_user: dict = Depends(get_current_user)
):
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT * FROM health_reports 
            WHERE app_name = ? 
            ORDER BY generated_at DESC LIMIT 1
        """, (app_name,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No health report found for this application. Trigger one first.")
            
        data = dict(row)
        return {
            "report_id": data["report_id"],
            "app_name": data["app_name"],
            "generated_at": data["generated_at"],
            "summary": json.loads(data["summary"]),
            "file_reports": json.loads(data["file_reports"]),
            "overall_score": data["overall_score"],
            "grade": data["grade"]
        }
    finally:
        conn.close()

@router.get("/health-check/{app_name}/history")
def get_health_history(
    app_name: str,
    current_user: dict = Depends(get_current_user)
):
    conn = get_connection()
    try:
        cursor = conn.execute("""
            SELECT generated_at, overall_score, grade, summary 
            FROM health_reports 
            WHERE app_name = ? 
            ORDER BY generated_at DESC
        """, (app_name,))
        rows = cursor.fetchall()
        
        history = []
        for r in rows:
            history.append({
                "generated_at": r["generated_at"],
                "overall_score": r["overall_score"],
                "grade": r["grade"],
                "summary": json.loads(r["summary"])
            })
        return history
    finally:
        conn.close()

@router.get("/health-check/{app_name}/badge")
def get_health_badge(app_name: str):
    # Fetch latest grade
    conn = get_connection()
    grade = "N/A"
    try:
        cursor = conn.execute("SELECT grade FROM health_reports WHERE app_name = ? ORDER BY generated_at DESC LIMIT 1", (app_name,))
        row = cursor.fetchone()
        if row:
            grade = row["grade"]
    finally:
        conn.close()
        
    # Define colors for grades
    colors = {
        "A": "#2ecc71", # green
        "B": "#3498db", # blue
        "C": "#f1c40f", # yellow
        "D": "#e67e22", # orange
        "F": "#e74c3c", # red
        "N/A": "#95a5a6" # gray
    }
    color = colors.get(grade, "#95a5a6")
    
    # Generate SVG Badge
    svg_badge = f"""<svg xmlns="http://www.w3.org/2000/svg" width="100" height="20">
  <linearGradient id="b" grandfather="1" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="a">
    <rect width="100" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#a)">
    <path fill="#555" d="M0 0h65v20H0z"/>
    <path fill="{color}" d="M65 0h35v20H65z"/>
    <path fill="url(#b)" d="M0 0h100v20H0z"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="32.5" y="15" fill="#010101" fill-opacity=".3">health</text>
    <text x="32.5" y="14">health</text>
    <text x="82.5" y="15" fill="#010101" fill-opacity=".3">{grade}</text>
    <text x="82.5" y="14">{grade}</text>
  </g>
</svg>"""
    return Response(content=svg_badge, media_type="image/svg+xml")
