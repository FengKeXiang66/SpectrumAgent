"""Numerical summaries and directly viewable reports for completed experiments."""
from html import escape
import json
import os
from pathlib import Path

import numpy as np


def metrics(y, prediction, classes, extras):
    from sklearn.metrics import cohen_kappa_score, confusion_matrix, precision_recall_fscore_support

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
    from matplotlib.font_manager import FontProperties
    from matplotlib.ft2font import FT2Font
    figure = Figure(figsize=(10, 5), constrained_layout=True)
    FigureCanvasAgg(figure)
    ax = figure.subplots()
    for row in curves["classes"]:
        if row["mean"] is None:
            continue
        mean, std = np.asarray(row["mean"]), np.asarray(row["std"])
        line, = ax.plot(curves["axis"], mean, label=f'{row["name"]} (n={row["count"]})')
        ax.fill_between(curves["axis"], mean-std, mean+std, color=line.get_color(), alpha=.12)
    ax.set(title=title, xlabel="Wavelength (nm) / component index", ylabel="Mean +/- population SD")
    glyphs = {ord(char) for row in curves['classes'] if row['mean'] is not None for char in row['name']}
    font = None
    if any(code > 127 for code in glyphs):
        fonts = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
        for name in ('msyh.ttc', 'simhei.ttf', 'simsun.ttc'):
            candidate = fonts / name
            if candidate.is_file() and glyphs <= FT2Font(str(candidate)).get_charmap().keys():
                font = FontProperties(fname=candidate)
                break
    ax.legend(prop=font)
    ax.grid(alpha=.2)
    figure.savefig(path, dpi=140)


def split_warning_banner(test_usage, checks):
    from .inputs import independent_duplicate_warning
    warning = independent_duplicate_warning(test_usage, checks)
    return ('<p data-split-warning="true" role="alert" style="padding:12px;border:2px solid #a22820;'
            'background:#fff2ef;color:#721b15;font-weight:bold">'+escape(warning)+'</p>') if warning else ''


def html_report(result):
    from .inputs import split_check_text
    config = result["config"]
    body = [f'<h1>{escape(config["name"])}</h1>',
            '<p>协议：显式训练/测试。训练指标为拟合成绩。测试用途：' + escape(config["test_usage"]) + '</p>',
            '<p>评价单位：' + escape(config["test"]["evaluation_unit"]) +
            '。曲线按观测等权，阴影为总体标准差。模型响应未经概率校准。</p>',
            '<p>类别：' + escape('、'.join(f'{k}={v}' for k, v in config['classes'].items())) + '</p>']
    body.append('<p style="white-space:pre-line">' + escape(split_check_text(result.get('split_checks'))) + '</p>')
    body.append(split_warning_banner(config['test_usage'], result.get('split_checks')))
    if config.get('notes'):
        body.append('<p style="white-space:pre-line">'+escape(config['notes'])+'</p>')
    if config.get('split_manifest'):
        body.append('<p>数据划分：' + escape(config['split_manifest']['split_id']) +
                    '。保存副本为 split_plan.json。</p>')
        for role, title in (('train', '训练'), ('test', '测试')):
            spec = config[role]
            body.append(f'<p>{title}取谱：{len(spec["members"])} 幅原图，'
                        f'{spec["neighborhood"]}×{spec["neighborhood"]} 邻域，'
                        f'采样步长 {spec["sampling_stride"]} 像元。</p>')
    for role in ("train", "test"):
        score = result["metrics"][role]
        sampling = result.get('datasets', {}).get(role, {}).get('sampling')
        if sampling:
            counts = '、'.join(f'{config["classes"][label]} {item["selected"]}/{item["eligible"]}'
                             for label, item in sampling['class_counts'].items())
            body.append(f'<p>训练类别抽样上限 {sampling["max_per_class"]}，种子 {sampling["sampling_seed"]}。'
                        f'实际抽样数／合格数 {escape(counts)}。</p>')
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
