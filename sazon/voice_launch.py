"""Starts everything the live voice agent needs, for trying it on your own computer (D93): `python -m sazon.voice_launch`.

ElevenLabs does the listening and the speaking, but its servers must reach our engine, so this opens a quick tunnel
(Cloudflare's `cloudflared`, no account) to the voice endpoint only, points the ElevenLabs agent at the tunnel's address
(it is new every time), and starts the endpoint with the shared secret. Press Ctrl+C to stop both. The chat page's
"Talk to Sofía" button works while this runs."""
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

from sazon import config
from sazon.client import SAZON_CLIENT
from screener.launching import port_is_free, stop
from screener.voice_agent import ElevenLabs, VoiceSetupError, provision

ROOT = Path(__file__).resolve().parent.parent
TUNNEL_WAIT_SECONDS = 45
_TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def find_tunnel_url(line: str) -> str | None:
    found = _TUNNEL_URL.search(line or "")
    return found[0] if found else None


def _read_url(process, timeout: float) -> str | None:
    """The tunnel's address, read from what cloudflared prints, or None if it does not appear in time."""
    lines: queue.Queue = queue.Queue()

    def reader():
        for line in process.stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=reader, daemon=True).start()
    deadline = time.monotonic() + timeout
    while (left := deadline - time.monotonic()) > 0:
        try:
            line = lines.get(timeout=min(left, 0.5))
        except queue.Empty:
            continue
        if line is None:
            return None
        if url := find_tunnel_url(line):
            return url
    return None


def find_cloudflared(env, which=shutil.which, home: Path | None = None) -> str | None:
    """Where the tunnel program is: the CLOUDFLARED setting, the PATH, or the user's own `bin` folder (which a Windows terminal
    may not have on its PATH even though a download was saved there). None when it is nowhere."""
    home = home if home is not None else Path.home()
    configured = env.get("CLOUDFLARED")
    if configured and Path(configured).is_file():
        return configured
    if on_path := which("cloudflared"):
        return on_path
    own = home / "bin" / "cloudflared.exe"
    return str(own) if own.is_file() else None


def run(env=None, spawn=subprocess.Popen, provision_fn=provision, sleep=time.sleep, out=print, api_factory=ElevenLabs,
        port_free=port_is_free, wait_for_url=_read_url, find_exe=None) -> int:
    """0 after Ctrl+C, 1 when something failed or stopped by itself, 2 when it cannot start (no key, port in use)."""
    env = dict(os.environ if env is None else env)
    key, port = env.get("ELEVENLABS_API_KEY", "").strip(), config.voice_port()
    if not key:
        out("ELEVENLABS_API_KEY is not set. Add it to .env (your own key from elevenlabs.io), then run this again.")
        return 2
    if not port_free(port):
        out(f"Port {port} is already in use: stop what is running there and try again.")
        return 2
    exe = (find_exe or find_cloudflared)(env)
    if exe is None:
        out("cloudflared (the tunnel program) was not found. Download cloudflared-windows-amd64.exe from "
            "github.com/cloudflare/cloudflared/releases, save it as cloudflared.exe in your user bin folder (or set CLOUDFLARED to its path), "
            "then run this again.")
        return 2
    started = []
    try:
        tunnel = spawn([exe, "tunnel", "--url", f"http://localhost:{port}", "--no-autoupdate"],
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        started.append(tunnel)
        out("Opening the tunnel (a few seconds)...")
        url = wait_for_url(tunnel, TUNNEL_WAIT_SECONDS)
        if url is None:
            out("The tunnel did not give an address. Is cloudflared installed (cloudflared --version)?")
            return 1
        try:
            state = provision_fn(api_factory(key), SAZON_CLIENT, url, config.VOICE_STATE_PATH, voice_id=env.get("ELEVENLABS_VOICE_ID") or None)
        except VoiceSetupError as error:
            out(str(error))
            return 1
        server = spawn([sys.executable, "-m", "sazon.voice_server"], env={**env, "VOICE_LLM_SECRET": state.secret}, cwd=ROOT)
        started.append(server)
        out(f"Ready: the voice agent talks to {url} (only the voice endpoint is open). Press \"Talk to Sofía\" in the chat. Ctrl+C stops it.")
        while True:
            sleep(1)
            if any(process.poll() is not None for process in started):
                out("Something stopped by itself; stopping the rest.")
                return 1
    except KeyboardInterrupt:
        out("Stopping...")
        return 0
    finally:
        stop(started)


if __name__ == "__main__":
    load_dotenv()
    sys.exit(run())
