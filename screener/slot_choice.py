"""Reads the candidate's pick from the numbered slot list in plain code (D48). Picking books a real
call, so a pick must be unambiguous: one valid option number and nothing else we do not recognise.
Declining is safe (they can write again to book later), so it is read more generously."""
from screener.language import plain


class _NoSlot:
    def __repr__(self) -> str:
        return "NONE"


NONE = _NoSlot()  # the candidate declined every option

_DECLINE_WORDS = {"ninguna", "ninguno", "none", "neither", "retiro", "retirar", "cancelar", "cancela", "cancel",
                  "withdraw", "withdrawing"}
_DECLINE_PHRASES = {"no", "no gracias", "no thanks", "no thank you", "stop", "para", "paso"}
_DECLINE_STARTS = ("no gracias", "no thanks", "no quiero", "ya no quiero", "i do not want", "i don t want",
                  "i dont want")
_ORDINALS = {
    "primero": 1, "primera": 1, "first": 1, "uno": 1,
    "segundo": 2, "segunda": 2, "second": 2, "dos": 2, "two": 2,
    "tercero": 3, "tercera": 3, "third": 3, "tres": 3, "three": 3,
    "cuarto": 4, "cuarta": 4, "fourth": 4, "cuatro": 4, "four": 4,
    "quinto": 5, "quinta": 5, "fifth": 5, "cinco": 5, "five": 5,
}
_FILLER = {
    "el", "la", "los", "las", "opcion", "option", "numero", "number", "por", "favor", "please", "vale", "ok",
    "okay", "si", "me", "viene", "bien", "esa", "ese", "that", "the", "one", "quiero", "elijo", "prefiero", "i",
    "ll", "take", "choose", "pick", "go", "with", "gracias", "thanks", "de", "of", "un", "una", "want", "would",
    "like",
}


def read_slot_choice(text: str, options: int):
    """Returns the option number (1..options), NONE if they decline every option, or None if unclear."""
    if "?" in text:
        return None
    norm = plain(text)
    tokens = norm.split()
    if not tokens:
        return None
    if set(tokens) & _DECLINE_WORDS or norm in _DECLINE_PHRASES or norm.startswith(_DECLINE_STARTS):
        return NONE
    numbers = set()
    for token in tokens:
        if token.isdigit():
            numbers.add(int(token))
        elif token in _ORDINALS:
            numbers.add(_ORDINALS[token])
        elif token not in _FILLER:
            return None
    if len(numbers) != 1:
        return None
    number = numbers.pop()
    return number if 1 <= number <= options else None
