import pytest
from conftest import FIXTURE_PACKS

from athar.curriculum import load_pack


def test_loads_concepts_and_edges():
    pack = load_pack("mini-maths", packs_dir=FIXTURE_PACKS)
    assert pack.id == "mini-maths"
    assert pack.grades == (1, 6)
    assert len(pack.concepts) == 11
    assert pack.concepts["division"].requires == ("multiplication",)
    assert pack.concepts["area"].skills == ("spatial-reasoning",)
    assert pack.graph.has_edge("multiplication", "division")
    assert pack.skill_kinds == {"spatial-reasoning": "thinking", "persistence": "disposition"}


def test_prerequisites_ancestors_dependents():
    pack = load_pack("mini-maths", packs_dir=FIXTURE_PACKS)
    assert pack.prerequisites("division") == ["multiplication"]
    assert pack.ancestors("ratios") == ["fractions", "division", "multiplication", "addition", "counting"]
    assert pack.ancestors("area") == ["multiplication", "shapes-2d", "addition", "counting"]
    assert pack.dependents("addition") == ["multiplication", "subtraction"]
    assert pack.ancestors("counting") == []


def test_label_falls_back_to_english_then_id():
    pack = load_pack("mini-maths", packs_dir=FIXTURE_PACKS)
    assert pack.label("division", "fr") == "La division"
    assert pack.label("ratios", "fr") == "Ratios and proportion"
    assert pack.label("geometry", "fr") == "Géométrie"
    assert pack.label("visual_models") == "Visual models such as arrays and bar models"
    assert pack.label("no-such-id") == "no-such-id"


def test_pack_is_cached():
    assert load_pack("mini-maths", packs_dir=FIXTURE_PACKS) is load_pack("mini-maths", packs_dir=FIXTURE_PACKS)


def test_default_dir_comes_from_env(monkeypatch):
    monkeypatch.setenv("ATHAR_PACKS", str(FIXTURE_PACKS))
    assert load_pack("mini-maths").id == "mini-maths"


def _write_pack(folder, concepts: str) -> None:
    (folder / "bad").mkdir()
    (folder / "bad" / "pack.yaml").write_text(
        "id: bad\nname: Bad\nsubject: maths\ngrades: [1, 2]\n"
        "strands: [{id: number, label: {en: Number}}]\nskills: []\napproaches: []\n"
        f"concepts:\n{concepts}", encoding="utf-8")


def test_cycle_is_rejected(tmp_path):
    _write_pack(tmp_path, "  - {id: a, label: {en: A}, strand: number, grade: 1, requires: [b]}\n"
                          "  - {id: b, label: {en: B}, strand: number, grade: 1, requires: [a]}\n")
    with pytest.raises(ValueError, match="cycle"):
        load_pack("bad", packs_dir=tmp_path)


def test_unknown_reference_is_rejected(tmp_path):
    _write_pack(tmp_path, "  - {id: a, label: {en: A}, strand: shapes, grade: 1, requires: [zzz]}\n")
    with pytest.raises(ValueError) as err:
        load_pack("bad", packs_dir=tmp_path)
    assert "unknown strand 'shapes'" in str(err.value)
    assert "unknown concept 'zzz'" in str(err.value)


def test_missing_pack_raises(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        load_pack("nothing-here", packs_dir=tmp_path)
