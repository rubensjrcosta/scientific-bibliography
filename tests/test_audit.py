from scripts.audit import normalized_doi, normalized_text


def test_normalized_doi():
    assert normalized_doi('https://doi.org/10.1234/ABC') == '10.1234/abc'


def test_normalized_title():
    assert normalized_text('Gamma-Ray Astronomy') == normalized_text('Gamma Ray Astronomy')

from scripts.audit import has_value, is_placeholder


def test_placeholder_values():
    assert is_placeholder("No title")
    assert is_placeholder("Unknown")
    assert not has_value({"title": "No title"}, "title")
    assert has_value({"title": "Gamma-ray astronomy"}, "title")
