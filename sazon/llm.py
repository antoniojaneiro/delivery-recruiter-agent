from typing import Protocol


class LLMError(Exception):
    """The model could not be reached or refused (timeout, rate limit, bad model name)."""


class LLM(Protocol):
    def complete(self, system: str, user: str, json_mode: bool = False) -> str: ...
