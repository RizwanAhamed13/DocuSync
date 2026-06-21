import os
import json

CONFIG_DIR = os.path.expanduser("~/.quad")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return {"api_url": "http://localhost:8000", "token": None}
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            if "api_url" not in data:
                data["api_url"] = "http://localhost:8000"
            return data
    except Exception:
        return {"api_url": "http://localhost:8000", "token": None}

def save_config(config_dict: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config_dict, f, indent=2)

def get_token() -> str | None:
    return load_config().get("token")

def get_api_url() -> str:
    return load_config().get("api_url", "http://localhost:8000")
