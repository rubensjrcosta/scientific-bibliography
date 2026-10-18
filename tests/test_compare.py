from pathlib import Path
from scripts.audit import compare_bibliographies


def test_comparison(tmp_path: Path):
    original = tmp_path / "original.bib"
    incoming = tmp_path / "incoming.bib"
    original.write_text('''@article{Smith2020, author={Smith, A.}, title={An interesting astrophysics paper}, year={2020}, journal={Journal}, doi={10.1234/abc}}''', encoding="utf-8")
    incoming.write_text('''@article{DifferentKey, author={Smith, A.}, title={An interesting astrophysics paper}, year={2020}, journal={Journal}, doi={https://doi.org/10.1234/abc}}
@article{Jones2022, author={Jones, B.}, title={A completely new cosmic ray study}, year={2022}, journal={Journal}}''', encoding="utf-8")
    result = compare_bibliographies(incoming, original)
    assert result["counts"] == {"possible_duplicate": 1, "candidate_new": 1}
    assert result["rows"][0]["existing_keys"] == "Smith2020"
