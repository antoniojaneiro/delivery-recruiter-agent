"""D71: reading an uploaded CV. A file that is not a usable PDF never crashes anything."""
import pytest

from screener.cv import MAX_BYTES, MAX_PAGES, MAX_TEXT_CHARS, CvProblem, read_pdf
from tests.support.pdfs import pdf_with_text, pdf_without_text


def test_the_text_of_a_pdf_is_read():
    cv = read_pdf(pdf_with_text("Juan Perez Gil", "Repartidor en Glovo, 3 anos"))
    assert cv.problem is None
    assert "Juan Perez Gil" in cv.text and "Glovo" in cv.text


@pytest.mark.parametrize("data", [b"", b"hello", b"<html>%PDF-</html>", b"GIF89a" + b"x" * 50])
def test_a_file_that_does_not_start_like_a_pdf_is_refused(data):
    assert read_pdf(data).problem == CvProblem.NOT_A_PDF


def test_a_file_over_the_size_limit_is_refused():
    assert read_pdf(b"%PDF-1.4\n" + b"0" * MAX_BYTES).problem == CvProblem.TOO_BIG


@pytest.mark.parametrize("data", [b"%PDF-1.4\nthis is not a real pdf", pdf_with_text("x")[:120]])
def test_a_broken_pdf_is_a_file_without_text_not_a_crash(data):
    assert read_pdf(data).problem == CvProblem.NO_TEXT


def test_a_pdf_with_no_text_layer_is_a_file_without_text():
    cv = read_pdf(pdf_without_text())
    assert cv.problem == CvProblem.NO_TEXT and cv.text == ""


def test_an_encrypted_pdf_is_a_file_without_text():
    from pypdf import PdfReader, PdfWriter
    import io

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_with_text("Juan Perez"))))
    writer.encrypt("secret")
    buffer = io.BytesIO()
    writer.write(buffer)
    assert read_pdf(buffer.getvalue()).problem == CvProblem.NO_TEXT


def test_only_the_first_pages_and_characters_are_read():
    from pypdf import PdfReader, PdfWriter
    import io

    page = PdfReader(io.BytesIO(pdf_with_text("word " * 2000)))
    writer = PdfWriter()
    for _ in range(MAX_PAGES + 3):
        writer.add_page(page.pages[0])
    buffer = io.BytesIO()
    writer.write(buffer)
    cv = read_pdf(buffer.getvalue())
    assert cv.problem is None and 0 < len(cv.text) <= MAX_TEXT_CHARS
