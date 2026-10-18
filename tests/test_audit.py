from scripts.audit import normalized_doi, normalized_text


def test_normalized_doi():
    assert normalized_doi('https://doi.org/10.1234/ABC') == '10.1234/abc'


def test_normalized_title():
    assert normalized_text('Gamma-Ray Astronomy') == normalized_text('Gamma Ray Astronomy')
