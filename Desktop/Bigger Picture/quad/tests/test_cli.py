import os
import tempfile
import json
import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from cli import config as cli_config
from cli.quad import cli as quad_cli

@pytest.fixture(autouse=True)
def mock_config_path():
    # Use a temporary config file for tests to avoid altering user settings
    fd, temp_cfg = tempfile.mkstemp(suffix="-cfg.json")
    os.close(fd)
    
    old_cfg_file = cli_config.CONFIG_FILE
    cli_config.CONFIG_FILE = temp_cfg
    
    yield
    
    cli_config.CONFIG_FILE = old_cfg_file
    if os.path.exists(temp_cfg):
        os.remove(temp_cfg)

def test_auth_login():
    runner = CliRunner()
    
    with patch("requests.post") as mock_post:
        # Mock successful response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "mock-token-xyz"}
        mock_post.return_value = mock_resp
        
        result = runner.invoke(quad_cli, ["auth", "login"], input="alice\nsecretpassword\n")
        assert result.exit_code == 0
        assert "Successfully logged in" in result.output
        
        # Verify token is saved
        cfg = cli_config.load_config()
        assert cfg["token"] == "mock-token-xyz"

def test_auth_status():
    runner = CliRunner()
    
    # 1. Not logged in
    result = runner.invoke(quad_cli, ["auth", "status"])
    assert result.exit_code == 0
    assert "Not logged in" in result.output
    
    # 2. Logged in
    cli_config.save_config({"api_url": "http://localhost:8000", "token": "test-tok"})
    result = runner.invoke(quad_cli, ["auth", "status"])
    assert result.exit_code == 0
    assert "Logged in" in result.output

def test_apps_list():
    runner = CliRunner()
    
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"name": "app1", "stack": "python", "status": "RUNNING", "owner": "alice", "internal_port": 8000}
        ]
        mock_get.return_value = mock_resp
        
        result = runner.invoke(quad_cli, ["apps", "list"])
        assert result.exit_code == 0
        assert "app1" in result.output
        assert "python" in result.output

def test_health_check():
    runner = CliRunner()
    cli_config.save_config({"api_url": "http://localhost:8000", "token": "test-tok"})
    
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "app_name": "myapp",
            "overall_score": 90,
            "grade": "A",
            "summary": {
                "total_files": 5,
                "total_loc": 200,
                "secrets_count": 0,
                "functions_over_50_lines": 0,
                "bare_excepts_count": 0,
                "empty_catches_count": 0
            },
            "file_reports": []
        }
        mock_post.return_value = mock_resp
        
        result = runner.invoke(quad_cli, ["health", "check", "myapp"])
        assert result.exit_code == 0
        assert "Health Report: myapp" in result.output
        assert "Score:  90/100" in result.output
        assert "Grade: A" in result.output
