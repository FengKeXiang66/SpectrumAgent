"""Summarize existing measurements, never rerun or tune engines."""
import csv
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    result = json.loads((HERE / "e2e-result.json").read_text("utf-8"))
    assert result["passed"]
    old = next(row for row in csv.DictReader((ROOT / "milestone04/evidence/calibration/compactness.csv").open(encoding="utf-8"))
               if row["cube"] == "pe/20260804205214_64.hdr" and float(row["compactness"]) == .5)
    saved_http = [e["http_seconds"] for e in result["events"] if e["path"].endswith("/annotations/save") and e["status"] == 200]
    saves = [{**row, "http_seconds": http} for row, http in zip(result["saves"], saved_http, strict=True)]
    observations = result["fixed_twenty"]["observations"]
    diffusion = {f"{kind}_{stat}_seconds": function([row[f"{kind}_seconds"] for row in observations])
                 for kind in ("engine", "http") for stat, function in (("min", min), ("median", statistics.median), ("max", max))}
    segmentation = result["superpixels"]
    performance = {"source_level": "implementation measurements; wall-clock perf_counter; not a product latency guarantee",
                   "e2e_source": "e2e-result.json", "environment": result["environment"],
                   "header": result["header"], "shape": segmentation["shape"],
                   "execution": "real isolated source sidecar / authenticated loopback HTTP / CPU / default parameters; measured before test and compile gates",
                   "params": segmentation["params"],
                   "superpixels": {k:segmentation[k] for k in ("pca_seconds", "slic_seconds", "total_seconds", "n_before", "n_after", "feature_bytes", "resident_feature_bytes", "baseline_rss_bytes", "peak_rss_bytes", "peak_rss_delta_bytes")},
                   "prior_10_2_pe_default": {"source": "../calibration/compactness.csv", **old},
                   "raw_float64_cube_bytes_reference": 231*640*200*8,
                   "rss_delta_fraction_of_raw_cube_reference": segmentation["peak_rss_delta_bytes"]/(231*640*200*8),
                   "final_sidecar_peak_rss_bytes": result["final_sidecar_peak_rss_bytes"],
                   "diffusion_fixed_twenty": {"n_after": segmentation["n_after"], "threshold": .92, "queue_min_similarity": .80, **diffusion,
                                             "candidate_two_second_value_met": diffusion["engine_max_seconds"] <= 2},
                   "validate": result["validate"], "saves": saves,
                   "timing_boundaries": {"http": "client call through full response body; includes routing, header reads, JSON/PNG serialization and transport",
                                         "diffusion_engine": "existing DiffusionEngine.generate elapsed_seconds: readable, growth, candidate PNG and queue deepcopy; excludes HTTP serialization",
                                         "save_elapsed": "existing SessionStore.save elapsed_seconds: aggregation + quality + snapshot + DB; excludes prerequisite checks and HTTP serialization",
                                         "write_transaction": "existing transaction_seconds: connect/BEGIN IMMEDIATE, os.replace publication, row writes and commit; aggregation and temporary snapshot preparation occur before it"}}
    (HERE / "performance.json").write_text(json.dumps(performance, ensure_ascii=False, indent=2)+"\n", "utf-8")
    rows = "\n".join(f"| {name} | {row['elapsed_seconds']:.6f} | {row['transaction_seconds']:.6f} | {row['http_seconds']:.6f} |" for name,row in zip(("v1 新建无 note", "v2 新建带 note", "v2 覆写带 note"), saves, strict=True))
    text = f"""# 10.7 真实性能记录

来源与层级：`e2e-result.json` / `performance.json`，实现层实测；真实 pe `20260804205214_64.hdr`，231×640×200，磁盘 BIL=(231,200,640)。真实独立 sidecar、CPU、默认参数 n=800/m=0.5/PCA=5/k=3/block=32；无缓存预热分割、无调参，未与回归/编译同时测。每项单次测量，扩散取固定 20 种子逐次值；不构成跨机器时延承诺。环境为 `{result['environment']['platform']}`，Python `{result['environment']['python'].split()[0]}`；完整环境见 JSON。

| 操作 | 内部总耗时(s) | 写事务(s) | HTTP(s) |
|---|---:|---:|---:|
{rows}

保存内部耗时沿用 10.3 `save-timing.json` 口径，含当前工作态原谱聚合、质量校验、快照与落库；10.3 的旧值来自夹具，仅作计时边界来源，不作本表数据。写事务计时从连接/BEGIN 到发布快照、重写行并提交，原谱读取、聚合和 `.tmp` 快照准备发生在此前。HTTP 多含路由前置检查、序列化和传输。三次中最大写事务为 {max(r['transaction_seconds'] for r in saves):.6f}s。

独立 validate HTTP 耗时 {result['validate']['http_seconds']:.6f}s；{result['validate']['comparison_count']} 个已标部分比较，{result['validate']['suspicious_count']} 个可疑。阈值 {result['validate']['threshold']} 为 10.3 合成标注标定的实现层可调默认值。这里的矩形标签也是合成集成输入，不代表人工标注质量。

默认固定 20 种子扩散：引擎 min/median/max={diffusion['engine_min_seconds']:.6f}/{diffusion['engine_median_seconds']:.6f}/{diffusion['engine_max_seconds']:.6f}s；HTTP min/median/max={diffusion['http_min_seconds']:.6f}/{diffusion['http_median_seconds']:.6f}/{diffusion['http_max_seconds']:.6f}s。细分后 n={segmentation['n_after']}，满足 §6.3 的 2s 候选值；未经阈值/种子调优。0.92 是场景 S1 示例默认，0.80 是 S05 队列默认。单击之外的框选与涂鸦亦跑通，逐请求 HTTP 耗时见 events。

超像素本次 PCA={segmentation['pca_seconds']:.6f}s、初次 SLIC={segmentation['slic_seconds']:.6f}s、引擎总计={segmentation['total_seconds']:.6f}s（总计还包含原谱统计、细分与 PNG）。10.2 同一 cube/默认档的历史 PCA={float(old['pca_seconds']):.6f}s、SLIC={float(old['slic_seconds']):.6f}s、总计={float(old['total_seconds']):.6f}s，来源 `../calibration/compactness.csv`；卡中的 3.2/0.1s 只作量级参考，非阈值。

特征图 {segmentation['feature_bytes']:,} 字节，含 pre-clip 参照驻留 {segmentation['resident_feature_bytes']:,} 字节；sidecar 基线 RSS {segmentation['baseline_rss_bytes']:,}、峰值 {segmentation['peak_rss_bytes']:,}、增量 {segmentation['peak_rss_delta_bytes']:,} 字节。增量为原始 float64 cube 对照 236,544,000 字节的 {performance['rss_delta_fraction_of_raw_cube_reference']*100:.4f}%；完整 HTTP 链后峰值 {result['final_sidecar_peak_rss_bytes']:,} 字节。Windows WorkingSet/PeakWorkingSet 口径沿用 10.2，不清空工作集。是否全量读取另由有界读取测试佐证，不能单凭 RSS 证明。独立快照复算使用最多 32 原谱行，且在时延测量完成后于脚本进程执行，不计入 sidecar 峰值。

复跑：仓库根 `E:/AI_Agent/.venv/Scripts/python.exe milestone04/evidence/10.7/e2e.py`，再运行同目录 `summarize.py`。runtime/TEMP/TMP 均在 E 盘，脚本不会改源数据或固定种子；HTTP、快照、谱误差与源哈希断言必须全部通过才写成功结果。侧车健康检查按 JSON 身份校验，业务响应逐次校验 boot_id/pid；日志与响应均检查 token 不泄漏。
"""
    (HERE / "performance.md").write_text(text, "utf-8")


if __name__ == "__main__":
    main()
