"""Standalone reproducible report, data and scientific figures from one evaluation."""
import base64
import csv
from html import escape
import io
import json
import math
import os
from pathlib import Path
from threading import Lock
from uuid import uuid4
import zipfile

from backend.database import connect_database
from spectrumagent.storage import guard as storage
from . import ModelingError
from .evaluation import encode, stamp, NAMES
from .classification_curves import curves
from .classification_explanations import interpretation, coefficients, compare
from .classification_maps import tile

_plot_lock = Lock()


def value(v):
    return "不适用" if v is None else format(v, ".6g") if isinstance(v, float) else str(v)


def report_tables(ev):
    short_names = len(ev["classes"]) > 12 or any(len(c["name"]) > 14 for c in ev["classes"])
    matrix_names = ["C"+str(i+1) if short_names else c["name"] for i, c in enumerate(ev["classes"])]
    tables = [("冻结类别目录（图例短码与完整名称）", ["图例短码", "label_id", "完整名称"],
               [["C"+str(i+1), c["id"], c["name"]] for i, c in enumerate(ev["classes"])])]
    for population, pop in ev["populations"].items():
        for scope in ("pixel", "sample"):
            score = pop["scores"][scope]
            tables.append((population + " " + scope + " OOF合并与折间统计",
                ["指标", "OOF合并", "折均值", "折SD", "有效折"],
                [[k, value(score[k]), value(pop["fold_summary"][scope][k]["mean"]),
                  value(pop["fold_summary"][scope][k]["std"]), pop["fold_summary"][scope][k]["n_effective"]] for k in NAMES]
                + [["coverage", value(score["coverage"]), "", "", ""],
                   ["正确接纳比例", value(score["correct_acceptance_ratio"]), "", "", ""]]))
            tables.append((population + " " + scope + " 每类表现", ["类别", "Precision", "Recall", "F1", "真值数", "预测数", "拒识数"],
                [[ev["classes"][c["label"]]["name"], value(c["precision"]), value(c["recall"]), value(c["f1"]),
                  c["support"], c["predicted_count"], c["rejected_count"]] for c in score["per_class"]]))
            # Page-width-safe column groups preserve every cell for large catalogs.
            for start in range(0, len(ev["classes"]), 6):
                tables.append((population + " " + scope + " 混淆矩阵 行真实 列预测 列"+str(start+1)+"起",
                    ["真实/预测"] + matrix_names[start:start+6],
                    [[matrix_names[i]] + row[start:start+6] for i, row in enumerate(score["confusion"])]))
    tables.append(("各折指标", ["折", "总体", "层级", "OA", "AA", "Kappa", "macro-F1"],
        [[f["fold_index"]+1, population, scope] + [value(f[scope][k]) for k in NAMES]
         for population, p in ev["populations"].items() for f in p["folds"] for scope in ("pixel", "sample")]))
    tables.append(("样品主类明细", ["组", "真实主类", "预测主类", "真值数", "接纳数", "真实主类比例"],
        [[r["group"], ev["classes"][r["true_label"]]["name"],
          ev["classes"][r["predicted_label"]]["name"] if r["predicted_label"] is not None else "拒识",
          r["n_true"], r["n_accepted"], value(r["majority_fraction"])] for r in ev["sample_rows"]]))
    return tables


def figures(store, identifier, folder, checkpoint=lambda phase: None, options=None):
    ev = store.get(identifier)
    if ev.get('complete') is False:
        raise ModelingError('INCOMPLETE_EVALUATION', '部分结果请导出训练任务诊断，不能生成完整评价报告')
    options = options or {}
    population = options.get("population", "accepted")
    normalization = options.get("normalization", "count")
    short_names = any(len(c["name"]) > 14 for c in ev["classes"]) or len(ev["classes"]) > 12
    names = ["C"+str(i+1) if short_names else c["name"] for i, c in enumerate(ev["classes"])]
    # Matplotlib cache is session-local, never written into a user profile.
    cache = store.paths.root / "plot-cache"
    storage.mkdir(cache, parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt, font_manager
    import numpy as np
    for candidate in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc"):
        if Path(candidate).exists():
            font_manager.fontManager.addfont(candidate)
            plt.rcParams["font.family"] = font_manager.FontProperties(fname=candidate).get_name()
            break
    plt.rcParams["axes.unicode_minus"] = False
    outputs = []
    def save(name, title, fig):
        try:
            checkpoint("figure:"+name)
            fig.suptitle(title, fontsize=12)
            fig.text(.02, .015, "run " + ev["run_id"] + "\nevaluation " + identifier + " · " + ev["protocol"], fontsize=6)
            fig.tight_layout(rect=(0, .065, 1, .94))
            for ext in ("png", "svg"):
                path = storage.resolve_write(folder/(name+"."+ext), kind="EXPORT_CREATE")
                fig.savefig(path, dpi=180)
        finally:
            plt.close(fig)
        outputs.append({"name": name, "title": title, "png": name+".png", "svg": name+".svg"})
    with _plot_lock:
        for scope in ("pixel", "sample"):
            fig, ax = plt.subplots(figsize=(8, 6))
            score = ev["populations"][population]["scores"][scope]
            key = {"count": "confusion", "row": "row_normalized", "column": "column_normalized"}[normalization]
            matrix = np.asarray(score[key], dtype=float)
            image = ax.imshow(matrix, cmap="Blues", vmin=0, vmax=max(1, float(np.nanmax(matrix))) if np.isfinite(matrix).any() else 1)
            ax.set_xticks(range(len(ev["classes"])), names, rotation=45, ha="right")
            ax.set_yticks(range(len(ev["classes"])), names)
            ax.set_xlabel("预测"); ax.set_ylabel("真实"); fig.colorbar(image, ax=ax, label={"count": "计数", "row": "行占比", "column": "列占比"}[normalization])
            if len(ev["classes"]) <= 12:
                for (r, c), n in np.ndenumerate(matrix):
                    ax.text(c, r, "—" if not np.isfinite(n) else str(int(n)) if normalization == "count" else format(n, ".1%"), ha="center", va="center", fontsize=7,
                            color="white" if np.isfinite(n) and n > image.get_clim()[1]*.6 else "black")
            save("confusion-"+scope, scope+" "+population+" 混淆矩阵 "+normalization, fig)
        fig, ax = plt.subplots(figsize=(8, 4))
        curve = ev["lv"]["curve"]
        ax.errorbar([r["n_components"] for r in curve], [r["rmsecv"] for r in curve], yerr=[r["sd"] for r in curve], marker="o", capsize=3)
        ax.set_xlabel("潜变量数"); ax.set_ylabel("one-hot RMSECV")
        for key, color in (("best_lv", "#0e6e8c"), ("elbow_lv", "#a06a12"), ("selected_lv", "#17714a")):
            ax.axvline(ev["lv"][key], color=color, linestyle="--", label=key)
        ax.legend(fontsize=7); save("lv", "内层选模与折SD", fig)
        if ev["bands"]:
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot([r["index"] for r in ev["bands"]["curve"]], [r["rmsecv"] for r in ev["bands"]["curve"]], "o-")
            ax.set_xlabel("区间编号"); ax.set_ylabel("内层RMSECV")
            save("ipls", "iPLS区间扫描", fig)
        for scope in ("pixel", "sample"):
            for offset in range(0, len(ev["classes"]), 5):
                ranking = curves(store, identifier, scope=scope, offset=offset)
                for kind in ("roc", "pr"):
                    fig, ax = plt.subplots(figsize=(8, 4))
                    for row in ranking["classes"]:
                        if row[kind]:
                            ax.plot([p["x"] for p in row[kind]], [p["y"] for p in row[kind]], label=names[row["label"]])
                    available = any(row[kind] for row in ranking["classes"])
                    if not available:
                        ax.text(.5, .5, "不可计算：当前类别正例或负例不足", ha="center", va="center", transform=ax.transAxes)
                    if kind == "roc" and available:
                        ax.plot([0, 1], [0, 1], "--", color="gray")
                    ax.set_xlabel("FPR" if kind == "roc" else "Recall")
                    ax.set_ylabel("TPR" if kind == "roc" else "Precision")
                    if available:
                        ax.legend(fontsize=8)
                    ax.set_xlim(0, 1); ax.set_ylim(0, 1.02)
                    save(scope+"-"+kind+"-"+str(offset), scope+" "+kind.upper()+" 全体OOF OvR", fig)
        diagnostic = curves(store, identifier)
        fig, ax = plt.subplots(figsize=(8, 4))
        pts = [r for r in diagnostic["risk_coverage"] if r["risk"] is not None]
        ax.plot([r["coverage"] for r in pts], [r["risk"] for r in pts])
        ax.set_xlabel("Coverage"); ax.set_ylabel("Accepted error risk")
        save("risk-coverage", "像素级风险与覆盖率", fig)
        coef = coefficients(store, identifier)
        fig, ax = plt.subplots(figsize=(8, 4))
        x = [r["wavelength"] if r["wavelength"] is not None else r["column"] for r in coef["features"]]
        for name, ys in zip(names, coef["coefficients"]):
            ax.plot(x, ys, label=name)
        ax.set_xlabel((coef["features"][0]["unit"] or "波长单位未知") if coef["features"][0]["wavelength"] is not None else "变换后特征列/成分"); ax.set_ylabel("有符号系数")
        ax.axhline(0, color="gray", linewidth=.5); ax.legend(fontsize=7)
        save("coefficients", "最终模型有符号分类系数 非重要性排序", fig)
        try:
            imp = store.artifact(identifier, "importance-5")
        except ModelingError as error:
            if error.code != "ARTIFACT_NOT_FOUND":
                raise
        else:
            rows = [r for r in imp["top5"] if r["mean"] is not None]
            if rows:
                fig, ax = plt.subplots(figsize=(8, 4))
                ax.barh([r["feature_id"] for r in rows], [r["mean"] for r in rows], xerr=[r["std"] or 0 for r in rows])
                ax.axvline(0, color="gray", linewidth=.5); ax.invert_yaxis()
                ax.set_xlabel("留出macro-F1下降（折均值 ± 折SD）"); ax.set_ylabel("特征")
                save("importance", "重复置换重要性Top5 负值保留 非因果", fig)
    for i, cube in enumerate(ev["cubes"]):
        level = max(0, math.ceil(math.log2(max(cube["shape"][:2])/256)))
        image = tile(store, identifier, cube_index=i, level=level)
        name = "oof-map-"+str(i)
        from PIL import Image as PILImage
        from matplotlib.patches import Patch
        from mpl_toolkits.axes_grid1.anchored_artists import AnchoredSizeBar
        with _plot_lock:
            raster = np.asarray(PILImage.open(io.BytesIO(base64.b64decode(image["png_base64"]))))
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.imshow(raster, interpolation="nearest")
            ax.set_xlabel("列"); ax.set_ylabel("行")
            handles = [Patch(color=c["color"], label=name) for c, name in zip(ev["classes"], names)]
            handles += [Patch(color="#232d36", label="未评价"), Patch(color="#dcaa28", label="拒识")]
            ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8)
            bar = max(1, image["width"]//5)
            ax.add_artist(AnchoredSizeBar(ax.transData, bar, str(bar*2**level)+" px", "lower left",
                                         pad=.3, color="black", frameon=True, size_vertical=.3))
            save(name, "OOF评价图 "+cube["name"]+" 物理尺度未知", fig)
    if options:
        args = {k: options[k] for k in ("layer", "level", "tile_x", "tile_y", "hidden", "colors") if k in options}
        prediction_id = options.get("prediction_id")
        if prediction_id:
            from .classification_inference import ClassificationInference
            reader = ClassificationInference(store.registry, store.paths)
            try:
                current = reader.prediction_tile(prediction_id, **args)
            finally:
                reader.executor.shutdown(wait=True)
            title = "当前新数据预测视图 无真值 不报告精度"
        else:
            current = tile(store, identifier, cube_index=options.get("cube_index", 0), **args)
            title = "当前OOF视图 "+options.get("layer", "prediction")
        with _plot_lock:
            raster = np.asarray(PILImage.open(io.BytesIO(base64.b64decode(current["png_base64"]))))
            fig, ax = plt.subplots(figsize=(8, 4))
            alpha = options.get("opacity", .85)
            # The same verified middle-band base used by the workbench.
            if not prediction_id:
                base = tile(store, identifier, cube_index=options.get("cube_index", 0),
                            **{**args, "layer": "base"})
                ax.imshow(PILImage.open(io.BytesIO(base64.b64decode(base["png_base64"]))), interpolation="nearest")
            else:
                alpha = 1
            ax.imshow(raster, interpolation="nearest", alpha=alpha)
            ax.set_xlabel("当前瓦片列；原像素步长 "+str(2**options.get("level", 0))+" px")
            ax.set_ylabel("当前瓦片行")
            layer = options.get("layer", "prediction")
            if layer == "confidence":
                from matplotlib.colors import LinearSegmentedColormap, Normalize
                from matplotlib.cm import ScalarMappable
                cmap = LinearSegmentedColormap.from_list("score", [(1, 0, 120/255), (0, 1, 120/255)])
                fig.colorbar(ScalarMappable(norm=Normalize(0, 1), cmap=cmap), ax=ax, label="未校准最大分类得分")
            elif layer != "base":
                handles = ([Patch(color="#b83227", label="误分"), Patch(color="#4b5f5f", label="其他已评价")]
                    if layer == "errors" else [Patch(color="#dcaa28", label="拒识"), Patch(color="#4b5f5f", label="其他有效输入")]
                    if layer == "rejected" else [Patch(color=options.get("colors", {}).get(str(c["label"]), c["color"]), label=name)
                    for c, name in zip(ev["classes"], names) if c["label"] not in options.get("hidden", [])])
                ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=8)
            save("current-map", title+"；物理尺度未知", fig)
    return outputs


def export_report(store, identifier, fmt="bundle", figure="confusion-pixel", checkpoint=lambda phase: None, *, options=None):
    owned = []
    try:
        return _export_report(store, identifier, fmt, figure, checkpoint, owned, options)
    except BaseException:
        guard = storage.for_database(store.database)
        root = (guard.output_root if guard.output_root is not None else store.paths.root/"exports").resolve()
        for folder in owned:
            # Only the unique directories allocated by this export are eligible.
            target = folder.resolve()
            if target.is_relative_to(root) and target != root and not folder.is_symlink() and folder.is_dir():
                storage.rmtree(folder)
        raise


def _export_report(store, identifier, fmt, figure, checkpoint, owned, options):
    if fmt not in ("bundle", "html", "pdf", "docx", "json", "csv", "png", "svg"):
        raise ModelingError("INVALID_EXPORT_FORMAT", "不支持的导出格式")
    ev = store.get(identifier)
    if ev.get('complete') is False:
        raise ModelingError('INCOMPLETE_EVALUATION', '部分结果只能导出诊断，不能导出完整评价报告')
    options = options or {}
    export_id = str(uuid4())
    guard = storage.for_database(store.database)
    with connect_database(store.database) as db:
        project = db.execute("SELECT project_id FROM dataset_registry WHERE id=?", (ev["cubes"][0]["cube_id"],)).fetchone()[0]
    root = guard.output_root if guard.output_root is not None else store.paths.root / "exports"
    # Keep Windows MAX_PATH compatibility; complete immutable identities live
    # in the manifest, never rely on long directory names as the evidence.
    final = root / str(project)[:10] / (ev.get("training_set_ref") or "explicit")[:10] / ev["run_id"][:10] / identifier[:10] / export_id[:12]
    folder = final.with_name("_"+final.name)
    if len(str(folder)) + 50 > 250:
        raise ModelingError("EXPORT_PATH_TOO_LONG", "输出根路径过长，请配置较短的输出根")
    storage.mkdir(folder, parents=True)
    owned.append(folder)
    checkpoint("snapshot")
    pack = store.artifact(identifier, "model")
    ranking = {scope: [r for offset in range(0, len(ev["classes"]), 5)
                        for r in curves(store, identifier, scope=scope, offset=offset)["classes"]]
               for scope in ("pixel", "sample")}
    report = {"evaluation": ev, "frozen_model": pack, "ranking": ranking, "view": options, "generated_at": stamp(),
              "interpretation": interpretation(store, identifier, options.get("comparison_id")),
              "omissions": {"importance": "未计算时不自动进行置换计算", "comparison": "未指定比较对象", "inference": "本报告为训练OOF评价"}}
    tables = report_tables(ev)
    if options.get("comparison_id"):
        compared = compare(store, identifier, options["comparison_id"])
        report["comparison"] = compared
        report["omissions"]["comparison"] = None
        tables.append(("实验对比："+("可比" if compared["comparable"] else "不可比 "+",".join(compared["differences"])),
            ["层级/总体", "指标", "当前", "对比", "当前减对比"],
            [[r["scope"]+"/"+r["population"], r["name"], value(r["left"]), value(r["right"]), value(r["difference"])] for r in compared["rows"]]))
        tables.append(("逐类及逐折对比（原单位差）", ["层级/总体", "类别/折", "指标", "当前减对比"],
            [[r["scope"]+"/"+r["population"], r.get("class_name", "折"+str(r.get("fold_index", 0)+1)), r["name"], value(r["difference"])]
             for r in compared["per_class"]+compared["folds"]]))
    if options.get("prediction_id"):
        from .classification_inference import ClassificationInference
        reader = ClassificationInference(store.registry, store.paths)
        try:
            manifest = reader.manifest(options["prediction_id"])
            if reader.models.get(manifest["model_id"])["evaluation_id"] != identifier:
                raise ModelingError("EVALUATION_MISMATCH", "推理产物不属于本报告模型")
            report["prediction"] = manifest
            report["omissions"]["inference"] = "已包含无真值预测分布；不报告新图精度"
            tables.append(("新图预测分布（无真值）", ["统计", "值"],
                [[k, value(v)] for k, v in manifest["stats"].items() if not isinstance(v, (dict, list))]))
            tables.append(("新图预测类别分布", ["label", "类别", "预测数"],
                [[r["label"], ev["classes"][r["label"]]["name"], r["count"]] for r in manifest["stats"]["classes"]]))
        finally:
            reader.executor.shutdown(wait=True)
    tables += [(scope+" 全体OOF排序评价", ["类别", "ROC-AUC", "AP", "正例", "负例"],
                [[r["name"], value(r["roc_auc"]), value(r["ap"]), r["positive"], r["negative"]] for r in rs])
               for scope, rs in ranking.items()]
    try:
        imp = store.artifact(identifier, "importance-5")
        report["importance"] = imp
        tables.append(("留出重复置换重要性Top5", ["特征", "macro-F1下降", "折SD", "有效折"],
                       [[r["feature_id"], value(r["mean"]), value(r["std"]), r["effective_folds"]] for r in imp["top5"]]))
        report["omissions"]["importance"] = None
    except ModelingError as error:
        if error.code != "ARTIFACT_NOT_FOUND":
            raise
    storage.resolve_write(folder/"result.json", kind="EXPORT_CREATE").write_text(encode(report), "utf-8")
    if fmt == "bundle":
        import numpy as np
        observations = store.artifact(identifier, "observations")
        with storage.resolve_write(folder/"oof-predictions.npz", kind="EXPORT_CREATE").open("wb") as stream:
            np.savez_compressed(stream, **{k: v for k, v in observations.items() if k != "X"})
    csv_path = storage.resolve_write(folder/"metrics.csv", kind="EXPORT_CREATE")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["metric_id", "evaluation_id", "dimensions", "value", "undefined_reason", "n_effective"])
        with connect_database(store.database) as db:
            for row in db.execute("SELECT id,evaluation_id,identity_key,value,undefined_reason,n_effective FROM evaluation_metric WHERE evaluation_id=?", (identifier,)):
                cells = list(row)
                if cells[3] is None and not cells[4]:
                    cells[4] = "historical_derived_metric_reason_not_recorded"
                writer.writerow(cells)
    def csv_text(v):
        raw = str(v)
        return "'"+raw if raw.lstrip().startswith(("=", "+", "-", "@")) else raw
    with storage.resolve_write(folder/"tables.csv", kind="EXPORT_CREATE").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        for title, headers, rows in tables:
            writer.writerow([csv_text(title)]); writer.writerow([csv_text(v) for v in headers])
            writer.writerows([[csv_text(v) if isinstance(v, str) else v for v in row] for row in rows])
    with storage.resolve_write(folder/"curve-points.csv", kind="EXPORT_CREATE").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream); writer.writerow(["scope", "label_id", "name", "curve", "x", "y", "display_simplified"])
        for scope, rows in ranking.items():
            for row in rows:
                for kind in ("roc", "pr"):
                    for p in row[kind]:
                        writer.writerow([scope, ev["classes"][row["label"]]["id"], csv_text(row["name"]), kind, p["x"], p["y"],
                                         row.get("original_"+kind+"_points", len(row[kind])) > len(row[kind])])
    # A standalone CSV download includes tables, full-precision scalar evidence
    # and curve coordinates; the bundle also keeps each rectangular table file.
    with storage.resolve_write(folder/"tables.csv", kind="EXPORT_CREATE").open("a", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        for name, caption in (("metrics.csv", "完整精度标量证据与空值原因"), ("curve-points.csv", "曲线显示坐标与简化状态")):
            writer.writerow([]); writer.writerow([caption])
            with (folder/name).open(encoding="utf-8-sig", newline="") as source:
                writer.writerows(csv.reader(source))
    checkpoint("figures")
    plots = figures(store, identifier, folder, checkpoint, options) if fmt not in ("json", "csv") else []
    esc = lambda s: escape(str(s))
    html = "<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>分类结果报告</title><style>body{font:14px/1.6 'Microsoft YaHei',sans-serif;max-width:1080px;margin:30px auto;color:#16202a}table{border-collapse:collapse;width:100%;margin:15px 0}td,th{border:1px solid #ddd;padding:7px;text-align:left}img{max-width:100%}code{overflow-wrap:anywhere}figure{break-inside:avoid}@media print{thead{display:table-header-group}}</style><h1>光谱分类结果报告</h1>"
    intro = ["run "+ev["run_id"], "evaluation "+identifier, "协议 "+ev["protocol"]+"；定义 "+ev["definition"],
             "方法 PLS-DA；分组来源 "+ev["group_kind"]+"；种子 "+str(ev["seed"])+"；最终LV "+str(ev["lv"]["selected_lv"]),
             "有效配方 "+encode(pack["pipeline"]),
             "本报告展示同一评价快照的全体及接纳子集、像素及多数投票结果。折SD不是置信区间。",
             "图像数 "+str(ev["n_images"])+"；有效真值像素 "+str(ev["n_pixels"])+"；阈值 "+str(ev["threshold"])]
    intro += ["导出视图参数 "+encode(options), "生成时间 "+report["generated_at"]+"；代码引用 "+str(ev.get("code_version"))+"；算子 "+ev["operator"]+" v"+str(ev["operator_version"]),
              "完整类别名称见冻结目录；图例过长时使用C序号。各表保留全体和接纳双套，图件采用选择的总体及归一化。"]
    html += "".join("<p>"+esc(s)+"</p>" for s in intro+ev["limitations"])
    html += "<h2>结果解读</h2>" + "".join("<p>"+esc(c["text"])+"<br><code>"+esc(c["metric_id"])+"</code></p>" for c in report["interpretation"]["claims"])
    for title, headers, rows in tables:
        html += "<h2>"+esc(title)+"</h2><table><thead><tr>"+"".join("<th>"+esc(v)+"</th>" for v in headers)+"</tr></thead><tbody>"
        html += "".join("<tr>"+"".join("<td>"+esc(v)+"</td>" for v in row)+"</tr>" for row in rows)+"</tbody></table>"
    for plot in plots:
        data = base64.b64encode((folder/plot["png"]).read_bytes()).decode("ascii")
        html += "<figure><h2>"+esc(plot["title"])+"</h2><img src='data:image/png;base64,"+data+"'></figure>"
    html += "<h2>局限与追溯</h2><p>波长、拒识、分组、模型版本与来源以result.json和metrics.csv为准。未获得的结果不以示例值补齐。</p></html>"
    storage.resolve_write(folder/"report.html", kind="EXPORT_CREATE").write_text(html, "utf-8")
    if fmt in ("pdf", "bundle"):
        checkpoint("pdf")
        prose = intro + [c["text"]+"；metric_id "+c["metric_id"] for c in report["interpretation"]["claims"]]
        prose += report["interpretation"]["limitations"] + report["interpretation"]["suggestions"]
        write_pdf(storage.resolve_write(folder/"report.pdf", kind="EXPORT_CREATE"), ev, prose, tables, plots, folder)
    if fmt in ("docx", "bundle"):
        checkpoint("docx")
        prose = intro + [c["text"]+"；metric_id "+c["metric_id"] for c in report["interpretation"]["claims"]]
        prose += report["interpretation"]["limitations"] + report["interpretation"]["suggestions"]
        write_docx(storage.resolve_write(folder/"report.docx", kind="EXPORT_CREATE"), ev, prose, tables, plots, folder)
    mapping = {"json": "result.json", "csv": "tables.csv", "html": "report.html", "pdf": "report.pdf", "docx": "report.docx"}
    if fmt in ("png", "svg"):
        allowed = {p["name"] for p in plots if fmt in p}
        if figure not in allowed:
            raise ModelingError("FIGURE_NOT_AVAILABLE", "指定图件不存在")
        filename = figure+"."+fmt
    elif fmt == "bundle":
        filename = "classification-"+ev["run_id"][:8]+"-"+identifier[:8]+".zip"
        files = [p for p in folder.iterdir() if p.is_file()]
        manifest = {"export_id": export_id, "run_id": ev["run_id"], "evaluation_id": identifier, "created_at": stamp(),
                    "view": options, "omissions": report["omissions"],
                    "files": [{"filename": p.name, "sha256": store.file_hash(p), "bytes": p.stat().st_size} for p in files]}
        storage.resolve_write(folder/"manifest.json", kind="EXPORT_CREATE").write_text(encode(manifest), "utf-8")
        with zipfile.ZipFile(storage.resolve_write(folder/filename, kind="EXPORT_CREATE"), "w", zipfile.ZIP_DEFLATED) as archive:
            for path in files+[folder/"manifest.json"]:
                checkpoint("archive:"+path.name)
                archive.write(path, path.name)
    else:
        filename = mapping[fmt]
    path = folder/filename
    sha = store.file_hash(path)
    checkpoint("publish")
    if final.exists():
        raise ModelingError("EXPORT_DESTINATION_EXISTS", "导出目录已存在，请重试生成新身份")
    storage.replace(folder, final)
    owned.append(final)
    path = final/filename
    with connect_database(store.database) as db:
        db.execute("INSERT INTO classification_export VALUES (?,?,?,?,?,?)", (export_id, identifier, fmt, str(path), sha, stamp()))
    return {"export_id": export_id, "evaluation_id": identifier, "filename": filename, "bytes": path.stat().st_size, "sha256": sha, "format": fmt}


def write_pdf(path, ev, intro, tables, plots, folder):
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, Image, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    font = "ReportCJK"
    try:
        pdfmetrics.registerFont(TTFont(font, "C:/Windows/Fonts/simsun.ttc", subfontIndex=0))
    except Exception:
        font = "STSong-Light"
        pdfmetrics.registerFont(UnicodeCIDFont(font))
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = font
        style.wordWrap = "CJK"
    styles["Normal"].fontSize = 10
    styles["Normal"].leading = 15
    styles["Heading2"].keepWithNext = True
    doc = SimpleDocTemplate(str(path), pagesize=(612, 792), leftMargin=42, rightMargin=42, topMargin=42, bottomMargin=48)
    body = [Paragraph("光谱分类结果报告", styles["Title"])]
    def bounded_text(text):
        # Explicit soft lines for long recipe JSON; font backends differ in
        # their handling of unspaced ASCII tokens embedded in CJK paragraphs.
        lines, part, width = [], "", 0
        for char in text:
            units = 2 if ord(char) > 255 else 1
            if width+units > 92:
                lines.append(part); part, width = "", 0
            part += char; width += units
        return "<br/>".join(escape(v) for v in lines+[part])
    body += [Paragraph(bounded_text(s), styles["Normal"]) for s in intro+ev["limitations"]]
    for title, headers, rows in tables:
        body += [Spacer(1, 12), Paragraph(escape(title), styles["Heading2"])]
        data = [[Paragraph(escape(str(v)), styles["Normal"]) for v in row] for row in [headers]+rows]
        table = LongTable(data, repeatRows=1, colWidths=[528/len(headers)]*len(headers), hAlign="LEFT")
        table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#e7f3f7")),
                                  ("GRID", (0,0), (-1,-1), .3, colors.HexColor("#d8e0e8")),
                                  ("VALIGN", (0,0), (-1,-1), "TOP"), ("TOPPADDING", (0,0), (-1,-1), 5),
                                  ("BOTTOMPADDING", (0,0), (-1,-1), 5)]))
        body.append(table)
    from PIL import Image as PILImage
    for plot in plots:
        p = folder/plot["png"]
        with PILImage.open(p) as image:
            w, h = image.size
        image_width = min(510, 480*w/h)
        body.append(KeepTogether([Spacer(1, 12), Paragraph(escape(plot["title"]), styles["Heading2"]),
                                  Image(str(p), width=image_width, height=image_width*h/w)]))
    def footer(canvas, document):
        canvas.setFont(font, 6)
        canvas.drawString(42, 24, "run "+ev["run_id"]+" / evaluation "+ev["evaluation_id"])
        canvas.drawRightString(570, 14, str(document.page))
    doc.build(body, onFirstPage=footer, onLaterPages=footer)


def write_docx(path, ev, intro, tables, plots, folder):
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = section.bottom_margin = Inches(.75)
    section.left_margin = section.right_margin = Inches(.75)
    for name in ("Normal", "Title", "Heading 1", "Heading 2"):
        style = document.styles[name]
        style.font.name = "Microsoft YaHei"
        style._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        style.font.color.rgb = RGBColor(0, 0, 0)
        # Explicitly remove decorative borders inherited from document templates.
        for border in list(style._element.iter(qn("w:pBdr"))):
            border.getparent().remove(border)
    document.styles["Normal"].font.size = Pt(11)
    title = document.add_paragraph("光谱分类结果报告", "Title")
    borders = OxmlElement("w:pBdr")
    for edge in ("top", "bottom", "left", "right", "between"):
        element = OxmlElement("w:"+edge)
        element.set(qn("w:val"), "nil")
        borders.append(element)
    title._p.get_or_add_pPr().append(borders)
    for s in intro+ev["limitations"]:
        document.add_paragraph(s)
    for title, headers, rows in tables:
        document.add_heading(title, 1)
        table = document.add_table(rows=1, cols=len(headers))
        table.style = "Light Shading Accent 1"
        header = OxmlElement("w:tblHeader")
        table.rows[0]._tr.get_or_add_trPr().append(header)
        for c, text in zip(table.rows[0].cells, headers):
            c.text = str(text)
        for row in rows:
            for c, text in zip(table.add_row().cells, row):
                c.text = str(text)
        for row_index, row in enumerate(table.rows):
            cant_split = OxmlElement("w:cantSplit")
            row._tr.get_or_add_trPr().append(cant_split)
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    if len(rows) <= 8:
                        paragraph.paragraph_format.keep_with_next = row_index < len(table.rows)-1
                    for run in paragraph.runs:
                        run.font.size = Pt(10)
        document.add_paragraph()
    for plot in plots:
        document.add_heading(plot["title"], 1)
        from PIL import Image as PILImage
        with PILImage.open(folder/plot["png"]) as image:
            width, height = image.size
        document.add_picture(str(folder/plot["png"]), width=Inches(min(6.6, 5.8*width/height)))
    footer = section.footer.paragraphs[0]
    footer.text = "run "+ev["run_id"]+"\nevaluation "+ev["evaluation_id"]
    footer.add_run(" · 第 ")
    page = OxmlElement("w:fldSimple"); page.set(qn("w:instr"), "PAGE")
    footer._p.append(page)
    footer.add_run(" 页")
    for run in footer.runs:
        run.font.size = Pt(7)
    document.save(path)
