"""Tests for scripts.export (requires bibtexparser 1.x)."""
import pytest
from scripts.export import export_topics, parse_bib


def test_export_multilabel_and_unclassified(tmp_path):
    source = tmp_path / "classified.bib"
    source.write_text('''@article{A2020, title={Gamma-ray pulsar}, author={A, B}, year={2020}, bib_categories={gamma_ray_astronomy, pulsars_pwn}}\n@article{B2021, title={Other}, author={C, D}, year={2021}}\n''', encoding="utf-8")
    output = tmp_path / "topics"
    result = export_topics(source, output)
    assert result["total_entries"] == 2
    assert result["unclassified_entries"] == 1
    assert [e["ID"] for e in parse_bib(output / "gamma_ray_astronomy.bib").entries] == ["A2020"]
    assert [e["ID"] for e in parse_bib(output / "pulsars_pwn.bib").entries] == ["A2020"]
    assert [e["ID"] for e in parse_bib(output / "unclassified.bib").entries] == ["B2021"]
    with pytest.raises(FileExistsError):
        export_topics(source, output)
    assert export_topics(source, output, overwrite=True)["total_entries"] == 2


def test_never_overwrite_source(tmp_path):
    source = tmp_path / "cosmic_rays.bib"
    original = '@article{A2020, title={X}, author={A, B}, year={2020}, bib_categories={cosmic_rays}}'
    source.write_text(original, encoding="utf-8")
    with pytest.raises(ValueError):
        export_topics(source, tmp_path, overwrite=True)
    assert source.read_text(encoding="utf-8") == original
