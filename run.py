# run.py
import os
import sys
import time
import signal
import subprocess
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"
VENV_PYTHON = BASE_DIR / ".venv" / "Scripts" / "python.exe"
PYTHON_BIN = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

def check_docker():
    """Optional check for Docker Postgres container."""
    try:
        res = subprocess.run(["docker", "ps"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            print("[INFO] Docker is active. Ensuring PostgreSQL container is running...")
            subprocess.run(["docker", "compose", "up", "-d"], cwd=str(BASE_DIR), capture_output=True, timeout=5)
            print("[INFO] PostgreSQL container ready.")
        else:
            print("[INFO] Docker offline. Running with seamless demo/mock fallback.")
    except Exception:
        print("[INFO] Docker offline. Running with seamless demo/mock fallback.")

def main():
    print("=" * 72)
    print("  INSTITUTIONAL EMAIL INTELLIGENCE SYSTEM — DIRECT LAUNCHER")
    print("=" * 72)

    check_docker()

    # 1. Start FastAPI Backend Process
    print("\n[1/2] Starting FastAPI REST Backend on http://localhost:8000 ...")
    backend_cmd = [
        PYTHON_BIN,
        "-m", "uvicorn",
        "app.main:app",
        "--host", "127.0.0.1",
        "--port", "8000",
        "--reload"
    ]
    
    # Environment with backend on PYTHONPATH
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_DIR)

    backend_proc = subprocess.Popen(
        backend_cmd,
        cwd=str(BACKEND_DIR),
        env=env
    )

    # 2. Start Vite Frontend Process
    print("[2/2] Starting React Institutional Cockpit on http://localhost:5173 ...")
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    frontend_proc = subprocess.Popen(
        [npm_cmd, "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"],
        cwd=str(FRONTEND_DIR)
    )

    print("\n" + "=" * 72)
    print("  SYSTEM READY — COCKPIT & BACKEND ONLINE")
    print("=" * 72)
    print("  -> Cockpit UI:        http://localhost:5173")
    print("  -> FastAPI Swagger:   http://localhost:8000/docs")
    print("  -> Health Check:      http://localhost:8000/health")
    print("=" * 72)
    print("  Press Ctrl+C at any time to cleanly stop all servers.\n")

    # Open browser after a brief delay
    time.sleep(2)
    try:
        webbrowser.open("http://localhost:5173")
    except Exception:
        pass

    def cleanup(signum=None, frame=None):
        print("\n[SHUTDOWN] Stopping frontend and backend servers...")
        try:
            if sys.platform == "win32":
                subprocess.call(["taskkill", "/F", "/T", "/PID", str(frontend_proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.call(["taskkill", "/F", "/T", "/PID", str(backend_proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                frontend_proc.terminate()
                backend_proc.terminate()
        except Exception:
            pass
        print("[SHUTDOWN] All services stopped cleanly.")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    try:
        while True:
            # Check if either process died unexpectedly
            b_poll = backend_proc.poll()
            f_poll = frontend_proc.poll()
            if b_poll is not None:
                print(f"[ERROR] Backend exited unexpectedly with code {b_poll}")
                cleanup()
            if f_poll is not None:
                print(f"[ERROR] Frontend exited unexpectedly with code {f_poll}")
                cleanup()
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()

if __name__ == "__main__":
    main()
