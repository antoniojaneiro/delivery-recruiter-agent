"""A stand-in for a started process, for the tests of the launchers."""


class FakeProcess:
    def __init__(self, command, cwd=None, finishes_after=None):
        self.command, self.cwd = command, cwd
        self.finishes_after = finishes_after
        self.polls, self.terminated, self.killed = 0, False, False
        self.code = None

    def poll(self):
        self.polls += 1
        if self.finishes_after is not None and self.polls > self.finishes_after:
            self.code = 1
        return self.code

    def terminate(self):
        self.terminated, self.code = True, 0

    def wait(self, timeout=None):
        return self.code

    def kill(self):
        self.killed, self.code = True, -9
