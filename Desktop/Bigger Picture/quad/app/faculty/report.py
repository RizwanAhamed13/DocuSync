import csv
import json
from fpdf import FPDF

class AssignmentPDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', align='C')

def generate_assignment_report(
    assignment: dict,
    submissions: list[dict],
    similarity_flags: list[dict],
    output_path: str
) -> str:
    """
    Generate a PDF report at output_path.
    Return output_path.
    """
    pdf = AssignmentPDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # 1. Header Section
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, f"Assignment Report: {assignment.get('title', 'N/A')}", ln=True, align='C')
    pdf.set_font('Helvetica', '', 10)
    pdf.ln(5)
    pdf.cell(0, 6, f"Course Code: {assignment.get('course_code') or 'N/A'}", ln=True)
    pdf.cell(0, 6, f"Batch: {assignment.get('batch') or 'N/A'}", ln=True)
    pdf.cell(0, 6, f"Deadline: {assignment.get('deadline') or 'N/A'}", ln=True)
    pdf.cell(0, 6, f"Created By: {assignment.get('created_by') or 'N/A'}", ln=True)
    pdf.ln(10)
    
    # 2. Summary Table Section
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 8, "Submission Summary", ln=True)
    pdf.set_font('Helvetica', 'B', 9)
    
    # Header styling
    pdf.set_fill_color(60, 60, 60)
    pdf.set_text_color(255, 255, 255)
    
    headers = ["Roll No", "Name", "Stack", "Files", "Lines", "Quality", "Score", "Status"]
    widths = [25, 45, 25, 15, 15, 20, 15, 30]
    for h, w in zip(headers, widths):
        pdf.cell(w, 8, h, border=1, align='C', fill=True)
    pdf.ln()
    
    pdf.set_text_color(0, 0, 0)
    pdf.set_font('Helvetica', '', 9)
    sorted_subs = sorted(submissions, key=lambda s: s.get('roll_number') or '')
    
    fill = False
    for sub in sorted_subs:
        if fill:
            pdf.set_fill_color(240, 240, 240)
        else:
            pdf.set_fill_color(255, 255, 255)
            
        pdf.cell(25, 7, str(sub.get('roll_number') or 'N/A'), border=1, align='C', fill=True)
        pdf.cell(45, 7, str(sub.get('student_name') or 'N/A'), border=1, fill=True)
        pdf.cell(25, 7, str(sub.get('detected_stack') or 'N/A'), border=1, align='C', fill=True)
        pdf.cell(15, 7, str(sub.get('file_count') if sub.get('file_count') is not None else 'N/A'), border=1, align='C', fill=True)
        pdf.cell(15, 7, str(sub.get('line_count') if sub.get('line_count') is not None else 'N/A'), border=1, align='C', fill=True)
        pdf.cell(20, 7, str(sub.get('code_quality_score') if sub.get('code_quality_score') is not None else 'N/A'), border=1, align='C', fill=True)
        pdf.cell(15, 7, str(sub.get('score') if sub.get('score') is not None else 'N/A'), border=1, align='C', fill=True)
        pdf.cell(30, 7, str(sub.get('status') or 'N/A'), border=1, align='C', fill=True)
        pdf.ln()
        fill = not fill
        
    pdf.ln(10)
    
    # 3. Issues per Submission
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 8, "Detailed Submission Issues", ln=True)
    pdf.ln(2)
    
    for sub in sorted_subs:
        pdf.set_font('Helvetica', 'B', 10)
        pdf.cell(0, 6, f"{sub.get('student_name')} ({sub.get('roll_number') or 'N/A'}):", ln=True)
        pdf.set_font('Helvetica', '', 9)
        
        issues_raw = sub.get('issues') or '[]'
        try:
            issues = json.loads(issues_raw) if isinstance(issues_raw, str) else issues_raw
        except Exception:
            issues = []
            
        missing_features_raw = sub.get('missing_features') or '[]'
        try:
            missing = json.loads(missing_features_raw) if isinstance(missing_features_raw, str) else missing_features_raw
        except Exception:
            missing = []
            
        if not issues and not missing:
            pdf.cell(0, 5, "  No major static analysis issues found.", ln=True)
        else:
            if issues:
                pdf.cell(0, 5, "  Issues:", ln=True)
                for issue in issues:
                    pdf.cell(0, 5, f"    - {issue}", ln=True)
            if missing:
                pdf.cell(0, 5, "  Missing Features:", ln=True)
                for feat in missing:
                    pdf.cell(0, 5, f"    - {feat}", ln=True)
        pdf.ln(4)
        
    pdf.ln(6)
    
    # 4. Plagiarism Flags Table
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 8, "Plagiarism Check", ln=True)
    pdf.ln(2)
    
    if not similarity_flags:
        pdf.set_font('Helvetica', '', 10)
        pdf.cell(0, 6, "No plagiarism detected.", ln=True)
    else:
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_fill_color(60, 60, 60)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(70, 8, "Submission A", border=1, fill=True)
        pdf.cell(70, 8, "Submission B", border=1, fill=True)
        pdf.cell(25, 8, "Similarity %", border=1, align='C', fill=True)
        pdf.cell(25, 8, "Flag", border=1, align='C', fill=True)
        pdf.ln()
        
        pdf.set_text_color(0, 0, 0)
        pdf.set_font('Helvetica', '', 9)
        for flag in similarity_flags:
            sub_a_name = flag.get('submission_a')
            sub_b_name = flag.get('submission_b')
            for s in submissions:
                if s['submission_id'] == flag.get('submission_a'):
                    sub_a_name = f"{s.get('student_name')} ({s.get('roll_number') or 'N/A'})"
                if s['submission_id'] == flag.get('submission_b'):
                    sub_b_name = f"{s.get('student_name')} ({s.get('roll_number') or 'N/A'})"
                    
            if flag.get('flag') == 'HIGH':
                pdf.set_fill_color(255, 200, 200)
            else:
                pdf.set_fill_color(255, 255, 255)
                
            pdf.cell(70, 7, str(sub_a_name), border=1, fill=True)
            pdf.cell(70, 7, str(sub_b_name), border=1, fill=True)
            pdf.cell(25, 7, f"{flag.get('similarity')*100:.1f}%", border=1, align='C', fill=True)
            pdf.cell(25, 7, str(flag.get('flag')), border=1, align='C', fill=True)
            pdf.ln()
            
    pdf.ln(10)
    
    # 5. AI Summaries Section
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 8, "AI Project Summaries", ln=True)
    pdf.ln(2)
    
    for sub in sorted_subs:
        pdf.set_font('Helvetica', 'B', 10)
        pdf.cell(0, 6, f"{sub.get('student_name')} ({sub.get('roll_number') or 'N/A'}):", ln=True)
        pdf.set_font('Helvetica', '', 9)
        summary = sub.get('ai_summary') or "AI summary unavailable."
        pdf.multi_cell(0, 5, summary)
        pdf.ln(4)
        
    pdf.output(output_path)
    return output_path

def generate_csv_export(
    submissions: list[dict],
    output_path: str
) -> str:
    """
    Write CSV with submission analytics.
    """
    fields = [
        "roll_number", "student_name", "stack", "file_count", "line_count",
        "quality_score", "score", "feedback", "issues_count",
        "plagiarism_flag", "analyzed_at"
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(fields)
        for s in submissions:
            issues_raw = s.get('issues') or '[]'
            try:
                issues = json.loads(issues_raw) if isinstance(issues_raw, str) else issues_raw
            except Exception:
                issues = []
            issues_count = len(issues)
            
            writer.writerow([
                s.get("roll_number") or "",
                s.get("student_name") or "",
                s.get("detected_stack") or "",
                s.get("file_count") if s.get("file_count") is not None else "",
                s.get("line_count") if s.get("line_count") is not None else "",
                s.get("code_quality_score") if s.get("code_quality_score") is not None else "",
                s.get("score") if s.get("score") is not None else "",
                s.get("feedback") or "",
                issues_count,
                s.get("plagiarism_flag") or 0,
                s.get("analyzed_at") or ""
            ])
    return output_path
