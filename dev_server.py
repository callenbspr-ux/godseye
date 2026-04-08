#!/usr/bin/env python3
"""
GODSEYE Local Development Server
==================================
Serves the dashboard locally so you can iterate without pushing to GitHub.

Usage:
    cd /path/to/godseye
    python3 dev_server.py

Then open: http://localhost:8181

Endpoints:
    /                       → serves index.html
    /data/...               → serves data JSON files
    /api/run-pipeline       → runs fetch_live_data.py (POST)
    /api/run-mirofish       → runs mirofish_sim.py (POST)
    /api/run-all            → runs mirofish_sim.py then fetch_live_data.py (POST)
    /api/status             → returns server + last run status (GET)
"""

import http.server
import socketserver
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

PORT = 8181
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Shared state ──────────────────────────────────────────────────────────────
state = {
    "last_pipeline_run": None,
    "last_mirofish_run": None,
    "pipeline_running": False,
    "mirofish_running": False,
    "last_output": "",
    "server_started": datetime.now(timezone.utc).isoformat(),
}


def run_script(script_name, state_key_running, state_key_time):
    """Run a Python script as a subprocess and capture output."""
    script_path = os.path.join(SCRIPT_DIR, script_name)
    if not os.path.exists(script_path):
        return False, f"Script not found: {script_path}"

    state[state_key_running] = True
    state["last_output"] = f"Running {script_name}..."
    start = time.time()

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=SCRIPT_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        elapsed = round(time.time() - start, 1)
        output = result.stdout + (("\n[STDERR]\n" + result.stderr) if result.stderr else "")
        state["last_output"] = f"[{script_name}] Done in {elapsed}s\n\n" + output
        state[state_key_time] = datetime.now(timezone.utc).isoformat()

        success = result.returncode == 0
        return success, state["last_output"]

    except subprocess.TimeoutExpired:
        state["last_output"] = f"[{script_name}] Timed out after 120s"
        return False, state["last_output"]
    except Exception as e:
        state["last_output"] = f"[{script_name}] Error: {e}"
        return False, state["last_output"]
    finally:
        state[state_key_running] = False


class GODSEYEHandler(http.server.SimpleHTTPRequestHandler):
    """Custom handler: serves static files + /api/* endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SCRIPT_DIR, **kwargs)

    def log_message(self, format, *args):
        # Quiet most static file requests, show API calls
        if "/api/" in args[0] if args else "":
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] {format % args}")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            self._json({
                "ok": True,
                "server_started": state["server_started"],
                "last_pipeline_run": state["last_pipeline_run"],
                "last_mirofish_run": state["last_mirofish_run"],
                "pipeline_running": state["pipeline_running"],
                "mirofish_running": state["mirofish_running"],
                "last_output": state["last_output"][-2000:],  # Last 2000 chars
                "data_exists": os.path.exists(os.path.join(SCRIPT_DIR, "data", "live_data.json")),
                "debates_exists": os.path.exists(os.path.join(SCRIPT_DIR, "data", "mirofish_debates.json")),
            })
            return

        # Serve index.html for root
        if path == "/":
            self.path = "/index.html"

        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/run-pipeline":
            if state["pipeline_running"]:
                self._json({"ok": False, "message": "Pipeline already running"}, 409)
                return
            print(f"\n  🔄  Running pipeline... [{datetime.now().strftime('%H:%M:%S')}]")
            def run():
                run_script("fetch_live_data.py", "pipeline_running", "last_pipeline_run")
                print(f"  ✅  Pipeline done [{datetime.now().strftime('%H:%M:%S')}]")
            threading.Thread(target=run, daemon=True).start()
            self._json({"ok": True, "message": "Pipeline started"})
            return

        if path == "/api/run-mirofish":
            if state["mirofish_running"]:
                self._json({"ok": False, "message": "MiroFish sim already running"}, 409)
                return
            print(f"\n  🐟  Running MiroFish sim... [{datetime.now().strftime('%H:%M:%S')}]")
            def run():
                run_script("mirofish_sim.py", "mirofish_running", "last_mirofish_run")
                print(f"  ✅  MiroFish done [{datetime.now().strftime('%H:%M:%S')}]")
            threading.Thread(target=run, daemon=True).start()
            self._json({"ok": True, "message": "MiroFish sim started"})
            return

        if path == "/api/run-all":
            if state["pipeline_running"] or state["mirofish_running"]:
                self._json({"ok": False, "message": "Already running"}, 409)
                return
            print(f"\n  🚀  Running full pipeline (MiroFish + data)... [{datetime.now().strftime('%H:%M:%S')}]")
            def run():
                run_script("mirofish_sim.py", "mirofish_running", "last_mirofish_run")
                run_script("fetch_live_data.py", "pipeline_running", "last_pipeline_run")
                print(f"  ✅  Full pipeline done [{datetime.now().strftime('%H:%M:%S')}]")
            threading.Thread(target=run, daemon=True).start()
            self._json({"ok": True, "message": "Full pipeline started"})
            return

        self._json({"ok": False, "message": "Unknown endpoint"}, 404)

    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def main():
    os.chdir(SCRIPT_DIR)

    print("=" * 56)
    print("  GODSEYE Local Dev Server")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 56)
    print(f"\n  Dashboard → http://localhost:{PORT}")
    print(f"  Status    → http://localhost:{PORT}/api/status")
    print(f"\n  Serving:  {SCRIPT_DIR}")

    # Check for data files
    data_dir = os.path.join(SCRIPT_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)
    if not os.path.exists(os.path.join(data_dir, "live_data.json")):
        print("\n  ⚠  No live_data.json found.")
        print("     Click '🔄 Run Pipeline' in the dev toolbar to generate it.")
    else:
        print("\n  ✅  live_data.json found — dashboard will load data immediately.")

    if not os.path.exists(os.path.join(data_dir, "mirofish_debates.json")):
        print("  ⚠  No mirofish_debates.json found.")
        print("     Click '🐟 Run MiroFish' in the dev toolbar to generate it.")
    else:
        print("  ✅  mirofish_debates.json found.")

    print("\n  Press Ctrl+C to stop.\n")
    print("-" * 56)

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), GODSEYEHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n  Server stopped.")


if __name__ == "__main__":
    main()
