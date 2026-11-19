"""Versioned classification evidence. Reads never create identities or rewrite runs."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import PurePosixPath
from uuid import uuid4, uuid5, NAMESPACE_URL
from collections import OrderedDict
from threading import Lock

import numpy as np

from backend.database import connect_database
from spectrumagent.storage import guard as storage
from . import ModelingError
from .metrics import classification_scores, classification_fold_summary, _vote

DEFINITION = "classification-v2"
NAMES = ("oa", "aa", "kappa", "macro_f1")
DDL = """
CREATE TABLE IF NOT EXISTS classification_evaluation (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES training_run(id),
 protocol TEXT NOT NULL, definition TEXT NOT NULL, snapshot TEXT NOT NULL,
 created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS classification_evaluation_run ON classification_evaluation(run_id);
CREATE TABLE IF NOT EXISTS evaluation_metric (
 id TEXT PRIMARY KEY, evaluation_id TEXT NOT NULL REFERENCES classification_evaluation(id),
 identity_key TEXT NOT NULL, value REAL, undefined_reason TEXT, n_effective INTEGER NOT NULL,
 UNIQUE(evaluation_id,identity_key));
CREATE TABLE IF NOT EXISTS evaluation_artifact (
 id TEXT PRIMARY KEY, evaluation_id TEXT NOT NULL REFERENCES classification_evaluation(id),
 kind TEXT NOT NULL, relative_path TEXT NOT NULL, sha256 TEXT NOT NULL,
 UNIQUE(evaluation_id,kind));
CREATE TABLE IF NOT EXISTS classification_model (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES training_run(id),
 evaluation_id TEXT NOT NULL REFERENCES classification_evaluation(id),
 name TEXT NOT NULL, version INTEGER NOT NULL, project_id TEXT NOT NULL,
 catalog_hash TEXT NOT NULL, model_hash TEXT NOT NULL,
 stage TEXT NOT NULL CHECK(stage IN ('experiment','candidate')),
 created_at TEXT NOT NULL, UNIQUE(name,version), UNIQUE(evaluation_id,name));
CREATE TABLE IF NOT EXISTS classification_baseline (
 scope_key TEXT PRIMARY KEY, model_id TEXT NOT NULL REFERENCES classification_model(id),
 evaluation_id TEXT NOT NULL REFERENCES classification_evaluation(id),
 updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS classification_baseline_event (
 id TEXT PRIMARY KEY, scope_key TEXT NOT NULL, previous_model_id TEXT,
 model_id TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS classification_prediction (
 id TEXT PRIMARY KEY, model_id TEXT NOT NULL REFERENCES classification_model(id),
 cube_id TEXT NOT NULL REFERENCES dataset_registry(id), manifest TEXT NOT NULL,
 created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS classification_export (
 id TEXT PRIMARY KEY, evaluation_id TEXT NOT NULL REFERENCES classification_evaluation(id),
 format TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL);
"""


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


def matrix_detail(score, y_true, y_pred, groups, labels, scope):
    """All derived counts and normalization are operator results, not UI arithmetic."""
    matrix = np.asarray(score["confusion"], dtype=np.int64)
    rows, cols = matrix.sum(axis=1), matrix.sum(axis=0)
    correct, accepted = int(np.trace(matrix)), int(matrix.sum())
    true, pred, group = np.asarray(y_true), np.asarray(y_pred), np.asarray(groups)
    if scope == "sample":
        pairs = [(_vote(true[group == g]), _vote(pred[(group == g) & (pred >= 0)])
                  if np.any((group == g) & (pred >= 0)) else -2) for g in np.unique(group)]
        true, pred = (np.asarray([p[i] for p in pairs]) for i in (0, 1))
    total = len(true)
    rejected = [int(np.sum((true == label) & (pred < 0))) for label in labels]
    per_class = []
    for i, row in enumerate(score["per_class"]):
        tp = int(matrix[i, i])
        per_class.append({**row, "support": int(rows[i]), "predicted_count": int(cols[i]),
                          "tp": tp, "fp": int(cols[i])-tp, "fn": int(rows[i])-tp,
                          "rejected_count": rejected[i]})
    errors = [{"true_label": labels[i], "predicted_label": labels[j], "count": int(matrix[i, j]),
               "row_fraction": float(matrix[i, j]/rows[i]) if rows[i] else None}
              for i in range(len(labels)) for j in range(len(labels)) if i != j and matrix[i, j]]
    return {**score, "per_class": per_class, "row_totals": rows.tolist(), "column_totals": cols.tolist(),
            "row_normalized": [[float(v/rows[i]) if rows[i] else None for v in matrix[i]] for i in range(len(rows))],
            "column_normalized": [[float(v/cols[j]) if cols[j] else None for j, v in enumerate(row)] for row in matrix],
            "total": total, "accepted": accepted, "rejected": total-accepted,
            "correct": correct, "incorrect": accepted-correct,
            "coverage": accepted/total if total else None,
            "correct_acceptance_ratio": correct/total if total else None,
            "effective_classes": {"aa": sum(c["recall"] is not None for c in per_class),
                                  "macro_f1": sum(c["f1"] is not None for c in per_class)},
            "top_errors": sorted(errors, key=lambda e: (-e["count"], e["true_label"], e["predicted_label"]))[:20]}


def summarize(true, raw_pred, groups, confidence, fold_index, *, labels, threshold):
    true, raw_pred, groups = np.asarray(true), np.asarray(raw_pred), np.asarray(groups)
    confidence, fold_index = np.asarray(confidence), np.asarray(fold_index)
    pred = raw_pred.copy()
    pred[confidence < threshold] = -2
    populations = {}
    for population, prediction in (("all_labeled", raw_pred), ("accepted", pred)):
        scores = classification_scores(true, prediction, groups, labels=labels)
        folds = [{"fold_index": int(f), **classification_scores(true[fold_index == f], prediction[fold_index == f],
                   groups[fold_index == f], labels=labels)} for f in np.unique(fold_index)]
        summary = classification_fold_summary(folds)
        for scope in ("pixel", "sample"):
            for name in NAMES:
                summary[scope][name]["n_effective"] = sum(row[scope][name] is not None for row in folds)
        populations[population] = {
            "scores": {scope: matrix_detail(scores[scope], true, prediction, groups, labels, scope)
                       for scope in ("pixel", "sample")},
            "folds": folds, "fold_summary": summary}
    sample_rows = []
    for g in np.unique(groups):
        mask = groups == g
        voted = pred[mask & (pred >= 0)]
        values, counts = np.unique(true[mask], return_counts=True)
        sample_rows.append({"group": int(g), "true_label": int(_vote(true[mask])),
                            "predicted_label": int(_vote(voted)) if len(voted) else None,
                            "n_true": int(mask.sum()), "n_accepted": len(voted),
                            "truth_distribution": [{"label": int(v), "count": int(n)} for v, n in zip(values, counts)],
                            "majority_fraction": float(counts.max()/counts.sum())})
    return {"populations": populations, "sample_rows": sample_rows,
            "threshold": float(threshold), "tie_rule": "smallest frozen class index"}


class Evaluations:
    def __init__(self, registry, paths):
        self.registry, self.paths, self.database = registry, paths, registry.database
        self._verified, self._verify_lock = OrderedDict(), Lock()

    def create(self, run_id, snapshot, *, documents=None, arrays=None, matrices=None, links=None):
        identifier = str(uuid4())
        folder = self.paths.root / "models" / run_id / identifier
        storage.mkdir(folder, parents=True)
        artifacts, created = {}, []
        try:
            for kind, document in (documents or {}).items():
                path = folder / (kind + ".json")
                raw = encode(document).encode("utf-8")
                storage.resolve_write(path, kind="WRITE_BYTES").write_bytes(raw)
                created.append(path)
                artifacts[kind] = {"artifact_id": str(uuid4()), "sha256": hashlib.sha256(raw).hexdigest(),
                                   "relative_path": path.relative_to(self.paths.root / "models").as_posix()}
            for kind, values in (arrays or {}).items():
                path = folder / (kind + ".npz")
                with storage.resolve_write(path, kind="WRITE_BYTES").open("wb") as stream:
                    np.savez_compressed(stream, **values)
                created.append(path)
                artifacts[kind] = {"artifact_id": str(uuid4()), "sha256": self.file_hash(path),
                                   "relative_path": path.relative_to(self.paths.root / "models").as_posix()}
            for kind, values in (matrices or {}).items():
                path = folder/(kind+".npy")
                with storage.resolve_write(path, kind="WRITE_BYTES").open("wb") as stream:
                    np.save(stream, values, allow_pickle=False)
                created.append(path)
                artifacts[kind] = {"artifact_id": str(uuid4()), "sha256": self.file_hash(path),
                                   "relative_path": path.relative_to(self.paths.root/"models").as_posix()}
            for kind, source in (links or {}).items():
                # Immutable owned artifact; derived thresholds need no spectrum copy.
                with connect_database(self.database) as db:
                    row = db.execute("SELECT relative_path,sha256 FROM evaluation_artifact WHERE evaluation_id=? AND kind=?", (source, kind)).fetchone()
                if row is None:
                    raise ModelingError("ARTIFACT_NOT_FOUND", "派生评价所需源产物不存在")
                artifacts[kind] = {"artifact_id": str(uuid4()), "relative_path": row[0], "sha256": row[1]}
            snapshot = {**snapshot, "evaluation_id": identifier, "run_id": run_id, "schema_version": 2,
                        "definition": DEFINITION, "artifacts": artifacts, "created_at": stamp()}
            evidence = []
            for population, report in snapshot["populations"].items():
                for scope, score in report["scores"].items():
                    targets = [(name, score[name], None, None, "pooled", score["accepted"]) for name in NAMES]
                    targets += [(name, score[name], None, None, "pooled", score["total"])
                                for name in ("coverage", "correct_acceptance_ratio")]
                    targets += [(name, row[name], row["label"], None, "pooled", row["support"])
                                for row in score["per_class"] for name in ("precision", "recall", "f1")]
                    targets += [(name, row[scope][name], None, row["fold_index"], "fold", 1)
                                for row in report["folds"] for name in NAMES]
                    targets += [(name, summary[name][stat], None, None, stat, summary[name]["n_effective"])
                                for summary in [report["fold_summary"][scope]] for name in NAMES for stat in ("mean", "std")]
                    refs = {}
                    for name, value, class_id, fold_id, aggregation, n in targets:
                        key = encode({"population": population, "scope": scope, "name": name,
                                      "class_id": class_id, "fold_id": fold_id, "aggregation": aggregation})
                        metric_id = str(uuid5(NAMESPACE_URL, identifier + key))
                        reason = "undefined_denominator_or_insufficient_support" if value is None else None
                        evidence.append((metric_id, identifier, key, value, reason, int(n)))
                        refs[key] = metric_id
                    score["metric_refs"] = refs
            with connect_database(self.database) as db:
                db.execute("INSERT INTO classification_evaluation VALUES (?,?,?,?,?,?)",
                           (identifier, run_id, snapshot["protocol"], DEFINITION, encode(snapshot), stamp()))
                db.executemany("INSERT INTO evaluation_metric VALUES (?,?,?,?,?,?)", evidence)
                db.executemany("INSERT INTO evaluation_artifact VALUES (?,?,?,?,?)",
                    [(v["artifact_id"], identifier, k, v["relative_path"], v["sha256"]) for k, v in artifacts.items()])
            return snapshot
        except BaseException:
            for path in created:
                storage.unlink(path, missing_ok=True)
            raise

    @staticmethod
    def file_hash(path):
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024*1024), b""):
                h.update(block)
        return h.hexdigest()

    def verify(self, path, expected):
        """Hash once per unchanged owned file, bounded cache, recheck on edits."""
        try:
            stat = path.stat()
            signature = (stat.st_size, stat.st_mtime_ns, stat.st_ino, expected)
            with self._verify_lock:
                if self._verified.get(path) == signature:
                    self._verified.move_to_end(path)
                    return
            actual = self.file_hash(path)
            after = path.stat()
            if actual != expected or (after.st_size, after.st_mtime_ns, after.st_ino) != signature[:3]:
                raise ModelingError("ARTIFACT_HASH_MISMATCH", "评价产物缺失、变化或摘要不一致")
            with self._verify_lock:
                self._verified[path] = signature
                while len(self._verified) > 64:
                    self._verified.popitem(last=False)
        except FileNotFoundError:
            raise ModelingError("ARTIFACT_HASH_MISMATCH", "评价产物不存在") from None

    def get(self, identifier):
        with connect_database(self.database) as db:
            row = db.execute("SELECT snapshot FROM classification_evaluation WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise ModelingError("EVALUATION_NOT_FOUND", "评价快照不存在")
        return json.loads(row[0])

    def latest(self, run_id):
        with connect_database(self.database) as db:
            row = db.execute("SELECT id FROM classification_evaluation WHERE run_id=? "
                             "AND protocol IN ('nested_group_cv','exploratory_group_cv') "
                             "AND json_extract(snapshot,'$.parent_evaluation_id') IS NULL ORDER BY created_at DESC,id DESC LIMIT 1",
                             (run_id,)).fetchone()
        return self.get(row[0]) if row else None

    def cache(self, identifier, kind, document):
        snapshot = self.get(identifier)
        if not kind.replace("-", "").replace("_", "").isalnum():
            raise ModelingError("INVALID_ARTIFACT", "派生产物类型非法")
        folder = self.paths.root / "models" / snapshot["run_id"] / identifier
        raw = encode(document).encode("utf-8")
        expected = hashlib.sha256(raw).hexdigest()
        path = folder / (kind + "-" + expected[:16] + ".json")
        artifact_id = str(uuid5(NAMESPACE_URL, identifier + "/" + kind))
        storage.resolve_write(path, kind="WRITE_BYTES").write_bytes(raw)
        with connect_database(self.database) as db:
            db.execute("INSERT INTO evaluation_artifact VALUES (?,?,?,?,?) ON CONFLICT(evaluation_id,kind) DO UPDATE SET "
                       "relative_path=excluded.relative_path,sha256=excluded.sha256",
                       (artifact_id, identifier, kind, path.relative_to(self.paths.root / "models").as_posix(), expected))
        return {"artifact_id": artifact_id, "sha256": expected}

    def scalar(self, identifier, identity, value, n_effective=0, reason=None):
        key = encode(identity)
        metric_id = str(uuid5(NAMESPACE_URL, identifier + key))
        if value is not None and not np.isfinite(value):
            raise ModelingError("INVALID_METRIC_INPUT", "证据标量必须有限或为空")
        with connect_database(self.database) as db:
            db.execute("INSERT INTO evaluation_metric VALUES (?,?,?,?,?,?) ON CONFLICT(evaluation_id,identity_key) DO NOTHING",
                       (metric_id, identifier, key, value,
                        (reason or "undefined_denominator_or_insufficient_support") if value is None else None, n_effective))
        return metric_id

    def artifact(self, identifier, kind, fields=None):
        with connect_database(self.database) as db:
            row = db.execute("SELECT relative_path,sha256 FROM evaluation_artifact WHERE evaluation_id=? AND kind=?",
                             (identifier, kind)).fetchone()
        if not row:
            raise ModelingError("ARTIFACT_NOT_FOUND", "评价产物不存在")
        relative = PurePosixPath(row[0])
        base = (self.paths.root / "models").resolve()
        path = base.joinpath(*relative.parts).resolve()
        if relative.is_absolute() or ".." in relative.parts or "\\" in row[0] or ":" in row[0] or not path.is_relative_to(base):
            raise ModelingError("INVALID_ARTIFACT", "评价产物引用非法")
        self.verify(path, row[1])
        if path.suffix == ".npz":
            with np.load(path, allow_pickle=False) as archive:
                return {k: archive[k].copy() for k in (archive.files if fields is None else fields) if k in archive.files}
        if path.suffix == ".npy":
            return np.load(path, allow_pickle=False, mmap_mode="r")
        return json.loads(path.read_text("utf-8"))

    def spectra(self, identifier, selection):
        try:
            matrix = self.artifact(identifier, "raw_spectra")
        except ModelingError as error:
            if error.code != "ARTIFACT_NOT_FOUND":
                raise
            # Compatibility for early v2 evaluation artifacts, never rewrite them.
            return self.artifact(identifier, "observations", fields=["X"])["X"][selection].copy()
        try:
            return matrix[selection].copy()
        finally:
            matrix._mmap.close()
