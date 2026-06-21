import re
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from app.middleware.rate_limit import limiter
from typing import Optional

from app.auth.models import UserRegister, UserLogin, UserUpdate, AuthResponse, UserPublic
from app.auth.service import (
    create_user,
    authenticate_user,
    create_access_token,
    revoke_token,
    decode_token
)
from app.auth.dependencies import get_current_user
from app.db import get_connection

router = APIRouter(prefix="/auth", tags=["auth"])

def get_user_by_username(username: str) -> Optional[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if row:
            user_dict = dict(row)
            user_dict.pop("password_hash", None)
            return user_dict
        return None
    finally:
        conn.close()

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, request: Request):
    final_role = "student"
    if payload.role in ("faculty", "admin"):
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            token_payload = decode_token(token)
            if token_payload and token_payload.get("role") == "admin":
                final_role = payload.role
            else:
                final_role = "student"
        else:
            final_role = "student"
    else:
        if payload.role:
            final_role = payload.role
            
    try:
        user = create_user(
            username=payload.username,
            email=payload.email,
            password=payload.password,
            role=final_role,
            display_name=payload.display_name,
            college=payload.college,
            department=payload.department,
            year_of_study=payload.year_of_study
        )
        token = create_access_token(user["id"], user["username"], user["role"])
        return {"user": user, "access_token": token}
    except ValueError as e:
        err_msg = str(e)
        if "already taken" in err_msg or "already registered" in err_msg or "already exists" in err_msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)

@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, payload: UserLogin):
    identifier = payload.username_or_email or payload.username
    user = authenticate_user(identifier, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password"
        )
    token = create_access_token(user["id"], user["username"], user["role"])
    return {"user": user, "access_token": token}

@router.post("/logout")
def logout(current_user: dict = Depends(get_current_user)):
    jti = current_user.get("jti")
    if jti:
        revoke_token(jti)
    return {"logged_out": True}

@router.get("/me", response_model=UserPublic)
def get_me(current_user: dict = Depends(get_current_user)):
    username = current_user["sub"]
    user = get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user

def _update_profile(payload: UserUpdate, username: str):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE username = ?", (username,))
        if not cursor.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        update_fields = []
        params = []
        for field in ["display_name", "bio", "college", "department", "year_of_study", "github_url", "linkedin_url"]:
            val = getattr(payload, field)
            if val is not None:
                update_fields.append(f"{field} = ?")
                params.append(val)

        if update_fields:
            query = f"UPDATE users SET {', '.join(update_fields)} WHERE username = ?"
            params.append(username)
            cursor.execute(query, params)
            conn.commit()

        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        user_dict = dict(row)
        user_dict.pop("password_hash", None)
        return user_dict
    finally:
        conn.close()


@router.put("/profile", response_model=UserPublic)
def put_profile(payload: UserUpdate, current_user: dict = Depends(get_current_user)):
    return _update_profile(payload, current_user["sub"])


@router.patch("/profile", response_model=UserPublic)
def patch_profile(payload: UserUpdate, current_user: dict = Depends(get_current_user)):
    return _update_profile(payload, current_user["sub"])


@router.patch("/me", response_model=UserPublic)
def patch_me(payload: UserUpdate, current_user: dict = Depends(get_current_user)):
    username = current_user["sub"]

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE username = ?", (username,))
        if not cursor.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            
        update_fields = []
        params = []
        for field in ["display_name", "bio", "college", "department", "year_of_study", "github_url", "linkedin_url"]:
            val = getattr(payload, field)
            if val is not None:
                update_fields.append(f"{field} = ?")
                params.append(val)
                
        if update_fields:
            query = f"UPDATE users SET {', '.join(update_fields)} WHERE username = ?"
            params.append(username)
            cursor.execute(query, params)
            conn.commit()
            
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        user_dict = dict(row)
        user_dict.pop("password_hash", None)
        return user_dict
    finally:
        conn.close()
