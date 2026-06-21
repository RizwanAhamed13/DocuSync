import click
import requests
from cli.config import get_api_url, get_token
from cli.output import print_success, print_error, print_info

@click.command(name="share")
@click.argument("app_name")
@click.argument("team_slug")
def share_command(app_name, team_slug):
    """Link a deployed application to a team project showcase."""
    api_url = get_api_url()
    token = get_token()
    if not token:
        print_error("You must be logged in to share. Run 'quad auth login'.")
        return
        
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"app_name": app_name}
    
    try:
        resp = requests.post(f"{api_url}/teams/{team_slug}/projects", json=payload, headers=headers)
        if resp.status_code in [200, 201]:
            print_success(f"Application '{app_name}' successfully linked and shared with team '{team_slug}'!")
        else:
            print_error(resp.json().get("detail") or "Failed to share application.")
    except Exception as e:
        print_error(f"Failed to connect: {e}")
