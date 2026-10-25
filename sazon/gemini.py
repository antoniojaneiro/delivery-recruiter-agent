import os

import openai
from dotenv import load_dotenv

from sazon.llm import LLMError

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_MODEL = "gemini-3.8-flash"  # unverified: check with --list-models
TIMEOUT_SECONDS = 20
MAX_RETRIES = 2


class GeminiClient:
    def __init__(self, model: str, sdk: openai.OpenAI):
        self.model = model
        self._sdk = sdk

    def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        kwargs = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.2 if json_mode else 0.6,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = self._sdk.chat.completions.create(**kwargs)
        except openai.OpenAIError as error:
            raise LLMError(f"{type(error).__name__}: {error}") from error
        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise LLMError("the model returned an empty answer")
        return content


    def models(self) -> list[str]:
        try:
            return sorted(m.id for m in self._sdk.models.list())
        except openai.OpenAIError as error:
            raise LLMError(f"{type(error).__name__}: {error}") from error


def from_env(load_dotenv_file: bool = True) -> GeminiClient:
    if load_dotenv_file:
        load_dotenv()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise LLMError("GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    sdk = openai.OpenAI(api_key=key, base_url=os.environ.get("LLM_BASE_URL", BASE_URL),
                        timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)
    return GeminiClient(model, sdk)


