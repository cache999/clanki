"""Write a small text PDF for end-to-end tests (lecture material can't be committed).
Usage: python tests/make_pdf.py tests/fixtures/vision_test.pdf"""
import sys
from pathlib import Path

PAGES = [
    ["The Visual System - test fixture",
     "Rhodopsin absorbs maximally near 498 nm.",
     "Cones mediate colour vision in bright light."],
    ["Retinal cell layers (outer to inner):",
     "• Photoreceptors",
     "• Bipolar cells",
     "• Ganglion cells"],
]


def _text(s: str) -> bytes:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("cp1252")


def make_pdf(pages: list[list[str]]) -> bytes:
    n = len(pages)
    kids = " ".join("%d 0 R" % (4 + 2 * i) for i in range(n))
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [" + kids.encode() + b"] /Count %d >>" % n,
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    for i, lines in enumerate(pages):
        stream = b"".join(b"BT /F1 16 Tf 72 %d Td (" % (760 - 30 * k) + _text(line) + b") Tj ET\n"
                          for k, line in enumerate(lines))
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                    b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % (5 + 2 * i))
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for k, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % k + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


if __name__ == "__main__":
    p = Path(sys.argv[1])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(make_pdf(PAGES))
