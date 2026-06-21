import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.db import get_connection

router = APIRouter(tags=["feed"])


class PostCreate(BaseModel):
    content: str
    code_snippet: Optional[str] = None
    language: Optional[str] = None
    project_name: Optional[str] = None
    post_type: str = "text"


class CommentCreate(BaseModel):
    content: str


def _now():
    return datetime.now(timezone.utc).isoformat()


def _user_meta(conn, username: str):
    row = conn.execute(
        "SELECT display_name, avatar_initial FROM users WHERE username = ?", (username,)
    ).fetchone()
    if row:
        return row["display_name"] or username, row["avatar_initial"] or username[:1].upper()
    return username, username[:1].upper()


@router.get("/feed", response_model=List[dict])
def list_feed():
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM posts ORDER BY created_at DESC LIMIT 20"
        )
        posts = []
        for row in cursor.fetchall():
            p = dict(row)
            display_name, avatar_initial = _user_meta(conn, p["username"])
            p["display_name"] = display_name
            p["avatar_initial"] = avatar_initial
            posts.append(p)
        return posts
    finally:
        conn.close()


@router.post("/feed", status_code=status.HTTP_201_CREATED)
def create_post(payload: PostCreate, current_user: dict = Depends(get_current_user)):
    if not payload.content.strip() and not (payload.code_snippet or "").strip():
        raise HTTPException(status_code=400, detail="Post content cannot be empty")
    conn = get_connection()
    try:
        post_id = "post_" + uuid.uuid4().hex[:12]
        now = _now()
        post_type = payload.post_type
        if payload.code_snippet and post_type == "text":
            post_type = "code"
        conn.execute(
            """
            INSERT INTO posts
            (post_id, username, content, code_snippet, language, project_name, post_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post_id, current_user["sub"], payload.content, payload.code_snippet,
                payload.language, payload.project_name, post_type, now,
            ),
        )
        conn.commit()
        try:
            from app.badges.service import check_and_award
            check_and_award(current_user["sub"], "post_created")
        except Exception:
            pass
        row = conn.execute("SELECT * FROM posts WHERE post_id = ?", (post_id,)).fetchone()
        p = dict(row)
        display_name, avatar_initial = _user_meta(conn, p["username"])
        p["display_name"] = display_name
        p["avatar_initial"] = avatar_initial
        return p
    finally:
        conn.close()


@router.post("/feed/{post_id}/like")
def like_post(post_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_connection()
    try:
        exists = conn.execute("SELECT 1 FROM posts WHERE post_id = ?", (post_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Post not found")
        already = conn.execute(
            "SELECT 1 FROM post_likes WHERE post_id = ? AND username = ?",
            (post_id, current_user["sub"]),
        ).fetchone()
        if already:
            conn.execute(
                "DELETE FROM post_likes WHERE post_id = ? AND username = ?",
                (post_id, current_user["sub"]),
            )
            conn.execute(
                "UPDATE posts SET likes_count = MAX(0, likes_count - 1) WHERE post_id = ?",
                (post_id,),
            )
            liked = False
        else:
            conn.execute(
                "INSERT INTO post_likes (post_id, username, created_at) VALUES (?, ?, ?)",
                (post_id, current_user["sub"], _now()),
            )
            conn.execute(
                "UPDATE posts SET likes_count = likes_count + 1 WHERE post_id = ?",
                (post_id,),
            )
            liked = True
            author_row = conn.execute(
                "SELECT username FROM posts WHERE post_id = ?", (post_id,)
            ).fetchone()
            if author_row and author_row["username"] != current_user["sub"]:
                try:
                    from app.notifications.service import create_notification
                    create_notification(
                        author_row["username"], "like", "New like",
                        f"{current_user['sub']} liked your post", "/feed",
                        conn=conn,
                    )
                except Exception:
                    pass
        conn.commit()
        count = conn.execute(
            "SELECT likes_count FROM posts WHERE post_id = ?", (post_id,)
        ).fetchone()["likes_count"]
        return {"post_id": post_id, "liked": liked, "likes_count": count}
    finally:
        conn.close()


@router.get("/feed/{post_id}/comments", response_model=List[dict])
def list_comments(post_id: str):
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM post_comments WHERE post_id = ? ORDER BY created_at ASC",
            (post_id,),
        )
        comments = []
        for row in cursor.fetchall():
            c = dict(row)
            display_name, avatar_initial = _user_meta(conn, c["username"])
            c["display_name"] = display_name
            c["avatar_initial"] = avatar_initial
            comments.append(c)
        return comments
    finally:
        conn.close()


@router.post("/feed/{post_id}/comments", status_code=status.HTTP_201_CREATED)
def create_comment(post_id: str, payload: CommentCreate, current_user: dict = Depends(get_current_user)):
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="Comment cannot be empty")
    conn = get_connection()
    try:
        exists = conn.execute("SELECT 1 FROM posts WHERE post_id = ?", (post_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Post not found")
        comment_id = "cmt_" + uuid.uuid4().hex[:12]
        now = _now()
        conn.execute(
            """
            INSERT INTO post_comments (comment_id, post_id, username, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (comment_id, post_id, current_user["sub"], payload.content, now),
        )
        conn.execute(
            "UPDATE posts SET comments_count = comments_count + 1 WHERE post_id = ?",
            (post_id,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM post_comments WHERE comment_id = ?", (comment_id,)
        ).fetchone()
        c = dict(row)
        display_name, avatar_initial = _user_meta(conn, c["username"])
        c["display_name"] = display_name
        c["avatar_initial"] = avatar_initial
        return c
    finally:
        conn.close()
