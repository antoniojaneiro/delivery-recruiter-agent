from typing import Protocol


class LLMError(Exception):
    """The model could not be reached or refused (timeout, rate limit, bad model name)."""

    @property
    def kind(self) -> str:
        """A short label safe to log: the SDK error's class name, never the message content."""
        head = str(self).split(":", 1)[0].strip()
        return head if ":" in str(self) and head.isidentifier() else "LLMError"


class LLM(Protocol):
    def complete(self, system: str, user: str, json_mode: bool = False) -> str: ...


class _NoModel:
    """For a job that sends only fixed texts: if a text ever needs the model, the caller falls back to its fixed one."""

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        raise LLMError("no model in this job")


NO_MODEL: LLM = _NoModel()
