from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import os
import pty

router = APIRouter(prefix="/terminal", tags=["terminal"])


@router.websocket("/ws/{app_name}")
async def terminal_ws(websocket: WebSocket, app_name: str):
    await websocket.accept()
    # Open a PTY shell in the project directory
    project_dir = os.path.join("projects", app_name)
    if not os.path.exists(project_dir):
        project_dir = os.getcwd()

    master_fd, slave_fd = pty.openpty()
    process = await asyncio.create_subprocess_exec(
        "/bin/bash",
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
        cwd=project_dir,
        env={**os.environ, "TERM": "xterm-256color"},
    )
    os.close(slave_fd)

    async def read_pty():
        loop = asyncio.get_event_loop()
        while True:
            try:
                data = await loop.run_in_executor(None, lambda: os.read(master_fd, 1024))
                if not data:
                    break
                await websocket.send_bytes(data)
            except (OSError, WebSocketDisconnect):
                break

    reader = asyncio.create_task(read_pty())
    try:
        while True:
            msg = await websocket.receive()
            if "bytes" in msg and msg["bytes"] is not None:
                os.write(master_fd, msg["bytes"])
            elif "text" in msg and msg["text"] is not None:
                os.write(master_fd, msg["text"].encode())
    except WebSocketDisconnect:
        pass
    finally:
        reader.cancel()
        try:
            process.kill()
        except Exception:
            pass
        try:
            os.close(master_fd)
        except Exception:
            pass
