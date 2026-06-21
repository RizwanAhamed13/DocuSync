import os
import zipfile
import tempfile
import click
import requests
from cli.config import get_api_url, get_token
from cli.output import console, print_success, print_error, print_info

@click.command(name="deploy")
@click.argument("app_name", required=False)
def deploy_command(app_name):
    """Package the current directory and deploy it to Quad."""
    if not app_name:
        app_name = os.path.basename(os.getcwd()).lower()
        # Clean app name to be valid: alphanumeric and hyphens only
        app_name = "".join(c if c.isalnum() or c == "-" else "-" for c in app_name)
        app_name = app_name.strip("-")
        
    api_url = get_api_url()
    token = get_token()
    if not token:
        print_error("You must be logged in to deploy. Run 'quad auth login'.")
        return
        
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Zip files
    print_info(f"Packaging codebase for application '{app_name}'...")
    fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    
    ignore_dirs = {".git", "node_modules", "venv", "__pycache__", ".pytest_cache", ".gemini", "projects_source", "projects"}
    
    try:
        with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zip_ref:
            for root, dirs, files in os.walk("."):
                # Exclude ignored dirs in-place
                dirs[:] = [d for d in dirs if d not in ignore_dirs]
                for file in files:
                    file_path = os.path.join(root, file)
                    # Exclude the temporary zip itself if it is in the same directory
                    if os.path.abspath(file_path) == os.path.abspath(temp_zip_path):
                        continue
                    arcname = os.path.relpath(file_path, ".")
                    zip_ref.write(file_path, arcname=arcname)
                    
        # 2. Upload zip
        print_info("Uploading bundle to control plane...")
        with open(temp_zip_path, "rb") as f:
            resp = requests.post(
                f"{api_url}/deploy/upload?name={app_name}",
                headers=headers,
                files={"file": (f"{app_name}.zip", f, "application/zip")}
            )
            
        if resp.status_code in [200, 202]:
            print_success(f"Deployment uploaded and build pipeline triggered for '{app_name}'!")
            # Print logs URL
            print_info(f"Logs: {api_url}/deploy/{app_name}/logs")
        else:
            print_error(resp.json().get("detail") or resp.text)
    except Exception as e:
        print_error(f"Deployment failed: {e}")
    finally:
        if os.path.exists(temp_zip_path):
            os.remove(temp_zip_path)
