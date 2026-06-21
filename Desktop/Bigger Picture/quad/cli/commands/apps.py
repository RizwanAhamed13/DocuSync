import click
import requests
from rich.table import Table
from cli.config import load_config, get_api_url, get_token
from cli.output import console, print_success, print_error, print_info

@click.group(name="apps")
def apps_group():
    """Manage application resources."""
    pass

@apps_group.command(name="list")
def apps_list():
    """List all deployed applications."""
    api_url = get_api_url()
    try:
        resp = requests.get(f"{api_url}/apps")
        if resp.status_code == 200:
            apps = resp.json()
            if not apps:
                print_info("No applications found.")
                return
                
            table = Table(title="Deployed Applications")
            table.add_column("Name", style="cyan", no_wrap=True)
            table.add_column("Stack", style="magenta")
            table.add_column("Status", style="green")
            table.add_column("Owner", style="yellow")
            table.add_column("Port", style="blue")
            
            for app in apps:
                table.add_row(
                    app.get("name", "N/A"),
                    app.get("stack", "N/A"),
                    app.get("status", "STOPPED"),
                    app.get("owner", "N/A"),
                    str(app.get("internal_port", "N/A"))
                )
            console.print(table)
        else:
            print_error("Failed to retrieve apps.")
    except Exception as e:
        print_error(f"Failed to connect to control plane: {e}")

@apps_group.command(name="create")
@click.argument("name")
@click.argument("stack")
def apps_create(name, stack):
    """Create a new application slot."""
    api_url = get_api_url()
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        resp = requests.post(f"{api_url}/apps", json={"name": name, "stack": stack}, headers=headers)
        if resp.status_code == 200:
            print_success(f"Application '{name}' of stack '{stack}' created successfully.")
        elif resp.status_code == 409:
            print_error(f"App with name '{name}' already exists.")
        else:
            print_error(resp.json().get("detail") or "Failed to create app.")
    except Exception as e:
        print_error(f"Failed to connect: {e}")

@apps_group.command(name="delete")
@click.argument("name")
def apps_delete(name):
    """Delete an application resource."""
    api_url = get_api_url()
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        resp = requests.delete(f"{api_url}/deploy/{name}", headers=headers)
        if resp.status_code in [200, 204]:
            print_success(f"Application '{name}' deleted successfully.")
        else:
            print_error(resp.json().get("detail") or f"Failed to delete application '{name}'.")
    except Exception as e:
        print_error(f"Failed to connect: {e}")
