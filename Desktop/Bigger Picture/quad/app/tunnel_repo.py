import uuid
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional
from app.db import get_connection

def create_tunnel(app_name: str, owner: str, local_port: int, subdomain: str, frpc_name: str) -> dict:
    conn = get_connection()
    tunnel_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    last_ping = created_at
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tunnels (tunnel_id, app_name, owner, local_port, subdomain, status, frpc_name, created_at, last_ping)
            VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
            """,
            (tunnel_id, app_name, owner, local_port, subdomain, frpc_name, created_at, last_ping)
        )
        conn.commit()
        
        cursor.execute("SELECT * FROM tunnels WHERE tunnel_id = ?", (tunnel_id,))
        row = cursor.fetchone()
        return dict(row)
    finally:
        conn.close()

def get_tunnel(tunnel_id: str) -> Optional[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tunnels WHERE tunnel_id = ?", (tunnel_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def get_tunnel_by_subdomain(subdomain: str) -> Optional[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tunnels WHERE subdomain = ?", (subdomain,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def list_tunnels(owner: Optional[str] = None) -> List[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if owner:
            cursor.execute("SELECT * FROM tunnels WHERE owner = ?", (owner,))
        else:
            cursor.execute("SELECT * FROM tunnels")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def close_tunnel(tunnel_id: str) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE tunnels SET status = 'CLOSED' WHERE tunnel_id = ?", (tunnel_id,))
        conn.commit()
    finally:
        conn.close()

def delete_tunnel(tunnel_id: str) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tunnels WHERE tunnel_id = ?", (tunnel_id,))
        conn.commit()
    finally:
        conn.close()

def ping_tunnel(tunnel_id: str) -> None:
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE tunnels SET last_ping = ? WHERE tunnel_id = ?", (now, tunnel_id))
        conn.commit()
    finally:
        conn.close()

def cleanup_stale_tunnels(older_than_seconds: int = 300) -> List[str]:
    conn = get_connection()
    now = datetime.now(timezone.utc)
    stale_ids = []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT tunnel_id, last_ping FROM tunnels WHERE status = 'ACTIVE'")
        rows = cursor.fetchall()
        for row in rows:
            tid = row["tunnel_id"]
            lping = row["last_ping"]
            if lping:
                try:
                    lping_dt = datetime.fromisoformat(lping)
                    if lping_dt.tzinfo is None:
                        lping_dt = lping_dt.replace(tzinfo=timezone.utc)
                    elapsed = (now - lping_dt).total_seconds()
                    if elapsed > older_than_seconds:
                        stale_ids.append(tid)
                except Exception:
                    stale_ids.append(tid)
            else:
                stale_ids.append(tid)
                
        for tid in stale_ids:
            cursor.execute("UPDATE tunnels SET status = 'CLOSED' WHERE tunnel_id = ?", (tid,))
        conn.commit()
        return stale_ids
    finally:
        conn.close()
