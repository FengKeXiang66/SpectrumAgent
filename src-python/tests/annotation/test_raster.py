"""A0: TASK-07 R6/R7 invariants, committed before any implementation exists."""
from copy import deepcopy

import numpy as np
import pytest

from spectrumagent.annotation.raster import decode_rle, encode_rle, polygon_mask, rasterize


def region(op="add", *, geometry=None, index=0):
    value = {"region_id": "r-0001", "op": op, "geometry": geometry or {
        "type": "polygon", "points": [[0, 0], [0, 4], [4, 4], [4, 0]]},
        "source": "manual", "created_at": "2026-10-24T00:00:00+00:00"}
    if op == "add":
        value.update(class_index=index, confidence="high")
    return value


def document(*regions):
    return {"schema_version": 1, "raster_rule_version": 1, "cube_id": "cube-1",
            "classes": [{"index": i, "code": code, "name": code, "color": "#000000"}
                        for i, code in enumerate(("PE", "PP"))], "regions": list(regions)}


def test_idempotent_and_input_is_unchanged():
    doc = document(region(), region("uncertain"))
    before = deepcopy(doc)
    first = rasterize(doc, (5, 5))
    np.testing.assert_array_equal(first, rasterize(doc, (5, 5)))
    assert first.dtype == np.int32 and doc == before


def test_add_then_uncertain_is_minus_two_never_blank():
    result = rasterize(document(region(), region("uncertain")), (5, 5))
    assert np.all(result[:4, :4] == -2)
    assert np.all(result[4, :] == -1)


@pytest.mark.parametrize("points", [
    [[.5, .5], [.5, 3.5], [3.5, 3.5], [3.5, .5]],  # centres on edges/vertices
    [[0, 0], [0, 4], [2, 2], [4, 4], [4, 0]],  # concave
    [[0, 0], [0, 7], [7, 7], [7, 0], [0, 0], [2, 2], [5, 2], [5, 5], [2, 5], [2, 2], [0, 0]],  # hole, doubled bridge
])
def test_polygon_branch_is_exactly_frozen_polygon_mask(points):
    shape = (8, 8)
    result = rasterize(document(region(geometry={"type": "polygon", "points": points})), shape)
    expected = np.where(polygon_mask(shape, points), 0, -1).astype(np.int32)
    np.testing.assert_array_equal(result, expected)
    if len(points) > 5:
        assert result[3, 3] == -1 and result[1, 5] == 0
    if points[0] == [.5, .5]:
        assert result[0, 0] == result[3, 3] == 0


def test_region_order_is_sensitive_not_commutative():
    first, second = region(index=0), region(index=1)
    a = rasterize(document(first, second), (5, 5))
    b = rasterize(document(second, first), (5, 5))
    assert a[1, 1] == 1 and b[1, 1] == 0
    assert not np.array_equal(a, b)


def test_cross_row_rle_and_polygon_mix_same_class_overlap():
    rows = [[0, 1, 3], [1, 0, 2], [2, 2, 3]]
    pixel_set = {"type": "pixel_set", "rows": rows, "segments_fingerprint": {"n_segments": 3}}
    doc = document(region(geometry=pixel_set), region())
    expected = polygon_mask((5, 5), region()["geometry"]["points"]) | decode_rle(rows, (5, 5))
    np.testing.assert_array_equal(rasterize(doc, (5, 5)), np.where(expected, 0, -1).astype(np.int32))


def test_erase_and_uncovered_are_blank_but_have_distinct_document_history():
    erased = document(region(), region("erase"))
    np.testing.assert_array_equal(rasterize(erased, (5, 5)), rasterize(document(), (5, 5)))
    assert [entry["op"] for entry in erased["regions"]] == ["add", "erase"]
    uncertain = rasterize(document(region(), region("erase"), region("uncertain")), (5, 5))
    assert uncertain[0, 0] == -2 and uncertain[4, 4] == -1


def test_rle_round_trip_random_masks_is_bit_exact():
    rng = np.random.default_rng(int.from_bytes(b"RLE", "little"))
    for shape in [(1, 1), (3, 8), (17, 11)]:
        for mask in [np.zeros(shape, bool), np.ones(shape, bool), rng.integers(0, 2, shape).astype(bool)]:
            before = mask.copy()
            rows = encode_rle(mask)
            np.testing.assert_array_equal(decode_rle(rows, shape), mask)
            np.testing.assert_array_equal(mask, before)
            assert rows == sorted(rows)
