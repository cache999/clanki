from clanki import doctext
from make_pdf import make_pdf


def test_page_texts_extracts_each_page(tmp_path):
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(make_pdf([["Rods and cones", "Rhodopsin 498 nm"], ["Bipolar cells"]]))
    pages = doctext.page_texts(pdf)
    assert len(pages) == 2
    assert "Rhodopsin 498 nm" in pages[0] and "Bipolar cells" in pages[1]


def test_clean_collapses_blank_runs_and_trailing_space():
    assert doctext.clean("a  \n\n\n\nb \n") == "a\n\nb"


def test_document_text_marks_pages():
    assert doctext.document_text(["one", "", "three"], 1, 3) == "[p.1]\none\n\n[p.2]\n\n[p.3]\nthree"
    assert doctext.document_text(["one", "two", "three"], 2, 2) == "[p.2]\ntwo"


def test_chunks_respect_page_and_size_limits():
    pages = ["x" * 3000] * 10
    assert doctext.chunk_pages(pages, max_chars=10000, max_pages=6) == [(1, 3), (4, 6), (7, 9), (10, 10)]
    assert doctext.chunk_pages(["a"] * 7, max_chars=10000, max_pages=3) == [(1, 3), (4, 6), (7, 7)]


def test_empty_pages_never_form_a_chunk_on_their_own():
    # pages without text (figures, title slides) ride along and don't count towards max_pages
    assert doctext.chunk_pages(["", "", "text", "", ""], max_chars=100, max_pages=2) == [(1, 5)]
    assert doctext.chunk_pages(["a", "", "b", "c"], max_chars=100, max_pages=2) == [(1, 3), (4, 4)]
    assert doctext.chunk_pages(["", " "], max_chars=100, max_pages=2) == []


def test_a_single_huge_page_is_its_own_chunk():
    assert doctext.chunk_pages(["x" * 50, "y" * 500, "z"], max_chars=100, max_pages=6) == [(1, 1), (2, 2), (3, 3)]


def test_context_window_clamps_to_document():
    assert doctext.context_window(10, page=1, radius=2) == (1, 3)
    assert doctext.context_window(10, page=9, radius=2) == (7, 10)
