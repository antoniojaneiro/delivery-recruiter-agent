"""Reading an uploaded CV (D71). The file is untrusted: it is checked, read for a bounded amount of text, and any
failure is an answer ("no text"), never an exception."""
import io
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from screener.extraction import build_cv_prompt, clean_text, parse_reply

MAX_BYTES = 2 * 1024 * 1024
MAX_PAGES = 5
MAX_TEXT_CHARS = 6000  # what the model is ever shown of a CV


class CvProblem(StrEnum):
    NOT_A_PDF = "not_a_pdf"  # refused and not stored
    TOO_BIG = "too_big"  # refused and not stored
    NO_TEXT = "no_text"  # a scan, an encrypted or a broken PDF: stored, but nothing to read


@dataclass(frozen=True)
class CvText:
    text: str = ""
    problem: CvProblem | None = None


def read_pdf(data: bytes) -> CvText:
    if not isinstance(data, bytes) or not data.startswith(b"%PDF-"):
        return CvText(problem=CvProblem.NOT_A_PDF)
    if len(data) > MAX_BYTES:
        return CvText(problem=CvProblem.TOO_BIG)
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            return CvText(problem=CvProblem.NO_TEXT)
        text = ""
        for page in reader.pages[:MAX_PAGES]:
            text += (page.extract_text() or "") + "\n"
            if len(text) >= MAX_TEXT_CHARS:
                break
    except Exception:  # a malformed file can fail in many ways inside the parser
        return CvText(problem=CvProblem.NO_TEXT)
    text = " ".join(text.split())[:MAX_TEXT_CHARS]
    return CvText(text) if text else CvText(problem=CvProblem.NO_TEXT)


def extract_cv(llm, spec, text: str, today: date):
    """What the model reads out of the CV text, or None when its reply cannot be used. The caller keeps only the
    fields the client allows from a CV; whatever else the reply says is ignored."""
    safe = clean_text(text)[:MAX_TEXT_CHARS]
    user = f"Today is {today.isoformat()}.\n<cv_text>\n{safe}\n</cv_text>"
    return parse_reply(llm.complete(build_cv_prompt(spec), user, json_mode=True), spec.extraction_model)
