import click
import requests
import json
from cli.config import get_api_url, get_token
from cli.output import console, print_success, print_error, print_info, poll_job

@click.group(name="ai")
def ai_group():
    """AI features (chat, ingest)."""
    pass

@ai_group.command(name="ingest")
@click.argument("app_name")
@click.option("--wait/--no-wait", default=True, help="Wait for indexing to complete")
def ai_ingest(app_name, wait):
    """Index an app's codebase for AI features."""
    api_url = get_api_url()
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    
    try:
        resp = requests.post(f"{api_url}/ai/ingest/{app_name}", headers=headers)
        if resp.status_code == 202:
            job_id = resp.json()["job_id"]
            print_info(f"Ingestion job triggered (ID: {job_id})")
            if wait:
                session = requests.Session()
                session.headers.update(headers)
                result = poll_job(session, api_url, job_id, f"Indexing '{app_name}' codebase...")
                print_success("Codebase successfully indexed and embedded!")
        else:
            print_error(resp.json().get("detail") or "Failed to start ingestion job.")
    except Exception as e:
        print_error(f"Failed to connect: {e}")

@ai_group.command(name="chat")
@click.argument("app_name")
def ai_chat(app_name):
    """Start an interactive chat session with your codebase."""
    api_url = get_api_url()
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    session = requests.Session()
    session.headers.update(headers)
    
    print_info(f"Starting interactive AI chat for '{app_name}'. Type 'exit' or 'quit' to end.")
    history = []
    
    while True:
        try:
            question = click.prompt("Question")
            if question.lower() in ["exit", "quit"]:
                break
                
            resp = session.post(f"{api_url}/ai/chat/{app_name}", json={
                "question": question,
                "history": history
            })
            
            if resp.status_code == 202:
                job_id = resp.json()["job_id"]
                result = poll_job(session, api_url, job_id, "Thinking...")
                
                answer = result.get("answer", "No response.")
                console.print(f"\n[bold green]AI:[/bold green] {answer}\n")
                
                sources = result.get("sources", [])
                if sources:
                    console.print("[bold blue]Sources cited:[/bold blue]")
                    for s in sources:
                        console.print(f"  - {s['file_path']} (lines {s['start_line']}-{s['end_line']})")
                    console.print()
                    
                # Append to history
                history.append({"role": "user", "content": question})
                history.append({"role": "assistant", "content": answer})
            else:
                print_error(resp.json().get("detail") or "Failed to query AI.")
        except click.Abort:
            console.print()
            break
        except Exception as e:
            print_error(f"Error: {e}")
            break
