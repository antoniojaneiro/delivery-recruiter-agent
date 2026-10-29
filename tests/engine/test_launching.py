"""D94: what both launchers (the demo and the voice call) do the same way: see whether a port is taken, and stop what they
started, killing what ignores the request."""
import socket

from screener.launching import port_is_free, stop
from tests.support.processes import FakeProcess


def test_a_busy_port_is_seen_as_busy_and_a_free_one_as_free():
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        assert port_is_free(busy.getsockname()[1]) is False
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
    assert port_is_free(free) is True


def test_what_is_running_is_asked_to_stop_and_what_has_finished_is_left_alone():
    running, finished = FakeProcess(["a"]), FakeProcess(["b"])
    finished.code = 0
    stop([running, finished])
    assert running.terminated and not finished.terminated and not running.killed


def test_what_ignores_the_request_is_killed():
    import subprocess

    class Stubborn(FakeProcess):
        def wait(self, timeout=None):
            if not self.killed:
                raise subprocess.TimeoutExpired("x", timeout)

    stuck = Stubborn(["a"])
    stop([stuck])
    assert stuck.terminated and stuck.killed
