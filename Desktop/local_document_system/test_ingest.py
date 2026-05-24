import os
import time
import json
import httpx

API_BASE = "http://localhost:8000"

# 1. Define Sample Documents
documents_data = {
    "cs101_syllabus.txt": """
CS101: Foundations of Computer Science
Semester: Fall 2026
Instructor: Dr. Elizabeth Adams (adams.e@university.edu)
Office: Tech Hall, Room 405
Office Hours: Tuesdays and Thursdays, 2:00 PM - 4:00 PM

Course Description:
This course introduces the fundamental concepts of computer science, including algorithms, data structures, software engineering principles, and basic programming in Python.

Grading Criteria:
- Homework Assignments: 30% (5 coding assignments throughout the semester)
- Midterm Examination: 25% (Date: October 14, covers weeks 1-7)
- Final Programming Project: 35% (Submission Deadline: December 8, requires building a command-line RAG application)
- Class Participation: 10%

Class Attendance:
Attendance is mandatory. More than three unexcused absences will result in a 5% penalty on the final grade.
Late submissions for coding assignments lose 10% per day and will not be accepted after 3 days past the deadline.
""",
    
    "academic_integrity_policy.txt": """
University Academic Integrity & Conduct Code
Published: August 2025
Applicability: All undergraduate and graduate programs

1. Plagiarism and Cheating:
Plagiarism is defined as presenting someone else's work, ideas, or language as one's own without clear citation. Cheating includes using unauthorized aids during exams, copying homework, or sharing code in programming classes.

2. Sanctions and Procedures:
- First Offense: An automatic zero (F) on the assignment or exam in question. The instructor will file a formal incident report with the Academic Review Board (ARB).
- Second Offense: Suspension from the university for one academic semester.
- Third Offense: Permanent expulsion from the university.

3. Appeal Process:
Students have the right to appeal any ARB decision. The appeal must be submitted in writing to the Office of the Dean of Academic Affairs within 5 business days of receiving the sanction notice. The student may present evidence and witnesses at the hearing.
""",
    
    "admissions_enrollment_guide.txt": """
Office of the Registrar: Course Registration & Enrollment Guide
Academic Year: 2026-2027

General Guidelines:
Students must enroll in courses via the student portal. Registration for the Fall semester opens on November 10, and Spring registration opens on April 15.

Credit Hours Requirements:
- Full-Time Status: A minimum of 12 credit hours per semester.
- Part-Time Status: Anything under 12 credit hours.
- Maximum Credit Load: 18 credit hours per semester. Requests to exceed this limit require a waiver signed by the student's Academic Advisor and the Department Chair.

Add/Drop Policy:
Students may add or drop courses freely within the first 10 academic days of the semester without penalty. Courses dropped after the 10th day but before the 40th day will receive a grade of 'W' (Withdrawn) on their transcript. No courses may be dropped after the 40th academic day.

Prerequisites:
Many advanced courses require prerequisite classes. If a student wants to bypass a prerequisite, they must obtain a prerequisite waiver form signed by the Department Chair of the teaching department.
"""
}

def create_files():
    print("Generating sample academic files...")
    for filename, content in documents_data.items():
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content.strip())
        print(f"Created file: {filename}")

async def upload_files():
    print("\nUploading files to local DocuSync server...")
    async with httpx.AsyncClient() as client:
        for filename in documents_data.keys():
            with open(filename, "rb") as f:
                files = {"file": (filename, f, "text/plain")}
                try:
                    response = await client.post(f"{API_BASE}/upload", files=files)
                    if response.status_code == 200:
                        print(f"Successfully sent upload request for: {filename}")
                    else:
                        print(f"Upload failed for {filename}: {response.json()}")
                except Exception as e:
                    print(f"Connection error uploading {filename}: {e}")
                    return False
    return True

async def wait_for_ingestion():
    print("\nWaiting for background AI processing to complete (polling status)...")
    async with httpx.AsyncClient() as client:
        for _ in range(20):  # Poll up to 20 times (60 seconds)
            response = await client.get(f"{API_BASE}/documents")
            if response.status_code == 200:
                docs = response.json()
                processing = [d["filename"] for d in docs if d["status"] == "processing"]
                completed = [d["filename"] for d in docs if d["status"] == "completed"]
                failed = [d["filename"] for d in docs if d["status"] == "failed"]
                
                print(f"Status - Completed: {len(completed)}, Processing: {len(processing)}, Failed: {len(failed)}")
                
                if len(processing) == 0:
                    print("All files finished processing!")
                    return docs
            time.sleep(3)
    print("Warning: Polling timed out. Some files might still be processing.")
    return []

async def test_search_queries():
    queries = [
        "What happens if I cheat on an exam?",
        "When is the CS101 final project deadline?",
        "What is the maximum credits I can take?",
        "Who is the professor for computer science?"
    ]
    
    print("\n==================================================")
    print("Running Semantic Search Verification Queries:")
    print("==================================================")
    
    async with httpx.AsyncClient() as client:
        for query in queries:
            print(f"\nQuery: '{query}'")
            try:
                response = await client.post(f"{API_BASE}/search", json={"query": query, "limit": 2})
                if response.status_code == 200:
                    hits = response.json()
                    if not hits:
                        print("  -> No results returned.")
                    for h in hits:
                        relevancy = round(h["score"] * 100)
                        print(f"  -> Match: '{h['filename']}' (Page {h['page']}) - Relevance: {relevancy}%")
                        print(f"     Snippet: \"...{h['text'][:150]}...\"")
                else:
                    print(f"  -> Search failed: {response.status_code}")
            except Exception as e:
                print(f"  -> Connection error: {e}")

def cleanup_files():
    print("\nCleaning up local test text files...")
    for filename in documents_data.keys():
        if os.path.exists(filename):
            os.remove(filename)
            print(f"Deleted test file: {filename}")

async def main():
    create_files()
    if await upload_files():
        docs = await wait_for_ingestion()
        if docs:
            print("\n==================================================")
            print("Extracted AI Metadata Profiles:")
            print("==================================================")
            for d in docs:
                if d["status"] == "completed":
                    print(f"\nFile: {d['filename']}")
                    print(f"Summary: {d['summary']}")
                    print(f"Tags: {', '.join(d['tags'])}")
                    print(f"Key Findings:")
                    for f in d["key_findings"]:
                        print(f"  - {f}")
            
            await test_search_queries()
    cleanup_files()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
