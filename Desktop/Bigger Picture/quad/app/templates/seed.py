import os
import zipfile
from datetime import datetime, timezone
from app.db import get_connection

TEMPLATES_DIR = "templates"

TEMPLATES = [
    {
        "slug": "fastapi-starter",
        "name": "FastAPI + SQLite starter",
        "description": "A minimal FastAPI app with a SQLite-backed health endpoint.",
        "stack": "Python",
        "files": {
            "main.py": (
                "from fastapi import FastAPI\n\n"
                "app = FastAPI()\n\n"
                "@app.get('/')\n"
                "def root():\n"
                "    return {'message': 'Hello from FastAPI starter'}\n"
            ),
            "requirements.txt": "fastapi\nuvicorn\n",
            "README.md": "# FastAPI Starter\n\nRun with: uvicorn main:app --reload\n",
        },
    },
    {
        "slug": "react-vite",
        "name": "React + Vite + Tailwind",
        "description": "A React single-page app scaffolded with Vite and Tailwind CSS.",
        "stack": "Node",
        "files": {
            "package.json": (
                '{\n  "name": "react-vite-app",\n  "scripts": {\n'
                '    "dev": "vite",\n    "build": "vite build"\n  }\n}\n'
            ),
            "index.html": "<!doctype html><html><body><div id='root'></div></body></html>\n",
            "README.md": "# React + Vite + Tailwind\n\nRun with: npm install && npm run dev\n",
        },
    },
    {
        "slug": "flask-app",
        "name": "Flask web app",
        "description": "A simple Flask web application with one route.",
        "stack": "Python",
        "files": {
            "app.py": (
                "from flask import Flask\n\n"
                "app = Flask(__name__)\n\n"
                "@app.route('/')\n"
                "def home():\n"
                "    return 'Hello from Flask'\n\n"
                "if __name__ == '__main__':\n"
                "    app.run(host='0.0.0.0', port=5000)\n"
            ),
            "requirements.txt": "flask\n",
            "README.md": "# Flask App\n\nRun with: python app.py\n",
        },
    },
    {
        "slug": "express-api",
        "name": "Express.js REST API",
        "description": "A REST API skeleton built with Express.js.",
        "stack": "Node",
        "files": {
            "package.json": (
                '{\n  "name": "express-api",\n  "main": "server.js",\n'
                '  "scripts": { "start": "node server.js" },\n'
                '  "dependencies": { "express": "^4.18.0" }\n}\n'
            ),
            "server.js": (
                "const express = require('express');\n"
                "const app = express();\n"
                "app.get('/', (req, res) => res.json({ message: 'Express API' }));\n"
                "app.listen(3000, () => console.log('Listening on 3000'));\n"
            ),
            "README.md": "# Express REST API\n\nRun with: npm install && npm start\n",
        },
    },
    {
        "slug": "fullstack",
        "name": "FastAPI backend + React frontend",
        "description": "A fullstack starter pairing a FastAPI backend with a React frontend.",
        "stack": "Python+Node",
        "files": {
            "backend/main.py": (
                "from fastapi import FastAPI\n\n"
                "app = FastAPI()\n\n"
                "@app.get('/api/ping')\n"
                "def ping():\n"
                "    return {'pong': True}\n"
            ),
            "backend/requirements.txt": "fastapi\nuvicorn\n",
            "frontend/index.html": "<!doctype html><html><body><h1>Fullstack</h1></body></html>\n",
            "README.md": "# Fullstack Starter\n\nFastAPI backend + React frontend.\n",
        },
    },
]


def _build_zip(tpl: dict) -> str:
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    zip_path = os.path.join(TEMPLATES_DIR, f"{tpl['slug']}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path, content in tpl["files"].items():
            zf.writestr(rel_path, content)
    return zip_path


def seed_templates():
    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    try:
        for tpl in TEMPLATES:
            _build_zip(tpl)
            conn.execute(
                """
                INSERT OR IGNORE INTO templates
                (slug, name, description, stack, created_by, is_public, created_at)
                VALUES (?, ?, ?, ?, 'system', 1, ?)
                """,
                (tpl["slug"], tpl["name"], tpl["description"], tpl["stack"], now),
            )
        conn.commit()
    finally:
        conn.close()
