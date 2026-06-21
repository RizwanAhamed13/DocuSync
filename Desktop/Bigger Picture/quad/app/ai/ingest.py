import os
import time
import uuid
import sqlite3
from app.db import get_connection
from app.ai.embedder import Embedder
from app.ai.store import VectorStore

SUPPORTED_EXTENSIONS = {
    ".py":   "python",
    ".java": "java",
    ".js":   "javascript",
    ".ts":   "typescript",
    ".jsx":  "javascript",
    ".tsx":  "typescript",
    ".html": "html",
    ".css":  "css",
    ".sql":  "sql",
    ".md":   "text",
    ".txt":  "text",
    ".toml": "text",
    ".yaml": "text",
    ".yml":  "text",
    ".json": "text",
    ".xml":  "text",
}

SKIP_DIRS = {
    "node_modules", ".git", "target", "build",
    "dist", "__pycache__", ".venv", "venv",
    ".idea", ".vscode", "coverage", ".nyc_output"
}

MAX_FILE_SIZE_BYTES = 100_000    # skip files over 100KB
CHUNK_SIZE_LINES = 60            # target lines per chunk
CHUNK_OVERLAP_LINES = 10         # overlap between adjacent chunks

def walk_project(project_path: str) -> list[dict]:
    """
    Walk the project directory.
    Skip SKIP_DIRS and files over MAX_FILE_SIZE_BYTES.
    Skip binary files (check first 512 bytes for null bytes).
    Return list of:
    { file_path: str (relative), language: str, content: str }
    """
    files = []
    abs_project_path = os.path.abspath(project_path)
    for root, dirs, filenames in os.walk(abs_project_path):
        # Filter directories in-place
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            
            fpath = os.path.join(root, fname)
            try:
                stat = os.stat(fpath)
                if stat.st_size > MAX_FILE_SIZE_BYTES:
                    continue
                
                with open(fpath, "rb") as f:
                    chunk = f.read(512)
                    if b"\x00" in chunk:
                        continue # binary file
                    
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                
                rel_path = os.path.relpath(fpath, abs_project_path)
                files.append({
                    "file_path": rel_path,
                    "language": SUPPORTED_EXTENSIONS[ext],
                    "content": content
                })
            except Exception as e:
                print(f"Error reading {fpath}: {e}")
                
    return files

def get_symbol_name(node, content_str: str) -> str | None:
    for i in range(node.child_count()):
        child = node.child(i)
        if child.kind() == "identifier":
            return content_str[child.start_byte():child.end_byte()]
    return None

def find_symbols(node, in_symbol=False):
    symbols = []
    symbol_types = (
        "function_definition", "class_definition", 
        "class_declaration", "method_declaration", 
        "function_declaration", "method_definition", 
        "arrow_function"
    )
    is_symbol = node.kind() in symbol_types
    if is_symbol and not in_symbol:
        symbols.append(node)
        # Avoid nested symbols for main outer block definitions
        return symbols
    for i in range(node.child_count()):
        child = node.child(i)
        symbols.extend(find_symbols(child, in_symbol or is_symbol))
    return symbols

def split_lines_into_chunks(lines: list[str], start_line_idx: int, chunk_type: str, file_path: str, language: str, symbol_name: str = None) -> list[dict]:
    chunks = []
    total_lines = len(lines)
    if total_lines == 0:
        return []
        
    idx = 0
    while idx < total_lines:
        end_idx = min(idx + CHUNK_SIZE_LINES, total_lines)
        chunk_lines = lines[idx:end_idx]
        chunk_content = "\n".join(chunk_lines)
        
        chunks.append({
            "chunk_id": str(uuid.uuid4()),
            "file_path": file_path,
            "start_line": start_line_idx + idx + 1,
            "end_line": start_line_idx + end_idx,
            "chunk_type": chunk_type,
            "language": language,
            "content": chunk_content,
            "symbol_name": symbol_name
        })
        
        if end_idx == total_lines:
            break
        idx += (CHUNK_SIZE_LINES - CHUNK_OVERLAP_LINES)
        if idx >= total_lines:
            break
    return chunks

def chunk_file(file_info: dict) -> list[dict]:
    """
    Split a file into overlapping chunks using tree-sitter or line-sliding window.
    """
    file_path = file_info["file_path"]
    language = file_info["language"]
    content = file_info["content"]
    
    lines = content.splitlines()
    if not lines:
        return []
        
    # AST parsing for py, java, js, ts
    if language in ("python", "java", "javascript", "typescript"):
        try:
            from tree_sitter_language_pack import get_parser
            parser = get_parser(language)
            tree = parser.parse(content)
            root_node = tree.root_node()
            
            symbols = find_symbols(root_node)
            symbols.sort(key=lambda n: n.start_byte())
            
            chunks = []
            last_end_line = 0 # 0-indexed line index
            
            for sym in symbols:
                sym_start_line = sym.start_position().row
                sym_end_line = sym.end_position().row + 1 # exclusive line index
                
                # Block chunk before this symbol
                if sym_start_line > last_end_line:
                    block_lines = lines[last_end_line:sym_start_line]
                    chunks.extend(split_lines_into_chunks(block_lines, last_end_line, "block", file_path, language))
                
                # Symbol chunk
                sym_lines = lines[sym_start_line:sym_end_line]
                sym_kind = sym.kind()
                sym_type = "class" if "class" in sym_kind else "function"
                sym_name = get_symbol_name(sym, content)
                chunks.extend(split_lines_into_chunks(sym_lines, sym_start_line, sym_type, file_path, language, sym_name))
                
                last_end_line = sym_end_line
                
            # Final block chunk after last symbol
            if last_end_line < len(lines):
                block_lines = lines[last_end_line:]
                chunks.extend(split_lines_into_chunks(block_lines, last_end_line, "block", file_path, language))
                
            return chunks
        except Exception as e:
            # Fall back to sliding window on AST error
            print(f"AST parsing failed for {file_path}, falling back to sliding window: {e}")
            
    # Default sliding window for text/other languages
    return split_lines_into_chunks(lines, 0, "file", file_path, language)

def ingest_project(app_name: str, project_path: str) -> dict:
    """
    Full ingestion pipeline for one project.
    """
    start_time = time.time()
    files = walk_project(project_path)
    
    all_chunks = []
    file_count = 0
    for idx, f_info in enumerate(files):
        file_chunks = chunk_file(f_info)
        all_chunks.extend(file_chunks)
        file_count += 1
        if (idx + 1) % 10 == 0:
            print(f"Ingested {idx + 1} files...")
            
    # Embed chunks in batches of 32
    embedder = Embedder.get()
    chunk_ids = []
    embeddings = []
    documents = []
    metadatas = []
    
    batch_size = 32
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i+batch_size]
        batch_texts = [c["content"] for c in batch]
        try:
            batch_embeddings = embedder.embed(batch_texts)
            for j, c in enumerate(batch):
                chunk_ids.append(c["chunk_id"])
                embeddings.append(batch_embeddings[j])
                documents.append(c["content"])
                metadatas.append({
                    "app_name": app_name,
                    "file_path": c["file_path"],
                    "start_line": c["start_line"],
                    "end_line": c["end_line"],
                    "chunk_type": c["chunk_type"],
                    "language": c["language"],
                    "symbol_name": c["symbol_name"] or ""
                })
        except Exception as e:
            print(f"Error embedding batch {i}: {e}")
            
    # Clean up existing database entry/collection
    delete_project_index(app_name)
    
    # Store to ChromaDB
    if chunk_ids:
        try:
            VectorStore.upsert_chunks(
                app_name=app_name,
                chunk_ids=chunk_ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
        except Exception as e:
            print(f"Error saving to vector store: {e}")
            
        # Store metadata to SQLite
        conn = get_connection()
        try:
            cursor = conn.cursor()
            now_str = time.strftime("%Y-%m-%d %H:%M:%S")
            for c in all_chunks:
                cursor.execute("""
                    INSERT INTO code_chunks (
                        app_name, chunk_id, file_path, start_line, end_line,
                        chunk_type, language, content, symbol_name, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    app_name, c["chunk_id"], c["file_path"], c["start_line"], c["end_line"],
                    c["chunk_type"], c["language"], c["content"], c["symbol_name"], now_str
                ))
            conn.commit()
        except Exception as e:
            print(f"Error saving chunks to SQLite: {e}")
        finally:
            conn.close()
            
    duration = time.time() - start_time
    return {
        "files_indexed": file_count,
        "chunks_indexed": len(all_chunks),
        "duration_seconds": round(duration, 2)
    }

def delete_project_index(app_name: str) -> None:
    """
    Remove all code_chunks for app_name from SQLite and delete vector collection.
    """
    conn = get_connection()
    try:
        conn.execute("DELETE FROM code_chunks WHERE app_name = ?", (app_name,))
        conn.commit()
    except Exception as e:
        print(f"Error deleting code_chunks from SQLite: {e}")
    finally:
        conn.close()
        
    VectorStore.delete_collection(app_name)
