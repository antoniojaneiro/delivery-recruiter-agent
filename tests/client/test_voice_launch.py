"""D93: `python -m sazon.voice_launch` starts everything the live voice agent needs: a tunnel so ElevenLabs can reach our endpoint,
the agent pointed at that address, and the endpoint itself. It refuses to start without a key, and stops everything it
started."""
import io

import pytest

from sazon import config, voice_launch
from screener.voice_agent import VoiceSetupError, VoiceState

URL = "https://quiet-example-words.trycloudflare.com"


class FakeProcess:
    def __init__(self, lines=(), dies=False):
        self.stdout = iter(lines)
        self.stopped, self._dies = False, dies

    def poll(self):
        return 1 if self._dies else None

    def terminate(self):
        self.stopped = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.stopped = True


class World:
    """Everything the launcher touches, faked: processes, the ElevenLabs API and the clock."""

    def __init__(self, tunnel_lines=None, refuse=False, interrupt_after=2):
        self.spawned, self.out, self.provisioned = [], [], []
        self.tunnel_lines = [f"INF |  {URL}  |\n"] if tunnel_lines is None else tunnel_lines
        self.refuse, self.ticks, self.interrupt_after = refuse, 0, interrupt_after

    def spawn(self, command, **kwargs):
        process = FakeProcess(self.tunnel_lines if "cloudflared" in command[0] else ())
        self.spawned.append((command, kwargs, process))
        return process

    def provision(self, api, client, public_url, state_path, voice_id=None):
        if self.refuse:
            raise VoiceSetupError("ElevenLabs answered 401 to POST /v1/convai/secrets")
        self.provisioned.append((public_url, state_path, voice_id))
        return VoiceState("agent_1", "secret_1", "the-shared-secret")

    def sleep(self, seconds):
        self.ticks += 1
        if self.ticks >= self.interrupt_after:
            raise KeyboardInterrupt

    def run(self, env=None):
        env = {"ELEVENLABS_API_KEY": "key-123", **(env or {})}
        return voice_launch.run(env=env, spawn=self.spawn, provision_fn=self.provision, sleep=self.sleep, out=self.out.append,
                                api_factory=lambda key: object(), port_free=lambda port: True)


@pytest.mark.parametrize("line,expected", [
    (f"2026-10-29T01:20:11Z INF |  {URL}  |", URL), ("Visit it at https://abc-def.trycloudflare.com/", "https://abc-def.trycloudflare.com"),
    ("INF Requesting new quick Tunnel on trycloudflare.com...", None), ("https://example.com", None), ("", None)])
def test_the_tunnels_address_is_found_in_what_cloudflared_prints(line, expected):
    assert voice_launch.find_tunnel_url(line) == expected


def test_without_an_elevenlabs_key_nothing_is_started_and_the_user_is_told_what_to_add():
    world = World()
    assert world.run({"ELEVENLABS_API_KEY": ""}) == 2
    assert world.spawned == [] and "ELEVENLABS_API_KEY" in " ".join(world.out)


def test_it_starts_the_tunnel_points_the_agent_at_it_and_starts_the_endpoint_with_the_shared_secret():
    world = World()
    assert world.run({"ELEVENLABS_VOICE_ID": "voice_9"}) == 0  # Ctrl+C is a normal way to stop
    assert world.provisioned == [(URL, config.VOICE_STATE_PATH, "voice_9")]
    tunnel, server = (spawn[0] for spawn in world.spawned)
    assert tunnel[0] == "cloudflared" and f"http://localhost:{config.voice_port()}" in tunnel
    assert server[-2:] == ["-m", "sazon.voice_server"]
    assert world.spawned[1][1]["env"]["VOICE_LLM_SECRET"] == "the-shared-secret"
    assert "key-123" not in " ".join(world.out) and "the-shared-secret" not in " ".join(world.out)
    assert all(process.stopped for _, _, process in world.spawned)  # Ctrl+C stopped both


def test_if_the_tunnel_never_gives_an_address_the_endpoint_is_not_started_and_the_tunnel_is_stopped():
    world = World(tunnel_lines=["INF Requesting new quick Tunnel\n"])
    assert world.run() == 1
    assert len(world.spawned) == 1 and world.spawned[0][2].stopped and world.provisioned == []


def test_if_elevenlabs_refuses_everything_started_is_stopped_and_the_reason_is_shown_without_secrets():
    world = World(refuse=True)
    assert world.run() == 1
    assert len(world.spawned) == 1 and world.spawned[0][2].stopped
    assert "401" in " ".join(world.out) and "key-123" not in " ".join(world.out)


def test_if_the_endpoint_stops_by_itself_the_tunnel_is_stopped_too():
    world = World(interrupt_after=50)
    original = world.spawn

    def spawn(command, **kwargs):
        process = original(command, **kwargs)
        if "sazon.voice_server" in command:
            process._dies = True
        return process

    world.spawn = spawn
    assert world.run() == 1 and world.spawned[0][2].stopped  # the tunnel was still running, so it was stopped
