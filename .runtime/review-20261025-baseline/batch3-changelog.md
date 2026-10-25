# 批3第一波原型修订变更日志

授权：用户本批四处精确修订指令。起始HEAD：d3e327aa4a5c1925ea62806fe4086acf8bbbcb74；原型版本保持ui-v2.3。

## 第0步核验

- 工作区仅原有5个未跟踪公司文档，无其他改动；本批无恢复动作。
- L258/L894/L1946/L1844/L2310原文和行号均与实物相符；release-notes L14为指定MAT条目，L15为空行，无偏差。
- 原型LF计数（等价wc -l）与物理行数均为2976；需求哈希与既定基线一致。
- 批1的53条片段/49个原行正向重放得到批2第0步备份；批2的16条片段重放得到本批修改前原型；本批与既有两批改动行集合无交集。
- batch2-original.html哈希为78de8b003efa53e80b5231df27b2ed1d407e7bd2faaa9cd83106698d13fb1a8f，保持不变。
- 受保护已跟踪文件4318件已记录聚合哈希，提交前重新核验；原有5个未跟踪文档哈希已记录。

```text
?? SpecMetis_vs_SpectrumAgent_架构对比_20261022.md
?? 光谱Agent_D域编排_讨论交接摘要_20261022.md
?? 光谱平台_阶段一_代码审查与进度分析_20261018.md
?? 光谱平台_阶段一_需求符合度与质量评估_20261022.md
?? 光谱数据AI-Agent处理平台_阶段一技术选型_定稿v1.1_1792327262075_csvb.md
```

### 指定原行只读核对

- L258：".p-metric .v{font-size:22px; font-weight:750; color:var(--brand-d); line-height:1.15; font-variant-numeric:tabular-nums;}"
- L894："    <li><strong>主色只用于\"可点击\"和\"已选中\"。</strong>标题、正文、表格数字都不用主色，避免界面到处是蓝绿色块而失去视觉锚点。</li>"
- L1946："                  <div class=\"p-metric\"><div class=\"v\">94.5%</div><div class=\"l\">总体精度 OA（OOF子集汇总，按像素加权）</div><div class=\"src\">metrics.oa · v1.3 · run_…0412</div></div>"
- L1844："                  <button class=\"p-btn\">作为模板保存</button>"
- L2310："                  <button class=\"p-btn\">导出会话</button>"

## 修改清单

仅原型L258/L1844/L2310及release-notes新增L15。仓库提交固定为本日志、status-matrix.json、docs/release-notes-v0.3.0.md；外部原型不入Git。

## 每项old→new

| 项目 | old→new | 结论及边界 |
|---|---|---|
| N05 / L258 | .p-metric .v的color值var(--brand-d)→var(--ink) | 原型自身约束满足；其他字节和其他主色规则不变 |
| S02 / L1844 | 作为模板保存按钮→指定S02注释 | 原型自身约束满足；配方版本化与训练MAT导出保留 |
| S03 / L2310 | 导出会话按钮→指定S03注释 | 原型自身约束满足；FR-L10审计导出保留 |
| release-notes / 新L15 | 原L14之后插入指定LLM设置条目 | 其余原28行逐字节保持；不改发布状态 |

## 可重放片段

原型line为不位移原行；release-notes以完整原L14作非空插入锚点，其new_fragment保留该行并追加新L15。四条记录均可按文件全文精确替换重放；不把空字符串作为old_fragment。

```json
[
  {
    "asset": "prototype",
    "line": 258,
    "id": "N05",
    "old_fragment": ".p-metric .v{font-size:22px; font-weight:750; color:var(--brand-d); line-height:1.15; font-variant-numeric:tabular-nums;}",
    "new_fragment": ".p-metric .v{font-size:22px; font-weight:750; color:var(--ink); line-height:1.15; font-variant-numeric:tabular-nums;}"
  },
  {
    "asset": "prototype",
    "line": 1844,
    "id": "S02",
    "old_fragment": "                  <button class=\"p-btn\">作为模板保存</button>",
    "new_fragment": "                  <!-- S02 阶段一移除：独立训练模板入口（需求未定义该资产；保留已批准的配方版本化与训练MAT导出） -->"
  },
  {
    "asset": "prototype",
    "line": 2310,
    "id": "S03",
    "old_fragment": "                  <button class=\"p-btn\">导出会话</button>",
    "new_fragment": "                  <!-- S03 阶段一移除：会话导出入口（需求未定义该功能；保留 FR-L10 审计导出） -->"
  },
  {
    "asset": "release-notes",
    "line": 14,
    "new_line": 15,
    "id": "release-notes",
    "old_fragment": "- MAT生成失败保留已确认版本，提示失败原因，可在service层重建。覆写版本立即失效旧MAT，避免导出已被替换的标签；成功后重新生成。",
    "new_fragment": "- MAT生成失败保留已确认版本，提示失败原因，可在service层重建。覆写版本立即失效旧MAT，避免导出已被替换的标签；成功后重新生成。\n- 新「LLM 设置」屏可配置提供商、base_url、模型与 API key；key 以密码框输入并经 has_key 状态确认，仅存于 sidecar 内存，重启后需重新输入。"
  }
]
```

## 片段四项检查

| 检查项 | 结果 |
|---|---|
| 条目数 | 4：原型3条、release-notes1条 |
| 去重行数 | 4个文件+原行锚点；原型258/1844/2310，release-notes原L14 |
| 与diff行集合比对 | 原型仅替换{258,1844,2310}；release-notes仅在原L14后插入新L15；与4条记录归一化操作集合完全一致。原L14本身未改写 |
| old_fragment恰现一次 | 4/4在各自修改前文件全文恰现一次，亦在其定位原行恰现一次 |

正向重放与当前落盘逐字节一致；逆向重放恢复修改前两个文件字节和哈希。

## Fixture一致性核对

无新增或改动示例数值、fixture、ID、路径、阈值、算法和参数。沿用既有ui-self-consistency-v1 / ann-ui-fixture-v1。批1全部49行、批2全部16行逐行保持；全部input原始标签及属性不变，script块逐字节一致。无算术改动。

## 锚点全量对照

全部29个ID的prototype_lines前后一致；原型2976→2976行、LF数2976→2976，行位移0。仅S02/S03/N05的授权锚点行内容改变；F05锚定的L1946指标卡HTML保持原样。

| ID | 修改前prototype_lines | 修改后prototype_lines | 逐项核对 |
|---|---|---|---|
| F01 | 1484 | 1484 | 行号及锚点行内容均不变 |
| F02 | 1678/1714/1715/1716/1717/1718/1721 | 1678/1714/1715/1716/1717/1718/1721 | 行号及锚点行内容均不变 |
| F03 | 1802/1810/1821/1830 | 1802/1810/1821/1830 | 行号及锚点行内容均不变 |
| F04 | 1948/1955/1978/1983/2866/2872 | 1948/1955/1978/1983/2866/2872 | 行号及锚点行内容均不变 |
| F05 | 1597/1810/1946/2361 | 1597/1810/1946/2361 | 行号及锚点行内容均不变 |
| F06 | 2338/2339 | 2338/2339 | 行号及锚点行内容均不变 |
| F07 | 2331/2359/2360 | 2331/2359/2360 | 行号及锚点行内容均不变 |
| F08 | 1885 | 1885 | 行号及锚点行内容均不变 |
| S01 | 546/1417 | 546/1417 | 行号及锚点行内容均不变 |
| S02 | 1844 | 1844 | 行号不变；授权同行内容替换（1844） |
| S03 | 2310 | 2310 | 行号不变；授权同行内容替换（2310） |
| N01 | 2294/2531 | 2294/2531 | 行号及锚点行内容均不变 |
| N02 | 163/204/206/2419 | 163/204/206/2419 | 行号及锚点行内容均不变 |
| N03 | 1244/2423/2427/2940 | 1244/2423/2427/2940 | 行号及锚点行内容均不变 |
| N04 | 1470/1478/1479 | 1470/1478/1479 | 行号及锚点行内容均不变 |
| N05 | 894/258/1946 | 894/258/1946 | 行号不变；授权同行内容替换（258） |
| N06 | 1642/1647 | 1642/1647 | 行号及锚点行内容均不变 |
| D01 | 1458/1524/1168 | 1458/1524/1168 | 行号及锚点行内容均不变 |
| D02 | 843/2169 | 843/2169 | 行号及锚点行内容均不变 |
| D03 | 1597/1608/1815 | 1597/1608/1815 | 行号及锚点行内容均不变 |
| D04 | 1384/1386/1428/1435/2290/2291 | 1384/1386/1428/1435/2290/2291 | 行号及锚点行内容均不变 |
| D05 | 2249/2269 | 2249/2269 | 行号及锚点行内容均不变 |
| D06 | 771/2169/1923/1925/1926 | 771/2169/1923/1925/1926 | 行号及锚点行内容均不变 |
| D07 | 1661/1726/1730/2361 | 1661/1726/1730/2361 | 行号及锚点行内容均不变 |
| D08 | 1732/1862 | 1732/1862 | 行号及锚点行内容均不变 |
| D09 | 1428/1461/1854 | 1428/1461/1854 | 行号及锚点行内容均不变 |
| D10 | 2217/2254 | 2217/2254 | 行号及锚点行内容均不变 |
| D11 | 766/770/772 | 766/770/772 | 行号及锚点行内容均不变 |
| D12 | 2533 | 2533 | 行号及锚点行内容均不变 |

## 结构自检与SHA256

| 项目 | 修改前 | 修改后 |
|---|---|---|
| 错配结束标签 | 0 | 0 |
| 未闭合标签 | 0 | 0 |
| tr | 160 | 160 |
| div | 532 | 532 |
| p | 48 | 48 |
| button | 86 | 84 |
| 物理行数 / LF数 | 2976 / 2976 | 2976 / 2976 |

- 原型HTML：`11b6c2839bed04866e9b32cf5829ef45e8042ab440649594aa21a728f8b8889a` → `a3eaf01a1dde04225c68760fedfe927d144d095f15d53984dd7061bc5aa737f3`。
- 需求HTML：`08408b0bd5dea317b4e17f365cde7b829804faf15defe96c1b8bf58ca1e29ead` → `08408b0bd5dea317b4e17f365cde7b829804faf15defe96c1b8bf58ca1e29ead`。
- release-notes：`ed1c13ba2508a3acdcd6cae48662c1b0f38ce231d01f2a9628eeff8e1b1ec191` → `5fc0b089cc082337594af792d5dc2748fe0d106d5e1ada97ec463462b41de8bf`。
- status-matrix：`c3d938581612ea3745302706c9a57634631ab98b71a131fbccb8a7156482acab` → `6cad3f7b95928c02b6e58c05acd08c65e7a38a0fac01238b1ad377630a53b1a3`。

## 需要科祥确认或范围限制

- 本批三项均仅登记“原型自身约束满足”，不写需求全文通过，不推定业务实现状态。
- 其他26个ID逐对象不变，全部根元数据、既有updates及29组prototype_lines不变；仅N05/S02/S03各追加一条updates。
- 无执行中歧义或行号/原文偏差；未扩展修改.kpi .v、.tag、h3等主色用法。
- 需求、历史版、业务代码、测试、配置、TASK及milestone证据不改；无build、项目测试、打包、tag或push。

## 最终落盘核验

原型外部落盘完成并与四条片段正向/逆向重放匹配。release-notes除单行插入外与HEAD逐字节一致。HTML结构零错配、零未闭合；保留tr/div/p计数；按钮仅减少授权的2个。提交前Git范围及受保护文件最终复核结果在本节追加；commit ID在交付回报中提供。

最终静态复核通过：

```json
{
  "protected_files_byte_identical": 4318,
  "protected_aggregate_sha256": "f91f9dc1a239ac3176b898642ef17aa95f30613681076da646d44bd49b65f265",
  "original_five_untracked_identical": true,
  "fragment_four_checks": true,
  "forward_reverse_replay": true,
  "matrix_only_three_updates": true,
  "other_26_rows_and_root_metadata_unchanged": true,
  "all_29_anchors_unchanged": true,
  "prototype_lf_count": 2976
}
```

- 实际执行Git附带wc.exe -l，输出：2976 E:/中达瑞和公司/光谱数据AI-Agent处理平台_第一阶段UI设计与高保真原型.html。
- 受保护4318件已跟踪文件的路径/字节哈希聚合复算一致；五个原有未跟踪公司文档集合及字节哈希一致。仅status-matrix、release-notes有已跟踪差分，新日志精确路径force-add。
- git diff --check通过；release-notes diff仅1行新增；status-matrix diff仅三条updates，去掉追加字段后与起始HEAD的完整JSON对象一致。
- 提交集合固定为本日志、status-matrix.json、docs/release-notes-v0.3.0.md。公司目录原型不入Git；原有五个公司文档保持未跟踪。完成本提交后停手等待独立复核。
