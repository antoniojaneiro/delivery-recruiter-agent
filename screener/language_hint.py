"""Which language the candidate is writing in (D67). The model's guess is not enough: it called a bare city and a
plain name Spanish. A name, a place or a number says nothing, so the chat language changes only when the candidate's
own words show it. These are everyday function words that exist in one of the two languages only."""
import re
import unicodedata

from screener.model import Language

_SPANISH = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "soy", "eres", "es", "estoy", "tengo", "tienes", "vivo",
    "vive", "puedo", "quiero", "quisiera", "mi", "mis", "mucho", "muy", "anos", "ano", "experiencia", "trabajo",
    "trabajar", "semana", "semanas", "dias", "dia", "disponible", "tiempo", "completo", "manana", "mananas", "tarde",
    "noche", "gracias", "hola", "buenas", "por", "favor", "para", "con", "sin", "pero", "porque", "cuando", "donde",
    "como", "que", "en", "de", "del", "al", "si", "lunes", "martes", "miercoles", "jueves", "viernes", "sabado",
    "domingo", "empezar", "puedes", "tres", "dos", "cuatro", "cinco", "ciudad",
}
_ENGLISH = {
    "the", "an", "i", "my", "am", "have", "has", "can", "live", "lives", "work", "works", "years", "year",
    "experience", "in", "at", "with", "for", "and", "is", "are", "to", "of", "days", "day", "week", "weeks", "full",
    "time", "part", "please", "yes", "thanks", "hello", "hi", "morning", "afternoon", "evening", "available",
    "start", "from", "this", "that", "was", "would", "like", "want", "need", "not", "dont", "on", "it", "do", "does",
    "you", "your", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "next", "three",
    "two", "four", "five", "city", "weekends", "weekend",
}


def _words(text: str) -> list[str]:
    plain = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()
    return re.findall(r"[a-z]+", plain)


def language_of(message: str, claimed: Language | None, current: Language) -> Language:
    """The language the chat should be in after this message: the one its words show, else (for a longer message
    no known word can check) the model's claim, else the one the chat is already in."""
    words = _words(message)
    spanish, english = sum(w in _SPANISH for w in words), sum(w in _ENGLISH for w in words)
    if spanish != english:
        return Language.ES if spanish > english else Language.EN
    if claimed and len(words) >= 4 and spanish == english == 0:
        return claimed
    return current
