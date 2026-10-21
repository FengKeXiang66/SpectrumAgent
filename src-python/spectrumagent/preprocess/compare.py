"""B10 pixel-derived metrics and explicit recipe comparison; no aggregate SQL."""
from itertools import combinations

import numpy as np

from .registry import invalid, json_safe


BOUNDARIES = [
    "TASK-05 §2.5 边界1：SNR 跨算子类型不可比，仅同类算子内相对比较。",
    "TASK-05 §2.5 边界2：零方差/单样本类排除 Fisher；该类样本不足，未参与选优；不加 epsilon。",
    "TASK-05 §2.5 边界3：类间距离原值不可跨配方比；按卡以 Fisher 为主排序。",
]


class PixelMetrics:
    def __init__(self):
        self.snr = []
        self.labels = {}
        self.nan_spectra_skipped = 0
        self.snr_nan_count = 0

    def update(self, spectra, labels):
        finite = np.isfinite(spectra).all(axis=1)
        self.nan_spectra_skipped += int((~finite).sum())
        x, indices = spectra[finite], labels[finite]
        if not len(x):
            return
        rms = np.sqrt(np.mean(np.diff(x, axis=1)**2, axis=1)) if x.shape[1] > 1 else np.zeros(len(x))
        good = rms != 0
        self.snr_nan_count += int((~good).sum())
        self.snr.extend((x[good].mean(axis=1)/rms[good]).tolist())
        for index in np.unique(indices[indices >= 0]):
            selected = x[indices == index]
            state = self.labels.setdefault(int(index), {
                "count": 0, "sum": np.zeros(x.shape[1]), "sumsq": np.zeros(x.shape[1]),
                "first": selected[0].copy(), "identical": True})
            state["identical"] &= bool(np.all(selected == state["first"]))
            state["count"] += len(selected)
            state["sum"] += selected.sum(axis=0)
            state["sumsq"] += (selected*selected).sum(axis=0)

    def result(self, *, labeled):
        values = np.asarray(self.snr)
        snr = {"mean": None, "median": None, "p10": None, "p90": None, "n_pixels": len(values)}
        if len(values):
            snr.update(mean=float(values.mean()), median=float(np.median(values)),
                       p10=float(np.percentile(values, 10)), p90=float(np.percentile(values, 90)))
        moments, eligible, excluded, all_classes = {}, [], [], []
        for index, state in sorted(self.labels.items()):
            count = state["count"]
            mean = state["sum"]/count
            variance = np.maximum(state["sumsq"]/count-mean*mean, 0.)
            if state["identical"]:
                variance[:] = 0.
            moments[index] = {"count": count, "mean": mean, "std": np.sqrt(variance)}
            # Trace of population covariance: squared Euclidean deviation/pixel.
            pooled = float(variance.sum())
            all_classes.append((mean, pooled, count))
            if count <= 1 or pooled == 0:
                excluded.append({"label_index": index, "pixel_count": count,
                                 "reason": "该类样本不足，未参与选优"})
            else:
                eligible.append((mean, pooled, count))
        result = {"snr": snr, "snr_nan_count": self.snr_nan_count,
                  "nan_spectra_skipped": self.nan_spectra_skipped,
                  "boundaries": list(BOUNDARIES), "excluded_classes": excluded,
                  "limitations": [], "source": "TASK-05 §2.5/§2.6 R12；确定性逐像素计算，无 LLM 数值",
                  "variance_definition": "实现层口径：每类逐像素平方欧氏偏差均值（population covariance trace），按类像素数加权"}
        if labeled:
            distances = [float(np.linalg.norm(a[0]-b[0])) for a, b in combinations(eligible, 2)]
            fisher_within = sum(var*n for _, var, n in eligible)/sum(n for _, _, n in eligible) if eligible else None
            fisher_between = float(np.mean(distances)) if distances else None
            raw_distances = [float(np.linalg.norm(a[0]-b[0])) for a, b in combinations(all_classes, 2)]
            within = sum(var*n for _, var, n in all_classes)/sum(n for _, _, n in all_classes) if all_classes else None
            between = float(np.mean(raw_distances)) if raw_distances else None
            result.update(interclass_distance=between, intraclass_variance=within,
                          fisher=fisher_between/fisher_within if fisher_between is not None and fisher_within is not None and fisher_within != 0 else None,
                          fisher_components={"interclass_distance": fisher_between, "intraclass_variance": fisher_within})
        else:
            result["limitations"].append("未标注数据：仅 SNR；类间距离、类内方差及 Fisher 无标签不适用。")
        return json_safe(result), moments


def ranking(runs):
    eligible = [run for run in runs if run["status"] == "succeeded" and run["metrics"].get("fisher") is not None]
    eligible.sort(key=lambda row: (-row["metrics"]["fisher"], row["recipe_version_id"]))
    return [{"rank": i+1, "run_id": row["id"], "recipe_version_id": row["recipe_version_id"],
             "fisher": row["metrics"]["fisher"]} for i, row in enumerate(eligible)]


class CompareEngine:
    def __init__(self, runner):
        self.runner = runner

    def compare(self, cube_id, annotation_version_id, recipe_version_ids, **run_options):
        if not isinstance(recipe_version_ids, list) or not recipe_version_ids:
            raise invalid("recipe_version_ids", "必须显式指定至少一个配方版本")
        runs = [self.runner.run(cube_id, annotation_version_id, version, **run_options)
                for version in recipe_version_ids]
        return {"runs": runs, "ranking": ranking(runs), "boundaries": list(BOUNDARIES),
                "selection": "TASK-05 §2.5：Fisher 主排序，确定性计算；LLM 不参与数值判断"}
