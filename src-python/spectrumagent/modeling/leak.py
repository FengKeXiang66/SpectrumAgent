"""Visible preflight findings; acknowledging full-data fit does not remove it."""
from itertools import combinations

FULL_FIT_REASON = "现有算子 fit-on-apply 合一（preprocess/operators/standardize.py L1）；阶段一接受全数据拟合"
GLOBAL_FIT_OPERATORS = frozenset({"standardize", "msc", "emsc", "pca", "mnf", "ica"})


def preflight_report(meta, folds, *, strategy):
    overlaps = [{"fold_index": fold["fold_index"],
                 "overlap_groups": sorted(set(fold["train_groups"]) & set(fold["test_groups"]))} for fold in folds]
    duplicates = []
    for left, right in combinations(meta["cubes"], 2):
        reasons = []
        if left["input_fingerprint"] == right["input_fingerprint"]:
            reasons.append("input_fingerprint")
        # Compare the whole header+data content identity, not just shared headers.
        if left.get("source_hashes") and left["source_hashes"] == right.get("source_hashes"):
            reasons.append("source_hashes")
        if reasons:
            duplicates.append({"cube_ids": [left["cube_id"], right["cube_id"]], "reasons": reasons})
    affected = sorted({step["op"] for cube in meta["cubes"] for step in cube["pipeline"]["steps"]
                       if step["op"] in GLOBAL_FIT_OPERATORS})
    violations = sum(len(item["overlap_groups"]) for item in overlaps)
    return {"group_cross_fold": {"violation_count": violations, "folds": overlaps},
            "duplicate_content": {"duplicate_count": len(duplicates), "pairs": duplicates},
            "preprocess_full_fit": {"acknowledged": True, "reason": FULL_FIT_REASON, "affected_steps": affected},
            "random_split_requested": strategy == "random",
            "random_split_warning": "随机像素划分可能使同一cube跨训练/测试，不能代替按cube验证" if strategy == "random" else None,
            "passed": violations == 0 and not duplicates}
