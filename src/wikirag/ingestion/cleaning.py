def test_clean_text_preserves_mathematical_comparisons() -> None:
    text = "For all inputs where x < y and z > 0, the condition holds."
    cleaned = clean_text(text)
    assert cleaned == "For all inputs where x < y and z > 0, the condition holds."


def test_clean_text_removes_html_and_citation_markers() -> None:
    raw = "<p>Text with <b>bold</b> and a reference[1] or citation[citation needed] and [edit].</p>"
    cleaned = clean_text(raw)
    assert "<" not in cleaned
    assert ">" not in cleaned
    assert "[1]" not in cleaned
    assert "[citation needed]" not in cleaned
    assert "[edit]" not in cleaned
    assert "Text with bold and a reference or citation and ." == cleaned
