"""RC-030 C6.3 — tests for read-only PDF evidence helpers.

No real PDF is opened by these tests — page_text is supplied as plain
strings, matching how `dose_verification_sandbox.pdf_evidence` is used
(the caller extracts text via PyMuPDF elsewhere; this module never opens
a file itself).
"""
from dose_verification_sandbox.pdf_evidence import (
    expand_context, find_quote_in_page_text, normalize_whitespace,
)


def test_normalize_whitespace_collapses_newlines_and_runs():
    assert normalize_whitespace("a  b\n\nc\td") == "a b c d"


def test_find_quote_exact_match():
    page = "some prefix text цефтриаксон 20-50 мг/кг suffix text"
    quote = "цефтриаксон 20-50 мг/кг"
    assert find_quote_in_page_text(page, quote) == page.index(quote)


def test_find_quote_with_different_line_wrapping():
    """Regression for the real bug found in C6.2/C6.3/C6.4: PDF-extracted
    text wraps differently than the stored quote's whitespace."""
    page = "цефтриаксон** – по 1–2 г в сутки внутримышечно или\nвнутривенно детям старше 12\nлет, новорожденным до 2 нед – 20–50\nмг/кг/сут, детям от 3 нед"
    quote = "новорожденным до 2 нед – 20–50 мг/кг/сут"
    idx = find_quote_in_page_text(page, quote)
    assert idx != -1


def test_find_quote_falls_back_to_anchor_when_full_quote_absent():
    page = "цефтриаксон 20-50 мг/кг в сутки НЕТОЧНОЕ ОКОНЧАНИЕ СОВСЕМ ДРУГОЕ"
    quote = "20-50 мг/кг в сутки нечто, чего нет на странице вообще"
    idx = find_quote_in_page_text(page, quote, anchor_length=15)
    assert idx != -1  # matched via the 15-char anchor, not the full quote


def test_find_quote_returns_minus_one_when_truly_absent():
    page = "совершенно не связанный текст страницы"
    quote = "текст которого здесь совсем нет 12345"
    assert find_quote_in_page_text(page, quote) == -1


def test_expand_context_returns_window_around_quote():
    page = "AAAA " * 100 + "цефтриаксон 20-50 мг/кг" + " BBBB" * 100
    quote = "цефтриаксон 20-50 мг/кг"
    expanded = expand_context(page, quote, window=20)
    assert quote in expanded
    assert len(expanded) < len(normalize_whitespace(page))


def test_expand_context_falls_back_to_bare_quote_when_unlocatable():
    page = "текст без искомой цитаты вообще"
    quote = "совершенно другой текст, отсутствующий на странице целиком"
    assert expand_context(page, quote) == quote


def test_expand_context_handles_empty_inputs():
    assert expand_context("", "quote") == "quote"
    assert expand_context("page text", "") == ""
    assert expand_context("", "") == ""


def test_expand_context_deterministic_repeat():
    page = "context before цефтриаксон 20-50 мг/кг context after"
    quote = "цефтриаксон 20-50 мг/кг"
    assert expand_context(page, quote) == expand_context(page, quote)


def test_module_has_no_file_write_or_network_or_clinical_engine():
    import inspect
    import dose_verification_sandbox.pdf_evidence as mod
    source = inspect.getsource(mod)
    for marker in ("sqlite3.connect", "open(", "requests.", "socket.", "clinical_engine", "fitz."):
        assert marker not in source
