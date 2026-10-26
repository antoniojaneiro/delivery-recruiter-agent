class FakeLLM:
    """Returns queued replies and records every call."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        from sazon.llm import LLMError

        self.calls.append({"system": system, "user": user, "json_mode": json_mode})
        if not self.replies:
            raise LLMError("script exhausted")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class ScriptedLLM:
    """Extraction calls (json_mode) pop from `extractions`; phrasing calls pop from `phrases`.
    An empty phrases queue raises LLMError, so replies fall back to the fixed templates."""

    def __init__(self, extractions=(), phrases=()):
        import json
        self.extractions = [e if isinstance(e, (str, Exception)) else json.dumps(e) for e in extractions]
        self.phrases = list(phrases)
        self.calls = []

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        from sazon.llm import LLMError

        self.calls.append({"system": system, "user": user, "json_mode": json_mode})
        queue = self.extractions if json_mode else self.phrases
        if not queue:
            raise LLMError("script exhausted")
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply
