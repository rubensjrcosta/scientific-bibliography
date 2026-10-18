import pytest
from scripts.classify import classify_entry, run, load


def test_multilabel():
    labels, evidence, status = classify_entry({"title": "Gamma-ray emission from a pulsar wind nebula"})
    assert status == "classified"
    assert {"gamma_ray_astronomy", "pulsars_pwn"} <= set(labels)
    assert evidence


def test_unclassified_not_assumed_general():
    labels, _, status = classify_entry({"title": "An unrelated experimental study"})
    assert labels == [] and status == "unclassified"


def test_placeholder_title_review():
    labels, _, status = classify_entry({"title": "No Title"})
    assert labels == [] and status == "review_title"


def test_preserve_metadata_and_source(tmp_path):
    source = tmp_path / "master.bib"
    original = '@article{Example2024, title={Gamma-ray emission from pulsars}, author={A. Author}, year={2024}, journal={ApJ}, keywords={original}, doi={10.1234/example}}\n'
    source.write_text(original, encoding="utf-8")
    output, report, summary = (tmp_path / x for x in ("classified.bib", "report.csv", "summary.json"))
    stats = run(source, output, report, summary)
    assert stats["total_entries"] == 1
    assert source.read_text(encoding="utf-8") == original
    entry = load(output).entries[0]
    assert entry["ID"] == "Example2024"
    assert entry["keywords"] == "original"
    assert "gamma_ray_astronomy" in entry["bib_categories"]
    with pytest.raises(FileExistsError):
        run(source, output, report, summary)
