"""Starts the browser chat and the recruiter dashboard together. Run with: python demo_launch.py

Chat:       http://localhost:8501  (its candidates are saved in the dashboard)
Dashboard:  http://localhost:8502  (sign in with the email and password of a recruiter; see .env.example for the hiring manager)
Press Ctrl+C to stop both."""
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APPS = (("chat", "apps/chat_app.py", 8501), ("dashboard", "apps/dashboard.py", 8502))
STOP_WAIT_SECONDS = 5


def commands() -> list[tuple[str, list[str]]]:
    return [(name, [sys.executable, "-m", "streamlit", "run", script, "--server.port", str(port)])
            for name, script, port in APPS]


def port_is_free(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) != 0  # nothing answers there


def _stop(processes) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=STOP_WAIT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def run(spawn=subprocess.Popen, sleep=time.sleep, out=print, port_free=port_is_free) -> int:
    """Starts both apps and waits. Returns 0 after Ctrl+C, 1 when an app stopped by itself (the other is then
    stopped) and 2 when a port is already in use (nothing is started)."""
    busy = [(name, port) for name, _, port in APPS if not port_free(port)]
    for name, port in busy:
        out(f"Port {port} is already in use, so the {name} cannot start: stop what is running there and try again.")
    if busy:
        return 2
    started = [(name, spawn(command, cwd=ROOT)) for name, command in commands()]
    for name, _, port in APPS:
        out(f"{name}: http://localhost:{port}")
    code = 0
    try:
        while code == 0:
            sleep(1)
            for name, process in started:
                if process.poll() is not None:
                    out(f"The {name} stopped (exit code {process.poll()}); stopping the other one.")
                    code = 1
    except KeyboardInterrupt:
        out("Stopping both apps...")
    finally:
        _stop([process for _, process in started])
    return code


if __name__ == "__main__":
    sys.exit(run())
