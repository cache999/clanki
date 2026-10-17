import shutil
import subprocess
from pathlib import Path

import pytest

from clanki import convert


def test_configured_soffice_path_wins(tmp_path):
    exe = tmp_path / "soffice.exe"
    exe.write_text("")
    assert convert.find_soffice(str(exe)) == exe


def test_missing_configured_path_falls_back_to_path(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/soffice" if name == "soffice" else None)
    assert convert.find_soffice(str(tmp_path / "nope")) == Path("/usr/bin/soffice")


def test_windows_default_install_is_found(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    exe = tmp_path / "LibreOffice" / "program" / "soffice.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    monkeypatch.setattr(convert, "WINDOWS_CANDIDATES", [exe])
    assert convert.find_soffice() == exe


def test_no_soffice_anywhere(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(convert, "WINDOWS_CANDIDATES", [])
    assert convert.find_soffice() is None


def test_to_pdf_uses_a_private_profile_and_returns_the_pdf(monkeypatch, tmp_path):
    src = tmp_path / "talk.pptx"
    src.write_text("x")
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        out = Path(cmd[cmd.index("--outdir") + 1])
        (out / "talk.pdf").write_text("%PDF")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    pdf = convert.to_pdf(src, tmp_path / "out", soffice=Path("soffice"))
    assert pdf == tmp_path / "out" / "talk.pdf" and pdf.exists()
    cmd = seen["cmd"]
    assert cmd[:2] == ["soffice", "--headless"]
    assert any(a.startswith("-env:UserInstallation=file:") for a in cmd)
    assert cmd[-1] == str(src)


def test_to_pdf_raises_when_no_output(monkeypatch, tmp_path):
    src = tmp_path / "talk.pptx"
    src.write_text("x")
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "boom"))
    with pytest.raises(convert.ConversionError, match="boom"):
        convert.to_pdf(src, tmp_path / "out", soffice=Path("soffice"))


def test_to_pdf_without_libreoffice_explains_what_to_do(tmp_path):
    with pytest.raises(convert.ConversionError, match="LibreOffice"):
        convert.to_pdf(tmp_path / "a.docx", tmp_path, soffice=None)


SOFFICE = convert.find_soffice()


def _has_component(name):  # Linux distros split LibreOffice; Windows installs include everything
    return SOFFICE is not None and any((SOFFICE.resolve().parent / n).exists() for n in (name, name + ".exe"))


@pytest.mark.soffice
@pytest.mark.skipif(not _has_component("simpress"), reason="LibreOffice Impress not installed")
def test_real_pptx_conversion(tmp_path):
    from pptx import Presentation
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Phototransduction"
    slide.placeholders[1].text = "Rhodopsin absorbs maximally near 498 nm"
    prs.save(tmp_path / "talk.pptx")
    pdf = convert.to_pdf(tmp_path / "talk.pptx", tmp_path / "out", soffice=SOFFICE)
    assert pdf.read_bytes().startswith(b"%PDF")


@pytest.mark.soffice
@pytest.mark.skipif(not _has_component("swriter"), reason="LibreOffice Writer not installed")
def test_real_docx_conversion(tmp_path):
    from docx import Document
    d = Document()
    d.add_heading("Rods", 1)
    d.add_paragraph("Rhodopsin absorbs maximally near 498 nm.")
    d.save(tmp_path / "note.docx")
    pdf = convert.to_pdf(tmp_path / "note.docx", tmp_path / "out", soffice=SOFFICE)
    assert pdf.read_bytes().startswith(b"%PDF")
