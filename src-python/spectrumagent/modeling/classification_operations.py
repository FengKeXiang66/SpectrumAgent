"""One typed local API boundary for classification workbench operations."""
from . import ModelingError
from .evaluation import Evaluations, summarize
from .classification_curves import curves
from .classification_maps import tile, pixel
from .classification_models import ClassificationModels
from .classification_inference import ClassificationInference
from .classification_explanations import coefficients, importance, compare, interpretation, cloud_interpretation


def operations_for(registry, paths):
    """API and Agent share the same bounded queue and session task receipts."""
    with registry.lock:
        current = getattr(registry, "_classification_operations", None)
        if current is None:
            current = ClassificationOperations(registry, paths)
            registry._classification_operations = current
        return current


class ClassificationOperations:
    def __init__(self, registry, paths):
        self.store = Evaluations(registry, paths)
        self.models = ClassificationModels(registry, paths)
        self.tasks = ClassificationInference(registry, paths)

    def perform(self, identifier, action, body):
        ev = self.store.get(identifier)
        if ev.get('complete') is False:
            raise ModelingError('INCOMPLETE_EVALUATION', '部分结果须从训练任务诊断入口读取')
        from backend.database import connect_database
        with connect_database(self.store.database) as db:
            status = db.execute("SELECT status FROM training_run WHERE id=?", (ev["run_id"],)).fetchone()
        if not status or status[0] != "succeeded":
            raise ModelingError("RUN_NOT_READY", "训练未成功，不能消费未发布的评价")
        if action == "choices":
            import json
            from .evaluation import digest, encode
            with connect_database(self.store.database) as db:
                project = db.execute("SELECT project_id FROM dataset_registry WHERE id=?", (ev["cubes"][0]["cube_id"],)).fetchone()[0]
                scope = encode({"project": project, "task": "classification", "catalog": digest([c["id"] for c in ev["classes"]]),
                                "protocol": ev["protocol"], "definition": ev["definition"]})
                baseline = db.execute("SELECT evaluation_id,model_id FROM classification_baseline WHERE scope_key=?", (scope,)).fetchone()
                rows = db.execute("SELECT e.snapshot FROM classification_evaluation e JOIN training_run r ON r.id=e.run_id "
                    "WHERE r.status='succeeded' AND e.protocol IN ('nested_group_cv','exploratory_group_cv') "
                    "ORDER BY e.created_at DESC LIMIT ? OFFSET ?", (body.limit, body.offset)).fetchall()
                choices = []
                for row in rows:
                    candidate = json.loads(row[0])
                    member = db.execute("SELECT project_id FROM dataset_registry WHERE id=?", (candidate["cubes"][0]["cube_id"],)).fetchone()
                    if member and member[0] == project:
                        choices.append({k: candidate[k] for k in ("evaluation_id", "run_id", "protocol", "threshold", "created_at")})
            return {"evaluation_id": identifier, "baseline_evaluation_id": baseline[0] if baseline else None,
                    "baseline_model_id": baseline[1] if baseline else None, "items": choices, "offset": body.offset}
        if action == "evaluate_prediction":
            if not body.prediction_id or not body.annotation_version_id:
                raise ModelingError("TRUTH_REQUIRED", "须指定推理产物与匹配的冻结标注版本")
            prediction = self.tasks.manifest(body.prediction_id)
            if self.models.get(prediction["model_id"])["evaluation_id"] != identifier:
                raise ModelingError("EVALUATION_MISMATCH", "推理产物不属于当前评价模型")
            return self.tasks.calculate(identifier, "evaluate_prediction", {"prediction": body.prediction_id, "truth": body.annotation_version_id},
                lambda: self.tasks.evaluate(body.prediction_id, body.annotation_version_id))
        if action == "curves":
            return curves(self.store, identifier, scope=body.scope, offset=body.offset, limit=min(5, body.limit))
        if action == "map":
            if body.prediction_id:
                if self.models.get(self.tasks.manifest(body.prediction_id)["model_id"])["evaluation_id"] != identifier:
                    raise ModelingError("EVALUATION_MISMATCH", "推理产物不属于当前评价模型")
                return self.tasks.prediction_tile(body.prediction_id, layer=body.layer, level=body.level,
                                                  tile_x=body.tile_x, tile_y=body.tile_y, hidden=body.hidden, colors=body.colors)
            return tile(self.store, identifier, cube_index=body.cube_index, layer=body.layer, level=body.level,
                        tile_x=body.tile_x, tile_y=body.tile_y, hidden=body.hidden, colors=body.colors)
        if action == "pixel":
            return pixel(self.store, identifier, cube_index=body.cube_index, row=body.row, column=body.column,
                         true_label=body.true_label, predicted_label=body.predicted_label, offset=body.offset, limit=body.limit,
                         all_cubes=body.all_cubes, end_row=body.end_row, end_column=body.end_column)
        if action == "coefficients":
            return coefficients(self.store, identifier)
        if action == "importance":
            return self.tasks.calculate(identifier, "importance", {"repeats": body.repeats},
                                        lambda checkpoint: importance(self.store, identifier, body.repeats, checkpoint), contextual=True)
        if action == "compare":
            if not body.comparison_id:
                raise ModelingError("COMPARISON_REQUIRED", "请指定另一个评价快照")
            return compare(self.store, identifier, body.comparison_id)
        if action == "interpret":
            if body.cloud:
                return self.tasks.calculate(identifier, "interpret", {"comparison": body.comparison_id},
                                            lambda: cloud_interpretation(self.store, identifier, body.comparison_id))
            return interpretation(self.store, identifier, body.comparison_id)
        if action == "register":
            return self.models.register(identifier, body.name)
        if action == "baseline":
            model = self.models.get(body.model_id) if body.model_id else self.models.register(identifier, body.name)
            if model["evaluation_id"] != identifier:
                raise ModelingError("EVALUATION_MISMATCH", "基线模型不属于当前评价")
            return self.models.baseline(model["id"], body.clear)
        if action == "infer":
            model = self.models.get(body.model_id) if body.model_id else self.models.register(identifier, body.name)
            if model["evaluation_id"] != identifier:
                raise ModelingError("EVALUATION_MISMATCH", "推理模型不属于当前评价")
            return self.tasks.submit(model["id"], body.cube_ids, body.threshold)
        if action in ("task", "cancel", "retry"):
            if not body.task_id:
                raise ModelingError("TASK_REQUIRED", "缺少后台任务标识")
            snapshot = self.tasks.status(body.task_id, body.offset, body.limit)
            if snapshot["evaluation_id"] != identifier:
                raise ModelingError("EVALUATION_MISMATCH", "后台任务不属于当前评价")
            return snapshot if action == "task" else self.tasks.cancel(body.task_id) if action == "cancel" else self.tasks.retry(body.task_id)
        if action == "export":
            from .classification_export import export_report
            options = body.model_dump(include={"comparison_id", "prediction_id", "scope", "population", "normalization",
                "cube_index", "layer", "level", "tile_x", "tile_y", "hidden", "colors", "opacity"})
            if body.prediction_id:
                prediction = self.tasks.manifest(body.prediction_id)
                if self.models.get(prediction["model_id"])["evaluation_id"] != identifier:
                    raise ModelingError("EVALUATION_MISMATCH", "导出推理产物不属于当前评价模型")
            return self.tasks.calculate(identifier, "export", {"format": body.format, "figure": body.figure, **options},
                lambda checkpoint: export_report(self.store, identifier, body.format, body.figure, checkpoint, options=options), contextual=True)
        if action == "threshold":
            if body.threshold is None:
                raise ModelingError("INVALID_CONFIDENCE_THRESHOLD", "缺少拒识阈值")
            obs = self.store.artifact(identifier, "observations")
            report = summarize(obs["y"], obs["probabilities"].argmax(axis=1), obs["groups"], obs["probabilities"].max(axis=1),
                               obs["fold_index"], labels=list(range(len(ev["classes"]))), threshold=body.threshold)
            # New evaluation and fresh evidence, original run and truth remain immutable.
            derived = {k: v for k, v in ev.items() if k not in ("evaluation_id", "created_at", "artifacts", "populations", "sample_rows")}
            return self.store.create(ev["run_id"], {**derived, **report, "parent_evaluation_id": identifier},
                documents={"model": {**self.store.artifact(identifier, "model"), "confidence_threshold": body.threshold},
                           "fold_models": self.store.artifact(identifier, "fold_models")},
                arrays={"observations": obs}, links={"raw_spectra": identifier} if "raw_spectra" in ev["artifacts"] else None)
        raise ModelingError("INVALID_CLASSIFICATION_ACTION", "未知结果操作")
