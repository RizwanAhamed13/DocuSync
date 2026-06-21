import click
import requests
from cli.config import load_config, save_config, get_api_url
from cli.output import print_success, print_error, print_info

@click.group(name="auth")
def auth_group():
    """Manage authentication (login, register, logout, status)."""
    pass

@auth_group.command(name="login")
@click.option("--username", prompt=True, help="Username or Email")
@click.option("--password", prompt=True, hide_input=True, help="Password")
def auth_login(username, password):
    """Log in to Quad and save authentication token."""
    api_url = get_api_url()
    try:
        resp = requests.post(f"{api_url}/auth/login", json={
            "username_or_email": username,
            "password": password
        })
        if resp.status_code == 200:
            token = resp.json()["access_token"]
            cfg = load_config()
            cfg["token"] = token
            save_config(cfg)
            print_success(f"Successfully logged in as '{username}'.")
        else:
            print_error(resp.json().get("detail") or "Invalid credentials")
    except Exception as e:
        print_error(f"Failed to connect to control plane: {e}")

@auth_group.command(name="register")
@click.option("--username", prompt=True, help="Username")
@click.option("--email", prompt=True, help="Email address")
@click.option("--password", prompt=True, hide_input=True, help="Password")
def auth_register(username, email, password):
    """Register a new student account on Quad."""
    api_url = get_api_url()
    try:
        resp = requests.post(f"{api_url}/auth/register", json={
            "username": username,
            "email": email,
            "password": password
        })
        if resp.status_code == 201:
            print_success(f"Account '{username}' registered successfully! Run 'quad auth login' to log in.")
        else:
            print_error(resp.json().get("detail") or "Registration failed")
    except Exception as e:
        print_error(f"Failed to connect to control plane: {e}")

@auth_group.command(name="logout")
def auth_logout():
    """Clear authentication token from configuration."""
    cfg = load_config()
    cfg["token"] = None
    save_config(cfg)
    print_success("Successfully logged out.")

@auth_group.command(name="status")
def auth_status():
    """Check current authentication status."""
    cfg = load_config()
    token = cfg.get("token")
    if token:
        print_info(f"Logged in. Control plane URL: {cfg['api_url']}")
    else:
        print_info(f"Not logged in. Control plane URL: {cfg['api_url']}")
