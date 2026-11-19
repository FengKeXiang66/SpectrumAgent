"""Numerical summaries and directly viewable reports for completed experiments."""
from html import escape
import json

import numpy as np
from sklearn.metrics import cohen_kappa_score, confusion_matrix, precision_recall_fscore_support


def metrics(y, prediction, classes, extras):
    labels = sorted(classes)
    precision, recall, f1, support = precision_recall_fscore_support(y, prediction, labels=labels, zero_division=0)
    present = support > 0
    matrix = confusion_matrix(y, prediction, labels=labels)
    result = {"n": len(y), "correct": int((y == prediction).sum()), "accuracy": float((y == prediction).mean()),
              "macro_precision": float(precision[present].mean()), "macro_recall": float(recall[present].mean()),
              "macro_f1": float(f1[present].mean()), "macro_labels": np.asarray(labels)[present].tolist(),
              "confusion_labels": labels, "confusion": matrix.tolist(),
              "definition": "macro over classes present in truth; zero precision contributes zero to macro", "per_class": []}
    for i, label in enumerate(labels):
        predicted = int(matrix[:, i].sum())
        result["per_class"].append({"label": label, "name": classes[label], "support": int(support[i]),
                                    "predicted": predicted, "precision": float(precision[i]) if predicted else None,
                                    "recall": float(recall[i]) if support[i] else None,
                                    "f1": float(f1[i]) if support[i] else None})
    if "kappa" in extras:
        value = float(cohen_kappa_score(y, prediction, labels=labels))
        result["kappa"] = value if np.isfinite(value) else None
    if "weighted_f1" in extras:
        result["weighted_f1"] = float(np.average(f1, weights=support))
    if "balanced_accuracy" in extras:
        result["balanced_accuracy"] = result["macro_recall"]
    return result


def representative_curves(X, y, classes, axis):
    rows = []
    for label in sorted(classes):
        values = X[y == label]
        rows.append({"label": label, "name": classes[label], "count": len(values),
                     "mean": values.mean(axis=0).tolist() if len(values) else None,
                     "std": values.std(axis=0, ddof=0).tolist() if len(values) else None})
    return {"axis": axis, "aggregation": "equal_weight_per_observation", "std_ddof": 0, "classes": rows}


def curve_plot(curves, path, title):
    # Object API avoids changing pyplot's global backend in the desktop server.
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    figure = Figure(figsize=(10, 5), constrained_layout=True)
    FigureCanvasAgg(figure)
    ax = figure.subplots()
    for row in curves["classes"]:
        if row["mean"] is None:
            continue
        mean, std = np.asarray(row["mean"]), np.asarray(row["std"])
        line, = ax.plot(curves["axis"], mean, label=f'{row["label"]} (n={row["count"]})')
        ax.fill_between(curves["axis"], mean-std, mean+std, color=line.get_color(), alpha=.12)
    ax.set(title=title, xlabel="Wavelength (nm) / component index", ylabel="Mean +/- population SD")
    ax.legend()
    ax.grid(alpha=.2)
    figure.savefig(path, dpi=140)


def html_report(result):
    config = result["config"]
    body = [f'<h1>{escape(config["name"])}</h1>',
            '<p>协议：显式训练/测试。训练指标为拟合成绩。测试用途：' + escape(config["test_usage"]) + '</p>',
            '<p>评价单位：' + escape(config["test"]["evaluation_unit"]) +
            '。曲线按观测等权，阴影为总体标准差。模型响应未经概率校准。</p>',
            '<p>类别：' + escape('、'.join(f'{k}={v}' for k, v in config['classes'].items())) + '</p>']
    for role in ("train", "test"):
        score = result["metrics"][role]
        body.append(f'<h2>{role}</h2><p>{score["correct"]}/{score["n"]}，准确率 {score["accuracy"]:.4%}，'
                    f'Macro-F1 {score["macro_f1"]:.6f}</p>')
        body.append('<table><tr><th>类别</th><th>真值数</th><th>精确率</th><th>召回率</th><th>F1</th></tr>')
        for row in score["per_class"]:
            body.append('<tr>' + ''.join('<td>'+escape(str(row[k]))+'</td>' for k in ("name", "support", "precision", "recall", "f1"))+'</tr>')
        body.append('</table><details><summary>完整指标与混淆矩阵</summary><pre>'+escape(json.dumps(score, ensure_ascii=False, indent=2))+'</pre></details>')
        for stage in ("input", "processed"):
            body.append(f'<img src="{role}_{stage}.png" alt="{role} {stage} class means">')
    return ('<!doctype html><html lang="zh"><meta charset="utf-8"><title>光谱实验结果</title>'
            '<style>body{font:16px sans-serif;max-width:1100px;margin:30px auto;padding:20px}'
            'table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:8px}img{max-width:100%}</style>'
            + ''.join(body) + '</html>')
