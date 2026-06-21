import sqlite3
from . import config

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS apps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                stack TEXT,
                status TEXT NOT NULL DEFAULT 'STOPPED',
                container_id TEXT,
                image_tag TEXT,
                internal_port INTEGER,
                max_wake_seconds INTEGER DEFAULT 10,
                last_seen TEXT,
                created_at TEXT NOT NULL,
                build_log_path TEXT,
                owner TEXT,
                visibility TEXT NOT NULL DEFAULT 'public',
                description TEXT,
                tags TEXT,
                view_count INTEGER NOT NULL DEFAULT 0,
                upvote_count INTEGER NOT NULL DEFAULT 0
            );
        """)
        
        # Alter columns if existing apps table lacks them
        for col_name, col_type in [
            ("owner", "TEXT"),
            ("visibility", "TEXT NOT NULL DEFAULT 'public'"),
            ("description", "TEXT"),
            ("tags", "TEXT"),
            ("view_count", "INTEGER NOT NULL DEFAULT 0"),
            ("upvote_count", "INTEGER NOT NULL DEFAULT 0"),
            ("pid", "INTEGER"),
            ("process_port", "INTEGER"),
            ("approval_status", "TEXT NOT NULL DEFAULT 'pending'")
        ]:
            try:
                conn.execute(f"ALTER TABLE apps ADD COLUMN {col_name} {col_type};")
            except sqlite3.OperationalError:
                pass

        # Users table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                avatar_initial TEXT,
                role TEXT NOT NULL DEFAULT 'student',
                college TEXT,
                department TEXT,
                year_of_study INTEGER,
                bio TEXT,
                github_url TEXT,
                linkedin_url TEXT,
                created_at TEXT NOT NULL,
                last_login TEXT,
                dsa_streak INTEGER NOT NULL DEFAULT 0,
                dsa_streak_updated TEXT,
                dsa_total_solved INTEGER NOT NULL DEFAULT 0,
                leetcode_username TEXT
            );
        """)

        # Alter user columns for safety/migration if table exists
        for col_name, col_type in [
            ("dsa_streak", "INTEGER NOT NULL DEFAULT 0"),
            ("dsa_streak_updated", "TEXT"),
            ("dsa_total_solved", "INTEGER NOT NULL DEFAULT 0"),
            ("leetcode_username", "TEXT")
        ]:
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type};")
            except sqlite3.OperationalError:
                pass

        # Sessions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                token_jti TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
        """)

        # Tunnels table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tunnels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tunnel_id TEXT UNIQUE NOT NULL,
                app_name TEXT NOT NULL,
                owner TEXT NOT NULL,
                local_port INTEGER NOT NULL,
                subdomain TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                frpc_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_ping TEXT
            );
        """)

        # Teams table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                description TEXT,
                owner_username TEXT NOT NULL,
                visibility TEXT NOT NULL DEFAULT 'private',
                created_at TEXT NOT NULL
            );
        """)

        # Team members table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS team_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_slug TEXT NOT NULL REFERENCES teams(slug),
                username TEXT NOT NULL REFERENCES users(username),
                role TEXT NOT NULL DEFAULT 'member',
                joined_at TEXT NOT NULL,
                UNIQUE(team_slug, username)
            );
        """)

        # Project teams table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_name TEXT NOT NULL REFERENCES apps(name),
                team_slug TEXT NOT NULL REFERENCES teams(slug),
                added_at TEXT NOT NULL,
                UNIQUE(app_name, team_slug)
            );
        """)

        # Forks table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS forks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_app TEXT NOT NULL REFERENCES apps(name),
                forked_app TEXT NOT NULL REFERENCES apps(name),
                forked_by TEXT NOT NULL REFERENCES users(username),
                forked_at TEXT NOT NULL,
                UNIQUE(original_app, forked_by)
            );
        """)

        # Activity events table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                event_type TEXT NOT NULL,
                target_type TEXT,
                target_name TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL
            );
        """)

        # Upvotes table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS upvotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_name TEXT NOT NULL REFERENCES apps(name),
                username TEXT NOT NULL REFERENCES users(username),
                created_at TEXT NOT NULL,
                UNIQUE(app_name, username)
            );
        """)

        # App views table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_name TEXT NOT NULL REFERENCES apps(name),
                viewer_ip TEXT,
                viewed_at TEXT NOT NULL
            );
        """)

        # DSA Submissions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dsa_submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL REFERENCES users(username),
                problem_slug TEXT NOT NULL,
                problem_title TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                platform TEXT NOT NULL DEFAULT 'leetcode',
                solved_at TEXT NOT NULL,
                notes TEXT,
                UNIQUE(username, problem_slug)
            );
        """)

        # Code chunks table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS code_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_name TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL,
                chunk_type TEXT NOT NULL,
                language TEXT NOT NULL,
                content TEXT NOT NULL,
                symbol_name TEXT,
                indexed_at TEXT NOT NULL,
                UNIQUE(app_name, chunk_id)
            );
        """)

        # AI jobs table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT UNIQUE NOT NULL,
                app_name TEXT NOT NULL,
                username TEXT NOT NULL,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'QUEUED',
                input TEXT NOT NULL,
                result TEXT,
                error TEXT,
                queued_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                cache_key TEXT
            );
        """)

        # Assignments table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                assignment_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                created_by TEXT NOT NULL,
                course_code TEXT,
                batch TEXT,
                deadline TEXT,
                max_score INTEGER DEFAULT 100,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL
            );
        """)

        # Submissions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id TEXT UNIQUE NOT NULL,
                assignment_id TEXT NOT NULL REFERENCES assignments(assignment_id),
                student_username TEXT,
                student_name TEXT NOT NULL,
                roll_number TEXT,
                submitted_at TEXT NOT NULL,
                zip_path TEXT NOT NULL,
                extracted_path TEXT,
                app_name TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                score INTEGER,
                feedback TEXT
            );
        """)

        # Submission analysis table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS submission_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id TEXT NOT NULL REFERENCES submissions(submission_id),
                ai_summary TEXT,
                detected_stack TEXT,
                file_count INTEGER,
                line_count INTEGER,
                issues TEXT,
                missing_features TEXT,
                hardcoded_secrets INTEGER DEFAULT 0,
                missing_error_handling INTEGER DEFAULT 0,
                code_quality_score INTEGER,
                similarity_scores TEXT,
                plagiarism_flag INTEGER DEFAULT 0,
                similarity_threshold REAL DEFAULT 0.75,
                analyzed_at TEXT NOT NULL
            );
        """)

        # Hackathons table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hackathons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hackathon_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                theme TEXT,
                organizer_username TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                max_team_size INTEGER DEFAULT 4,
                min_team_size INTEGER DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'upcoming',
                judging_criteria TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)

        # Hack teams table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hack_teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hack_team_id TEXT UNIQUE NOT NULL,
                hackathon_id TEXT NOT NULL REFERENCES hackathons(hackathon_id),
                team_name TEXT NOT NULL,
                members TEXT NOT NULL,
                leader_username TEXT NOT NULL,
                app_name TEXT,
                tunnel_id TEXT,
                project_title TEXT,
                project_description TEXT,
                submitted_at TEXT,
                demo_url TEXT,
                repo_url TEXT,
                UNIQUE(hackathon_id, team_name)
            );
        """)

        # Hack scores table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hack_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hack_team_id TEXT NOT NULL REFERENCES hack_teams(hack_team_id),
                judge_username TEXT NOT NULL,
                criterion TEXT NOT NULL,
                score INTEGER NOT NULL,
                comment TEXT,
                scored_at TEXT NOT NULL,
                UNIQUE(hack_team_id, judge_username, criterion)
            );
        """)

        # Health reports table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS health_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT UNIQUE NOT NULL,
                app_name TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                summary TEXT NOT NULL,
                file_reports TEXT NOT NULL,
                overall_score INTEGER NOT NULL,
                grade TEXT NOT NULL
            );
        """)

        # Rate limiting log table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_limit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL,
                path TEXT NOT NULL,
                method TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                duration REAL NOT NULL,
                request_id TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Security events table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT,
                event TEXT NOT NULL,
                detail TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # DSA questions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dsa_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                examples TEXT NOT NULL,
                constraints TEXT NOT NULL,
                starter_code_python TEXT NOT NULL,
                starter_code_js TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)

        # DSA test cases table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dsa_test_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_slug TEXT NOT NULL REFERENCES dsa_questions(slug),
                input TEXT NOT NULL,
                expected_output TEXT NOT NULL,
                is_hidden INTEGER NOT NULL DEFAULT 0,
                order_index INTEGER NOT NULL DEFAULT 0
            );
        """)

        # Social posts table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                content TEXT NOT NULL,
                code_snippet TEXT,
                language TEXT,
                project_name TEXT,
                post_type TEXT NOT NULL DEFAULT 'text',
                likes_count INTEGER NOT NULL DEFAULT 0,
                comments_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
        """)

        # Post likes table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS post_likes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT NOT NULL REFERENCES posts(post_id),
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(post_id, username)
            );
        """)

        # Post comments table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS post_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                comment_id TEXT UNIQUE NOT NULL,
                post_id TEXT NOT NULL REFERENCES posts(post_id),
                username TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)

        # Notifications table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notification_id TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                link TEXT,
                read INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
        """)

        # Badges table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS badges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                badge_type TEXT NOT NULL,
                earned_at TEXT NOT NULL,
                UNIQUE(username, badge_type)
            );
        """)

        # Templates table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                stack TEXT NOT NULL,
                created_by TEXT NOT NULL,
                is_public INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
        """)

        # Devlogs table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS devlogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_id TEXT UNIQUE NOT NULL,
                app_name TEXT NOT NULL,
                author TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                published INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)

        conn.commit()
    finally:
        conn.close()
async def log_rate_limit(ip: str, path: str, method: str, status_code: int, duration: float, request_id: str):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO rate_limit_log (ip, path, method, status_code, duration, request_id) VALUES (?, ?, ?, ?, ?, ?)",
            (ip, path, method, status_code, duration, request_id),
        )
        conn.commit()
    finally:
        conn.close()

