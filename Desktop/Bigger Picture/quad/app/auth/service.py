import os
import re
import uuid
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional
import bcrypt
from jose import jwt, JWTError

from app.db import get_connection

JWT_SECRET = os.environ.get("JWT_SECRET", "change-this-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7   # 7 days

def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty")
    passwd = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(passwd, salt).decode('utf-8')

def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False

def create_user(
    username: str,
    email: str,
    password: str,
    role: str = "student",
    display_name: Optional[str] = None,
    college: Optional[str] = None,
    department: Optional[str] = None,
    year_of_study: Optional[int] = None
) -> dict:
    # Validate username: 3-30 chars, alphanumeric + hyphens only
    if not username or len(username) < 3 or len(username) > 30:
        raise ValueError("Username must be between 3 and 30 characters.")
    if not re.match(r"^[a-zA-Z0-9_\-]+$", username):
        raise ValueError("Username must contain only alphanumeric characters, hyphens, and underscores.")
    
    # Validate email
    if not email or "@" not in email or "." not in email:
        raise ValueError("Invalid email format.")
        
    # Validate password
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")

    password_hash = hash_password(password)
    avatar_initial = username[0].upper()
    created_at = datetime.now(timezone.utc).isoformat()
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO users (
                username, email, password_hash, display_name, avatar_initial,
                role, college, department, year_of_study, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username, email, password_hash, display_name, avatar_initial,
                role, college, department, year_of_study, created_at
            )
        )
        conn.commit()
        user_id = cursor.lastrowid
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        user_dict = dict(row)
        user_dict.pop("password_hash", None)
        return user_dict
    except sqlite3.IntegrityError as e:
        err_msg = str(e)
        if "username" in err_msg:
            raise ValueError(f"Username '{username}' is already taken.")
        elif "email" in err_msg:
            raise ValueError(f"Email '{email}' is already registered.")
        else:
            raise ValueError("Username or email already exists.")
    finally:
        conn.close()

def authenticate_user(username_or_email: str, password: str) -> Optional[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?",
            (username_or_email, username_or_email)
        )
        row = cursor.fetchone()
        if not row:
            return None
        
        user_dict = dict(row)
        if not verify_password(password, user_dict["password_hash"]):
            return None
            
        # Update last_login
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (now, user_dict["id"])
        )
        conn.commit()
        
        user_dict["last_login"] = now
        user_dict.pop("password_hash", None)
        return user_dict
    finally:
        conn.close()

def create_access_token(user_id: int, username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    jti = str(uuid.uuid4())
    
    payload = {
        "sub": username,
        "user_id": user_id,
        "role": role,
        "jti": jti,
        "exp": expire
    }
    
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    # Store session
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sessions (user_id, token_jti, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (user_id, jti, datetime.now(timezone.utc).isoformat(), expire.isoformat())
        )
        conn.commit()
    finally:
        conn.close()
        
    return token

def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        jti = payload.get("jti")
        if not jti:
            return None
            
        # Check jti in sessions (not revoked)
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM sessions WHERE token_jti = ?", (jti,))
            if not cursor.fetchone():
                return None
        finally:
            conn.close()
            
        return payload
    except JWTError:
        return None

def revoke_token(jti: str) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE token_jti = ?", (jti,))
        conn.commit()
    finally:
        conn.close()

def get_user_by_username(username: str) -> Optional[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if not row:
            return None
        u = dict(row)
        u.pop("password_hash", None)
        return u
    finally:
        conn.close()
