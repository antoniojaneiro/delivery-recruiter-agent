"""Small PDFs built by hand for the CV tests: no PDF writer needed."""


def pdf_with_text(*lines: str) -> bytes:
    """A one-page PDF whose text layer is `lines` (ASCII; parentheses and backslashes are escaped)."""
    def escape(line: str) -> str:
        return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    shown = "BT /F1 12 Tf 14 TL 50 750 Td " + " T* ".join(f"({escape(line)}) Tj" for line in lines) + " ET"
    return _assemble([
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(shown)} >>\nstream\n{shown}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ])


def pdf_without_text() -> bytes:
    """A page that draws a rectangle and holds no text, like a scanned CV."""
    drawing = "0 0 100 100 re f"
    return _assemble([
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>",
        f"<< /Length {len(drawing)} >>\nstream\n{drawing}\nendstream",
    ])


def _assemble(objects: list[str]) -> bytes:
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    start = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1")
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode("latin-1")
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode("latin-1")
    return out
