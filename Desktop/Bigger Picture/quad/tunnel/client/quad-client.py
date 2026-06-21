import argparse
import getpass
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import requests

def find_frpc() -> str:
    path = shutil.which("frpc")
    if path:
        return path
    if os.path.exists("./frpc"):
        return "./frpc"
    raise RuntimeError("frpc not found — download from https://github.com/fatedier/frp/releases")

def ping_loop(server_url: str, tunnel_id: str, stop_event: threading.Event):
    while not stop_event.is_set():
        try:
            r = requests.post(f"{server_url}/tunnels/{tunnel_id}/ping")
            if r.status_code != 200:
                pass
        except Exception:
            pass
        # Sleep in 1s increments to respond quickly to stop_event
        for _ in range(30):
            if stop_event.is_set():
                break
            time.sleep(1)

def main():
    parser = argparse.ArgumentParser(description="Quad Tunnel Client")
    parser.add_argument("--port", type=int, required=True, help="Local port to expose")
    parser.add_argument("--name", type=str, required=True, help="App / Tunnel name")
    parser.add_argument("--server", type=str, default="http://quad.localhost:8000", help="Quad server URL")
    parser.add_argument("--owner", type=str, default=getpass.getuser(), help="Owner username")
    parser.add_argument("--token", type=str, default=os.getenv("QUAD_FRP_TOKEN"), help="FRP token")
    
    args = parser.parse_args()
    
    token = args.token or os.getenv("FRP_TOKEN") or "changeme-set-in-env"
    
    try:
        frpc_bin = find_frpc()
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
        
    print(f"Connecting to Quad server at {args.server}...")
    
    try:
        payload = {
            "app_name": args.name,
            "local_port": args.port,
            "owner": args.owner
        }
        r = requests.post(f"{args.server}/tunnels/open", json=payload)
        if r.status_code != 201:
            print(f"Error: Server returned HTTP {r.status_code}: {r.json()}")
            sys.exit(1)
        resp_data = r.json()
    except Exception as e:
        print(f"Failed to communicate with server: {e}")
        sys.exit(1)
        
    tunnel_id = resp_data["tunnel_id"]
    public_url = resp_data["public_url"]
    frpc_config = resp_data["frpc_config"]
    
    # Write config to temp file
    temp_fd, temp_path = tempfile.mkstemp(suffix=".toml", prefix="frpc-")
    os.close(temp_fd)
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(frpc_config)
        
    print(f"\n==================================================")
    print(f"  Tunnel is open!")
    print(f"  Live at: {public_url}")
    print(f"==================================================\n")
    
    stop_event = threading.Event()
    ping_thread = threading.Thread(
        target=ping_loop, 
        args=(args.server, tunnel_id, stop_event), 
        daemon=True
    )
    ping_thread.start()
    
    cmd = [frpc_bin, "-c", temp_path]
    proc = None
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(1)
        if proc.poll() is not None:
            stdout, stderr = proc.communicate()
            err_text = stderr.decode()
            if "unknown command" in err_text or "run" in err_text:
                cmd = [frpc_bin, "run", "-c", temp_path]
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            else:
                print(f"frpc exited with code {proc.returncode}. Error: {err_text}")
                os.remove(temp_path)
                sys.exit(1)
                
        while proc.poll() is None:
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\nStopping tunnel...")
    finally:
        stop_event.set()
        ping_thread.join(timeout=2)
        
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                
        try:
            requests.post(f"{args.server}/tunnels/{tunnel_id}/close")
            print("Tunnel closed on server.")
        except Exception as e:
            print(f"Failed to close tunnel on server: {e}")
            
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        print("Cleanup complete. Goodbye!")

if __name__ == "__main__":
    main()
