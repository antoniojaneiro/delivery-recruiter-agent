"""What the launchers have in common (D94): see whether a port is taken, and stop what was started."""
import socket
import subprocess

STOP_WAIT_SECONDS = 5


def port_is_free(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) != 0  # nothing answers there


def stop(processes) -> None:
    """Asks each running process to stop, and kills the ones that do not within a few seconds."""
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=STOP_WAIT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
