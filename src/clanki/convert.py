"""PPTX/DOCX -> PDF with LibreOffice, so every document opens in the same PDF reader."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

_PROGRAM_FILES = [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)")]
WINDOWS_CANDIDATES = [Path(p) / "LibreOffice" / "program" / "soffice.exe"
                      for p in (_PROGRAM_FILES + [r"C:\Program Files"]) if p]


class ConversionError(Exception):
    pass


def find_soffice(configured: str | None = None) -> Path | None:
    if configured and Path(configured).is_file():
        return Path(configured)
    for name in ("soffice", "soffice.exe"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return next((p for p in WINDOWS_CANDIDATES if p.is_file()), None)


def to_pdf(src: Path, out_dir: Path, soffice: Path | None, timeout: float = 180) -> Path:
    if soffice is None:
        raise ConversionError("LibreOffice is needed to open PPTX/DOCX: install it from "
                              "libreoffice.org, or save the file as PDF from PowerPoint/Word.")
    out_dir.mkdir(parents=True, exist_ok=True)
    # A private profile lets conversion run while the user has LibreOffice open.
    with tempfile.TemporaryDirectory(prefix="clanki-lo-") as profile:
        cmd = [str(soffice), "--headless", "-env:UserInstallation=" + Path(profile).as_uri(),
               "--convert-to", "pdf", "--outdir", str(out_dir), str(src)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise ConversionError("LibreOffice timed out converting %s" % src.name) from e
    pdf = out_dir / (src.stem + ".pdf")
    if not pdf.exists():
        raise ConversionError("LibreOffice could not convert %s: %s"
                              % (src.name, (proc.stderr or proc.stdout).strip()))
    return pdf
