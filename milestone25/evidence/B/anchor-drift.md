# B 段收口前锚点复核

来源：eb1b25b 任务卡 §0.2、§3.3、§3.5、§6，与当前 B 段源码 grep -n 原文对照。完整原文见 anchors-after-B.txt；执行脚本 before-anchor-commands.ps1。此文件仅上报漂移，没有改任务卡。

| 路径 / 判定点 | 卡内行号 | B 段后行号 |
|---|---|---|
| src/components/datasets/types.ts · mergeRecords | 35 | 50 |
| 同文件 · Map / set / values | 36 / 37 / 38 | 51 / 52 / 53 |
| 同文件 · DatasetTransport（§3.5） | 26–33 范围内，声明起点 27 | 37–48（SpectrumRegion 仍在 26） |
| src-python/spectrumagent/api/schemas.py · all_datasets | 35 | 36 |
| src-python/spectrumagent/api/registry.py · UNIQUE | 120 | 121 |
| 同文件 · 导入查重 SELECT | 156 | 177 |
| 同文件 · 导入 INSERT | 165 | 199 |
| 同文件 · 全库 all_records | 174 | 231 |
| 同文件 · readable / read_header | 200 / 204 | 258 / 262 |
| 同文件 · payload UPDATE（含§6红线9） | 161 | 219 |
| src/components/datasets/api.ts · 目录选择 | 35 | 44 |

未漂移的全部既有锚点：App.tsx 54 / 85；DatasetPanel.tsx 48；types.ts all_datasets 15；display_names.test.ts G2 14；api.ts Request 6；Rust serde / enum 51 / 52；backend/database.py 10；paths.py NAS 8 / 9、属性 40 / 44 / 48 / 52 / 56；agent/state.py 166 / 173；llm.py 136；mat.py 52 / 88 / 190；session.py 387–389 / 405；guard.py 329 / 333 / 337 / 341 / 345 / 349；modeling/migrations.py 68–102；projection_io.py 21 / 73 / 74。

§3.3 补充复核同样未漂移：session.py 361、modeling/run.py 176、modeling/inference.py 225、preprocess/run.py 165 / 245，annotations / root/projects 的实际路径保持任务卡裁定。

B 段提交后，C 段按即停条款等待备卡方统一校准以上锚点，再继续开工闸门。
