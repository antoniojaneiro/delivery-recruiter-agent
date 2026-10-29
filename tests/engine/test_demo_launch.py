"""demo_launch.py starts the chat and the dashboard together and stops both when you stop it."""
import importlib.util
import sys

from tests.support.paths import ROOT
from tests.support.processes import FakeProcess


def load():
    spec = importlib.util.spec_from_file_location("demo_launch", ROOT / "demo_launch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_it_starts_the_chat_and_the_dashboard_on_two_different_ports():
    commands = dict(load().commands())
    chat, dashboard = commands["chat"], commands["dashboard"]
    assert chat[:4] == [sys.executable, "-m", "streamlit", "run"] and chat[4].replace("\\", "/") == "apps/chat_app.py"
    assert dashboard[4].replace("\\", "/") == "apps/dashboard.py"
    ports = [c[c.index("--server.port") + 1] for c in (chat, dashboard)]
    assert len(set(ports)) == 2


def test_it_runs_from_the_project_folder_so_the_apps_find_their_data():
    started = []
    launch = load()

    def spawn(command, cwd=None):
        started.append(FakeProcess(command, cwd))
        return started[-1]

    def sleep(_):
        raise KeyboardInterrupt

    launch.run(spawn=spawn, sleep=sleep, out=lambda *a: None, port_free=lambda port: True)
    assert len(started) == 2 and all(p.cwd == ROOT for p in started)


def test_stopping_with_ctrl_c_stops_both_apps():
    started = []
    launch = load()

    def spawn(command, cwd=None):
        started.append(FakeProcess(command, cwd))
        return started[-1]

    def sleep(_):
        raise KeyboardInterrupt

    assert launch.run(spawn=spawn, sleep=sleep, out=lambda *a: None, port_free=lambda port: True) == 0
    assert all(p.terminated for p in started)


def test_when_one_app_dies_the_other_is_stopped_and_it_says_so():
    started, said = [], []
    launch = load()

    def spawn(command, cwd=None):
        started.append(FakeProcess(command, cwd, finishes_after=1 if len(started) == 1 else None))
        return started[-1]

    code = launch.run(spawn=spawn, sleep=lambda _: None, out=said.append, port_free=lambda port: True)
    assert code == 1 and started[0].terminated and any("dashboard" in line for line in said)


def test_an_app_that_ignores_the_stop_request_is_killed():
    class Stubborn(FakeProcess):
        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            import subprocess
            if not self.killed:
                raise subprocess.TimeoutExpired("x", timeout)
            return self.code

    started = []
    launch = load()

    def spawn(command, cwd=None):
        started.append(Stubborn(command, cwd))
        return started[-1]

    def sleep(_):
        raise KeyboardInterrupt

    launch.run(spawn=spawn, sleep=sleep, out=lambda *a: None, port_free=lambda port: True)
    assert all(p.killed for p in started)


def test_a_port_that_is_already_in_use_is_reported_before_anything_is_started():
    started, said = [], []
    launch = load()
    code = launch.run(spawn=lambda *a, **k: started.append(1), sleep=lambda _: None, out=said.append,
                      port_free=lambda port: port != 8501)
    assert code == 2 and started == []
    assert any("8501" in line and "chat" in line and "already" in line for line in said)


def test_the_real_port_check_sees_a_busy_port_and_a_free_one():
    import socket
    launch = load()
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        assert launch.port_is_free(busy.getsockname()[1]) is False
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
    assert launch.port_is_free(free) is True
