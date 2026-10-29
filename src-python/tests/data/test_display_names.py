from copy import deepcopy
import json
from pathlib import Path
import sys

from spectrumagent.api.registry import display_names, safe_name

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from display_catalog import PAIRS, catalog_rows


def test_four_mode_pairs_and_seven_unique_names():
    rows = catalog_rows()
    original = deepcopy(rows)
    names = display_names(rows)
    assert len(names) == 15 and len(set(names.values())) == 15
    assert [names[f"id-{i}"] for i in range(1, 8)] == [f"unique-{i}" for i in range(7)]
    for i, name in enumerate(PAIRS, 8):
        assert names[f"id-{i}"] == f"{name}（反射率）"
        assert names[f"id-{i + 4}"] == f"{name}（原始 DN）"
    assert rows == original
    print("A", json.dumps(names, ensure_ascii=False))


def test_unique_names_keep_exact_safe_name_projection():
    values = [r"C:\private\one.hdr", "/nas/two.IMG", "Note: three.mat",
              "long-" + "a" * 200, "", "control\x00name"]
    rows = [(str(i), value, i % 2) for i, value in enumerate(values)]
    names = display_names(iter(rows))
    assert names == {identifier: safe_name(value) for identifier, value, _ in rows}
    assert display_names([]) == {}
    print("B", json.dumps(names, ensure_ascii=False))


def test_same_mode_collisions_are_stable_and_cannot_steal_unique_names():
    rows = [("a", "sample.hdr", 1), ("b", "sample.img", 1),
            ("c", "sample.mat", 0), ("d", "sample（原始 DN）", 0),
            ("e", "sample（原始 DN #2）", 0)]
    names = display_names(rows)
    assert names["a"] == "sample（原始 DN #3）"
    assert names["b"] == "sample（原始 DN #4）"
    assert names["c"] == "sample（反射率）"
    assert names["d"] == "sample（原始 DN）"
    assert names["e"] == "sample（原始 DN #2）"
    assert len(set(names.values())) == len(rows)
    assert display_names(rows) == names
    assert display_names([*rows, ("f", "sample", 1)])["a"] == names["a"]
    print("C", json.dumps(names, ensure_ascii=False))
