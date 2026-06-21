import os
import json
import hashlib
import uuid
import time
from rq import Queue
from redis import Redis
from app.db import get_connection

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

def get_redis() -> Redis:
    return Redis.from_url(REDIS_URL)

def get_queue() -> Queue:
    return Queue("quad-ai", connection=get_redis())

def enqueue_job(job_type: str, app_name: str,
                username: str, input_data: dict) -> str:
    """
    1. Compute cache_key = SHA256(job_type + json.dumps(input_data, sort_keys=True))
    2. Check ai_jobs for existing DONE job with same cache_key -> return existing job_id if found
    3. Insert ai_jobs record with status=QUEUED
    4. Enqueue to RQ target process_job
    5. Return job_id
    """
    # Sort keys for deterministic JSON serialization
    serialized_input = json.dumps(input_data, sort_keys=True)
    hash_payload = f"{job_type}:{serialized_input}".encode("utf-8")
    cache_key = hashlib.sha256(hash_payload).hexdigest()
    
    # 2. Check for cache hit
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT job_id FROM ai_jobs 
            WHERE cache_key = ? AND status = 'DONE'
            ORDER BY completed_at DESC LIMIT 1
        """, (cache_key,))
        row = cursor.fetchone()
        if row:
            return row["job_id"]
            
        # 3. Cache miss: insert new job record
        job_id = str(uuid.uuid4())
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO ai_jobs (
                job_id, app_name, username, job_type, status, input, queued_at, cache_key
            ) VALUES (?, ?, ?, ?, 'QUEUED', ?, ?, ?)
        """, (job_id, app_name, username, job_type, serialized_input, now_str, cache_key))
        conn.commit()
    finally:
        conn.close()
        
    # 4. Enqueue to RQ
    try:
        q = get_queue()
        q.enqueue("app.ai.worker.process_job", job_id)
    except Exception as e:
        print(f"Error enqueuing job {job_id} to Redis: {e}")

    # Fallback: start a background thread to process the job locally 
    # to guarantee AI features function without Redis/RQ
    try:
        import threading
        from app.ai.worker import process_job
        threading.Thread(target=process_job, args=(job_id,), daemon=True).start()
    except Exception as ex:
        print(f"Failed to run fallback local thread: {ex}")
        
    return job_id

def get_job_status(job_id: str) -> dict | None:
    """
    Return ai_jobs record for job_id, parsed input and result from JSON strings.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ai_jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        job_dict = dict(row)
        if job_dict.get("input"):
            try:
                job_dict["input"] = json.loads(job_dict["input"])
            except Exception:
                pass
        if job_dict.get("result"):
            try:
                job_dict["result"] = json.loads(job_dict["result"])
            except Exception:
                pass
        return job_dict
    finally:
        conn.close()
