import time
import json
from rich.console import Console
from rich.table import Table

console = Console()

def print_success(msg: str):
    console.print(f"[bold green]✓[/bold green] {msg}")

def print_error(msg: str):
    console.print(f"[bold red]✗ Error:[/bold red] {msg}")

def print_info(msg: str):
    console.print(f"[bold blue]i[/bold blue] {msg}")

def print_warning(msg: str):
    console.print(f"[bold yellow]⚠ Warning:[/bold yellow] {msg}")

def poll_job(session, base_url, job_id, message="Processing..."):
    with console.status(f"[bold green]{message}") as status:
        while True:
            resp = session.get(f"{base_url}/ai/jobs/{job_id}")
            if resp.status_code != 200:
                raise RuntimeError(f"Error querying job: {resp.text}")
            job = resp.json()
            job_status = job.get("status")
            if job_status == "DONE":
                result = job.get("result")
                if isinstance(result, str):
                    try:
                        return json.loads(result)
                    except Exception:
                        return result
                return result
            elif job_status == "FAILED":
                raise RuntimeError(job.get("error") or "Job failed")
            time.sleep(1)
