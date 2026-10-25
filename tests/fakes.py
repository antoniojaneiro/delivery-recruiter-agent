class FakeLLM:
    """Returns queued replies and records every call."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        self.calls.append({"system": system, "user": user, "json_mode": json_mode})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply
