"""The words a client's screens show, one entry per language (D66). A screen asks for a text by key; a text missing
in a language, or with different {placeholders} in two languages, is refused when the pack is built."""
from dataclasses import dataclass
from string import Formatter

from screener.model import Language
from screener.pack import Text


class UiTextError(ValueError):
    """A text pack that cannot be shown. The message lists every problem found."""


def _placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(text) if name}


@dataclass(frozen=True)
class UiPack:
    languages: tuple[Language, ...]  # the first one is the default
    texts: dict[str, Text]

    def __post_init__(self):
        problems = []
        for key, text in self.texts.items():
            missing = [str(language) for language in self.languages if not text.get(language)]
            if missing:
                problems.append(f"text '{key}' has nothing in {', '.join(missing)}")
                continue
            if len({frozenset(_placeholders(text[language])) for language in self.languages}) > 1:
                problems.append(f"text '{key}' has different placeholders in different languages")
        if problems:
            raise UiTextError("; ".join(problems))

    def get(self, key: str, language, **values) -> str:
        try:
            text = self.texts[key]
        except KeyError:
            raise UiTextError(f"no text '{key}'") from None
        return (text.get(language) or text[self.languages[0]]).format(**values)
