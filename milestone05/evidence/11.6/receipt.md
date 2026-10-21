# 11.6 回执

范围：S06 前端 + R15/D1 曲线。TASK-05 工作区 313 行原样入库，未自行修卡。没有进入 11.7。

## 测试结果与执行模式

| 检查 | 模式 | 结果 |
|---|---|---|
| Python 全量 | 仓库根 `.venv/Scripts/python.exe -m pytest backend/tests src-python/tests -q`，默认参数；同一 PowerShell 命令设置 E 盘 `PYTEST_DEBUG_TEMPROOT` | **621 passed / 0 failed / 0 skipped**，新增 4；10 条依赖弃用警告见原输出 |
| Rust 全量 | `src-tauri` 目录 `cargo test`，默认 features、默认并行，含 unit/integration/doc；offline，仅 TEMP/TMP 置 E 盘 | **56 passed / 0 failed / 0 ignored**，未新增 Rust 测试 |
| node 全量 | 托管 `C:/Users/Administrator/.workbuddy-ai/binaries/node/versions/22.22.2-6/node.exe --test src/components/preprocess/*.test.ts src/components/datasets/*.test.ts src/components/annotation/*.test.ts`，默认 runner | **59 passed / 0 failed / 0 skipped**；既有 31 未改，新增 28 |
| TypeScript | 托管 Node 22.22.2 加入 PATH 后 `npx --no-install tsc --noEmit` | **exit 0**，无诊断；`--no-install` 防止隐式下载 |

首次 D1 定向 pytest 的四项断言全通过，但沙箱退出时无法清理既有 `pytest-current`，进程 exit 1；未计为验收成功。随后按同一根目录/default 参数进行完整回归，在允许清理 E 盘临时目录的权限下正常 exit 0，详见 `pytest-full.txt`。未安装依赖。

## 新测试落点

- `src-python/tests/preprocess/test_curves.py`：四个测试函数。默认 False 空 before；最终 True 的 B01 类和/计数与未标注整体均值；Standard/PCA/MNF/ICA 拟合遍不污染；crop→resample 独立抽样、每类 ≤512、无输入轴 null、全 NaN 后谱 null。
- `src/components/preprocess/api.test.ts`：14 条。12 op 精确投影、运行体不透传 guard/block_size/UI 字段、report 已解析 JSON/npz 二进制包装/204 null。
- `src/components/preprocess/pipeline.test.ts`：8 条。目录/参数校验/纯轴维护/当前 source/编排/空链/无轴禁用/null 断线。
- `src/components/preprocess/panel.test.ts`：6 条。新 run 详情匹配恢复、错误信封、提交 TRANSPORT 自动恢复与未知状态、图例映射、组件接线与全局对话条边界、阶段二声明。

## 真实 run 曲线

`curves-sample.json` 为真实 pe `20260804205214_64.hdr` 的 RunEngine 产物摘录。复用 10.7 已存标注版本，只读备份数据库并复制快照到独立 `.runtime/m05-11.6/` 根后执行内置 `plastic-snv-sg1`，原 10.7 数据与证据不写入。

- run：`b10ce045-fa35-4ee4-af6f-35571454b964`，succeeded；默认 block_size=32 / guard=clip，B01=scale。
- 标注版本：`06c7481b-4aef-472d-8303-188a8b0a9d5f`。
- 曲线类别 index 1 = 17,996 像素、index 2 = 18,004 像素，合计 36,000；前后各 200 波段，无抽样缩减。
- report SHA256：`48c181a94dd6cabc41d0aac71ae3807bb7fcfa63e8022ca66cacae77ad4ae727`。
- 这些是 10.7 脚本合成集成区域，不冒充人工标注，不形成质量断言。

## 改动文件（逐路径）

1. `TASK-05-预处理.md`（科祥 R15，313 行，原样入库）
2. `src-python/spectrumagent/preprocess/run.py`（仅 D1：before/after 曲线采集、确定性抽样、写 report.curves；原执行/拟合/指标/落库逻辑不改）
3. `src-python/tests/preprocess/test_curves.py`
4. `src/components/datasets/DatasetPanel.tsx`（同标注模式的入口与视图切换）
5. `src/components/preprocess/api.ts`
6. `src/components/preprocess/types.ts`
7. `src/components/preprocess/pipeline.ts`
8. `src/components/preprocess/PreprocessPanel.tsx`
9. `src/components/preprocess/PipelineEditor.tsx`
10. `src/components/preprocess/CompareChart.tsx`
11. `src/components/preprocess/preprocess.css`
12. `src/components/preprocess/api.test.ts`
13. `src/components/preprocess/pipeline.test.ts`
14. `src/components/preprocess/panel.test.ts`
15. `milestone05/evidence/11.6/node-test.txt`
16. `milestone05/evidence/11.6/tsc.txt`
17. `milestone05/evidence/11.6/pytest-full.txt`
18. `milestone05/evidence/11.6/cargo-test.txt`
19. `milestone05/evidence/11.6/curves-sample.json`
20. `milestone05/evidence/11.6/receipt.md`
21. `milestone05/evidence/11.6/summary.json`
22. `milestone05/evidence/11.6/acceptance-map.md`

## 边界核对和保留项

`git diff src-tauri/` 与 `git diff src-python/spectrumagent/api/preprocess.py` 均零输出；11.1–11.5 既有测试、package/Cargo 依赖文件、App/footer 均未改。seed SHA256 仍为 `388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2`。公司两份文档不入库。

§5.1 原文“开放 11 个”与它逐名列出的 10 个存在数量笔误；实现严格取逐名名单并排除 reflectance/msc/emsc，未添加第 11 个卡外算子，未改卡。`runs` 摘要没有 recipe_version_id，恢复通过新摘要 id 查 get_run 详情核对，不扩摘要。无模型支持的四项和 MSC/EMSC 均按卡标注阶段二/不适用。13 条逐项见 `acceptance-map.md`；实机 UI 冒烟留科祥。11.6 提交后停等复核。
