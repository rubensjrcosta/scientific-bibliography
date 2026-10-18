import csv
from pathlib import Path
import pytest
from scripts.normalize import clean_value, normalize


def test_doi_and_unchanged_title():
    assert clean_value('doi', ' https://doi.org/10.1234/ABC ') == '10.1234/ABC'
    assert clean_value('title', r'{The {MAGIC} telescope}') == r'{The {MAGIC} telescope}'


def test_preserves_source_and_keys(tmp_path: Path):
    source = tmp_path / 'master.bib'
    source.write_text('@article{Keep2019Key, title={A {LaTeX} Title}, author={Doe, Jane}, year={ 2019 }, doi={https://doi.org/10.1234/ABC}}\n', encoding='utf-8')
    before = source.read_bytes()
    out, report = tmp_path / 'normalized.bib', tmp_path / 'report.csv'
    result = normalize(source, out, report)
    assert source.read_bytes() == before
    assert result['entries'] == 1
    assert 'Keep2019Key' in out.read_text()
    assert '10.1234/ABC' in out.read_text()
    assert list(csv.DictReader(report.open()))
    with pytest.raises(FileExistsError):
        normalize(source, out, tmp_path / 'new.csv')
    with pytest.raises(ValueError):
        normalize(source, source, tmp_path / 'new.csv')
