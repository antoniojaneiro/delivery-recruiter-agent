"""Reads the answer to the consent question in plain code (D44), so nothing the candidate writes
reaches the model before they have said yes. It is deliberately conservative: a reply it does not
fully recognise is "unclear" and the question is asked again."""
import re
import unicodedata
from dataclasses import dataclass

from sazon.model import Language

MAX_YES_WORDS = 5

# Phrases that contain "no" but mean yes. They are rewritten to "ok" before anything else.
_AGREEMENT_WITH_NO = (
    "no hay problema", "no tengo problema", "no hay inconveniente", "no tengo inconveniente", "sin problema",
    "no pasa nada", "no me importa", "no problem", "not a problem", "no worries",
)
_STRONG_YES = {
    "si", "sii", "sip", "claro", "vale", "ok", "okay", "okey", "yes", "yeah", "yep", "yup", "sure", "dale",
    "adelante", "perfecto", "genial", "acepto", "agree", "correcto", "bueno", "acuerdo", "supuesto", "parece",
    "fine", "great", "good", "cool", "course", "alright",
}
_FILLER = {
    "por", "favor", "que", "de", "me", "esta", "bien", "gracias", "thanks", "thank", "you", "that", "s", "is",
    "go", "ahead", "of", "with", "pleasure", "gladly", "con", "gusto", "continuar", "continue", "sounds", "all",
    "right", "please", "to", "it", "hecho", "listo",
}
_YES_VOCABULARY = _STRONG_YES | _FILLER
_DECLINE_EXACT = {
    "no", "nop", "nope", "nel", "no gracias", "no thanks", "no thank you", "no quiero", "no acepto",
    "prefiero que no", "stop", "para", "paso", "no quiero continuar", "no quiero seguir",
}
_DECLINE_START = ("no gracias", "no thanks", "no thank you", "no quiero", "no acepto", "prefiero que no")
_SPANISH_ONLY = {
    "si", "sii", "sip", "claro", "vale", "dale", "adelante", "perfecto", "acepto", "correcto", "bueno",
    "supuesto", "acuerdo", "gracias", "quiero", "prefiero", "hay", "problema", "favor", "parece", "esta",
    "bien", "por", "pasa", "nada", "inconveniente", "continuar",
}
_ENGLISH_ONLY = {
    "yes", "yeah", "yep", "yup", "sure", "thanks", "thank", "agree", "fine", "great", "cool", "problem",
    "worries", "ahead", "course", "please", "gladly", "continue", "sounds", "alright",
}


# "sí, soy Juan": a clear agreement word, then punctuation, then anything without a condition.
_LEADING_YES = re.compile(r"^[^a-z0-9]*(?:sii?|yes|yeah|yep|claro|vale|ok|okay|dale|sure|de acuerdo|por supuesto|of course)\s*[,.;:!]")
_CONDITIONS = {"no", "pero", "but", "not", "nunca", "never", "sin", "don", "dont", "t", "aunque", "unless", "solo", "only"}
MAX_TRAILING_WORDS = 25


@dataclass(frozen=True)
class ConsentReading:
    answer: bool | None
    language: Language | None = None


def _normalise(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", stripped).split())


def _language(tokens: set[str]) -> Language | None:
    spanish, english = bool(tokens & _SPANISH_ONLY), bool(tokens & _ENGLISH_ONLY)
    if spanish == english:
        return None
    return Language.ES if spanish else Language.EN


_GREETING = re.compile(
    r"^[\s¡!¿?.,;:-]*(?:hola|buenas(?:\s+(?:tardes|noches|dias))?|buenos\s+dias|hello|hi|hey|"
    r"good\s+(?:morning|afternoon|evening))\b[\s,.;:!¡-]*", re.IGNORECASE)


def _strip_greeting(text: str) -> str:
    """"hola, sí" is a yes: a greeting in front of the answer is not part of the answer."""
    folded = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return _GREETING.sub("", folded, count=1)


def read_consent(text: str) -> ConsentReading:
    greeted = bool(_GREETING.match("".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))))
    text = _strip_greeting(text)
    if greeted and not text.strip():
        return ConsentReading(None)
    if "?" in text:
        return ConsentReading(None)
    norm = _normalise(text)
    language = _language(set(norm.split()))
    if norm in _DECLINE_EXACT:
        return ConsentReading(False, language)
    for phrase in _AGREEMENT_WITH_NO:
        norm = re.sub(rf"\b{phrase}\b", "ok", norm)
    tokens = norm.split()
    if _leading_yes(text):
        return ConsentReading(True, language)
    if not tokens or len(tokens) > MAX_YES_WORDS:
        return ConsentReading(None)
    if len(tokens) <= 5 and any(norm.startswith(start) for start in _DECLINE_START) and not set(tokens) & _STRONG_YES:
        return ConsentReading(False, language)
    if set(tokens) <= _YES_VOCABULARY and set(tokens) & _STRONG_YES:
        return ConsentReading(True, language)
    return ConsentReading(None)


def _leading_yes(text: str) -> bool:
    folded = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()
    if not _LEADING_YES.match(folded):
        return False
    rest = _normalise(_LEADING_YES.sub("", folded, count=1)).split()
    return len(rest) <= MAX_TRAILING_WORDS and not set(rest) & _CONDITIONS


_STOP_EXACT = {
    "para", "stop", "basta", "cancelar", "cancela", "cancel", "unsubscribe", "stop please", "me retiro",
    "cancel my application", "i quit",
}
_STOP_STARTS = (
    "me retiro", "me doy de baja", "no quiero continuar", "ya no quiero continuar", "no quiero seguir", "ya no quiero seguir",
    "ya no me interesa", "please stop", "i want to stop", "i want to withdraw", "cancel my application",
)
MAX_WORDS_AFTER_STOP = 3


def is_stop_request(text: str) -> bool:
    """A clear request to stop, read in plain code so that opting out never depends on the model."""
    if "?" in text:
        return False
    norm = _normalise(text)
    if norm in _STOP_EXACT:
        return True
    for start in _STOP_STARTS:
        if norm == start or (norm.startswith(start + " ") and len(norm[len(start):].split()) <= MAX_WORDS_AFTER_STOP):
            return True
    return False


_HESITATION_WORDS = {
    "no", "se", "ni", "idea", "nose", "pues", "bueno", "ok", "okay", "vale", "ya", "asi", "a", "ver", "es", "que",
    "bien", "si", "idk", "lol", "well", "um", "uh", "hmm", "dunno", "know", "i", "don", "t", "not", "sure", "maybe",
    "quiza", "quizas", "tal", "vez", "otra", "esto",
}
_HESITATION_SOUNDS = re.compile(r"^(?:m+|h?m+|e+h*|a+h+|u+m+|(?:ja|je|ji|jo|ha|he)+)$")
MAX_HESITATION_WORDS = 4


def is_hesitation(text: str) -> bool:
    """"mmm", "no sé", "jaja", "ok": a filler or a laugh. The model sometimes calls these off-topic;
    they are only an answer that did not answer."""
    tokens = _normalise(text).split()
    if not tokens or len(tokens) > MAX_HESITATION_WORDS:
        return False
    return all(t in _HESITATION_WORDS or _HESITATION_SOUNDS.match(t) for t in tokens)


_RESUME_EXACT = {"continuar", "retomar", "reanudar", "sigamos", "continue", "resume"}
_RESUME_STARTS = (
    "quiero continuar", "quiero retomar", "quiero seguir", "me gustaria continuar", "i want to continue",
    "i want to resume", "let s continue", "lets continue",
)


def is_resume_request(text: str) -> bool:
    """An explicit wish to carry on after withdrawing. A polite "vale" or "gracias" to the farewell is not one."""
    if "?" in text:
        return False
    norm = _normalise(text)
    if norm in _RESUME_EXACT:
        return True
    return any(norm == start or (norm.startswith(start + " ") and len(norm[len(start):].split()) <= MAX_WORDS_AFTER_STOP)
               for start in _RESUME_STARTS)
