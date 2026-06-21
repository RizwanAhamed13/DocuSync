# Quad Control Plane Skeleton (Step 1.1)

A minimal control-plane skeleton for Quad, a self-hosted deployment platform. Built using Python 3.11, FastAPI, Pydantic, and SQLite (standard `sqlite3` library, no ORM).

## Installation

1. Create a virtual environment (optional but recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Application

To start the FastAPI development server:
```bash
uvicorn app.main:app --reload
```

By default, this will run on `http://127.0.0.1:8000`. It initializes the SQLite database at `./quad.db` automatically on startup.

## Running Tests

To run the unit tests:
```bash
pytest
```
