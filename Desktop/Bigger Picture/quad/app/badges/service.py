from datetime import datetime, timezone
from typing import List
from app.db import get_connection
from app.notifications.service import create_notification

# Badge metadata: badge_type -> (label, emoji)
BADGE_META = {
    "first_deploy": ("First Deploy", "🚀"),
    "dsa_10": ("10 Problems Solved", "🔟"),
    "dsa_50": ("50 Problems Solved", "💪"),
    "dsa_100": ("100 Problems Solved", "🏅"),
    "streak_7": ("7-Day Streak", "🔥"),
    "first_post": ("First Post", "📝"),
    "team_player": ("Team Player", "🤝"),
    "forked": ("Forked!", "🍴"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _award(conn, username: str, badge_type: str) -> bool:
    """Insert a badge if not already earned. Returns True if newly awarded."""
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO badges (username, badge_type, earned_at) VALUES (?, ?, ?)",
            (username, badge_type, _now()),
        )
        return cur.rowcount > 0
    except Exception:
        return False


def check_and_award(username: str, event: str, conn=None) -> List[str]:
    """Check conditions for the given event and award any newly earned badges.

    event: deploy_approved | dsa_solved | post_created | team_joined | project_forked
    Returns list of newly awarded badge_types.
    """
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    newly: List[str] = []
    try:
        if event == "deploy_approved":
            cnt = conn.execute(
                "SELECT COUNT(*) AS c FROM apps WHERE owner = ? AND approval_status = 'approved'",
                (username,),
            ).fetchone()["c"]
            if cnt >= 1 and _award(conn, username, "first_deploy"):
                newly.append("first_deploy")

        elif event == "dsa_solved":
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM dsa_submissions WHERE username = ?",
                (username,),
            ).fetchone()["c"]
            for threshold, btype in [(10, "dsa_10"), (50, "dsa_50"), (100, "dsa_100")]:
                if total >= threshold and _award(conn, username, btype):
                    newly.append(btype)
            streak = conn.execute(
                "SELECT dsa_streak FROM users WHERE username = ?", (username,)
            ).fetchone()
            if streak and streak["dsa_streak"] >= 7 and _award(conn, username, "streak_7"):
                newly.append("streak_7")

        elif event == "post_created":
            cnt = conn.execute(
                "SELECT COUNT(*) AS c FROM posts WHERE username = ?", (username,)
            ).fetchone()["c"]
            if cnt >= 1 and _award(conn, username, "first_post"):
                newly.append("first_post")

        elif event == "team_joined":
            if _award(conn, username, "team_player"):
                newly.append("team_player")

        elif event == "project_forked":
            if _award(conn, username, "forked"):
                newly.append("forked")

        if own_conn:
            conn.commit()

        # Send a notification for each new badge
        for btype in newly:
            label, emoji = BADGE_META.get(btype, (btype, "🏆"))
            create_notification(
                username,
                "badge_earned",
                "Badge earned!",
                f"{emoji} You earned the '{label}' badge",
                "/profile",
                conn=conn,
            )
        if own_conn:
            conn.commit()
    except Exception:
        pass
    finally:
        if own_conn:
            conn.close()
    return newly


def get_badges(username: str) -> List[dict]:
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT badge_type, earned_at FROM badges WHERE username = ? ORDER BY earned_at ASC",
            (username,),
        )
        out = []
        for row in cursor.fetchall():
            label, emoji = BADGE_META.get(row["badge_type"], (row["badge_type"], "🏆"))
            out.append({
                "badge_type": row["badge_type"],
                "earned_at": row["earned_at"],
                "label": label,
                "icon_emoji": emoji,
            })
        return out
    finally:
        conn.close()
