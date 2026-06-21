import os
import re
import zipfile
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.auth.dependencies import get_current_user
from app.db import get_connection
from app.repository import create_app, get_app, set_approval_status, update_status

router = APIRouter(prefix="/templates", tags=["templates"])

TEMPLATES_DIR = "templates"
PROJECTS_DIR = "projects"


class DeployTemplate(BaseModel):
    app_name: str


@router.get("")
def list_templates():
    conn = get_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM templates WHERE is_public = 1 ORDER BY id ASC"
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


@router.post("/{slug}/deploy", status_code=status.HTTP_201_CREATED)
def deploy_template(slug: str, payload: DeployTemplate, current_user: dict = Depends(get_current_user)):
    name = payload.app_name.strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,38}[a-z0-9]", name or ""):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid app name. Use lowercase letters, digits and hyphens.",
        )

    conn = get_connection()
    try:
        tpl = conn.execute("SELECT * FROM templates WHERE slug = ?", (slug,)).fetchone()
    finally:
        conn.close()
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    if get_app(name) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"App name '{name}' is already taken.",
        )

    zip_path = os.path.join(TEMPLATES_DIR, f"{slug}.zip")
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Template files missing")

    dest_dir = os.path.join(PROJECTS_DIR, name)
    os.makedirs(dest_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest_dir)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Failed to extract template: {e}")

    stack = tpl["stack"]
    create_app(name, stack=stack, owner=current_user["sub"])
    update_status(name, "PENDING_APPROVAL")
    set_approval_status(name, "pending")

    return {
        "app_name": name,
        "slug": slug,
        "status": "PENDING_APPROVAL",
        "approval_status": "pending",
    }


@router.get("/{slug}/files")
def preview_template_files(slug: str):
    zip_path = os.path.join(TEMPLATES_DIR, f"{slug}.zip")
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="Template not found")
    
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            files = []
            for name in zf.namelist():
                if not name.endswith("/"):
                    # skip metadata folders if any (like __MACOSX)
                    if not name.startswith("__MACOSX"):
                        files.append({"path": name, "type": "file"})
            return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{slug}/file")
def preview_template_file(slug: str, path: str):
    zip_path = os.path.join(TEMPLATES_DIR, f"{slug}.zip")
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="Template not found")
    
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            try:
                content = zf.read(path).decode("utf-8", errors="replace")
                return {"content": content, "path": path}
            except KeyError:
                raise HTTPException(status_code=404, detail="File not found in template")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

