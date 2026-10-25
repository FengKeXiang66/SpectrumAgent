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


## 批3第二波：Δ01 run_id单层化与D12写保护措辞回写

授权：用户本波六处精确同行替换指令；第0步已由用户独立复核四连哈希及行数后明确批准进入编辑。起始HEAD：90cf795859f1dca3074a15228acbdf152e29109c。本节仅追加，前述第一波日志全部原字节保留。

### 备份核验与第0步结果

- HEAD=90cf795；工作区仅原有5个未跟踪公司文档，无其他差异。
- 两份before快照在第0步创建，编辑前与对应current逐字节相同，未覆盖或修改快照。指定六处原文及行号全部吻合，无偏差。
- 第一波L258为var(--ink)、L1844/L2310为指定S02/S03注释；批1的53条片段/49行重放匹配批2备份，批2的16行与第一波三处顺序重放匹配本波原型快照。

| 第0步文件 | 行数 / LF数 | SHA256 |
|---|---|---|
| 需求 before快照 | 3211 / 3211 | 08408b0bd5dea317b4e17f365cde7b829804faf15defe96c1b8bf58ca1e29ead |
| 需求 current（编辑前） | 3211 / 3211 | 08408b0bd5dea317b4e17f365cde7b829804faf15defe96c1b8bf58ca1e29ead |
| 原型 before快照 | 2976 / 2976 | a3eaf01a1dde04225c68760fedfe927d144d095f15d53984dd7061bc5aa737f3 |
| 原型 current（编辑前） | 2976 / 2976 | a3eaf01a1dde04225c68760fedfe927d144d095f15d53984dd7061bc5aa737f3 |

快照路径：.runtime/review-20261025-baseline/batch3-wave2-before-需求.html；batch3-wave2-before-原型.html。两份快照不入提交，供独立复核。

### 六处old→new

| ID | 文件/行 | old→new |
|---|---|---|
| Δ01 | 需求L524 | `&lt;run_id&gt;/&lt;run_id&gt;/` → `&lt;run_id&gt;/`，其余字节不动 |
| Δ01 | 需求L566 | `&lt;run_id&gt;/&lt;run_id&gt;/` → `&lt;run_id&gt;/`，其余字节不动 |
| Δ01 | 需求L3131 | `&lt;run_id&gt;/&lt;run_id&gt;/` → `&lt;run_id&gt;/`，其余字节不动 |
| Δ01 | 需求L3196 | `&lt;run_id&gt;/&lt;run_id&gt;/` → `&lt;run_id&gt;/`，其余字节不动 |
| D12 | 需求L3064 | “不存在任何写向源目录的记录（FR-A12验收项）” → “不存在任何成功写向源目录的记录；被拒写入尝试均完整留痕（DENY记录与告警，FR-A11验收项）”；准确HTML见下方完整片段 |
| D12 | 原型L2533 | “且审计日志中不存在任何写向源目录的记录” → “且审计日志中不存在任何成功写向源目录的记录，被拒写入尝试均完整留痕” |

### 可重放片段

每条记录对应一个完整原行，不含原行结束符；按asset/line定位，old_fragment在对应修改前文件全文与该原行均恰现一次。同行替换保留原行结束符。

```json
[
  {
    "asset": "requirements",
    "line": 524,
    "id": "Δ01",
    "old_fragment": "        <tr style=\"background:#fbfdfb;\"><td class=\"mono\">FR-A12</td><td><strong>产物输出到 NAS 指定目录</strong><br><span class=\"tag n\">v2.6</span></td><td>处理与分析产物（中间立方体、模型、图、报告）写入 NAS 上<strong>独立于源目录</strong>的输出根，按 <code>&lt;输出根&gt;/&lt;项目&gt;/&lt;dataset_version&gt;/&lt;run_id&gt;/&lt;run_id&gt;/</code> 组织，便于其他工具直接读取并纳入既有备份策略；输出根可配置，不存在时自动创建（创建动作需记录）。<strong>产物目录不得建在源目录内部</strong>——在源目录下新建子目录同样属于\"改动了原数据\"。验收：① 一次完整分析的产物可在输出根下按上述层级查到；② <strong>源目录树结构与文件清单在分析前后完全一致（含无新增子目录）</strong>；③ 产物目录内含 manifest，记录本次 run 的输入版本与参数</td><td class=\"c\"><span class=\"chip c-p0\">P0</span></td></tr>",
    "new_fragment": "        <tr style=\"background:#fbfdfb;\"><td class=\"mono\">FR-A12</td><td><strong>产物输出到 NAS 指定目录</strong><br><span class=\"tag n\">v2.6</span></td><td>处理与分析产物（中间立方体、模型、图、报告）写入 NAS 上<strong>独立于源目录</strong>的输出根，按 <code>&lt;输出根&gt;/&lt;项目&gt;/&lt;dataset_version&gt;/&lt;run_id&gt;/</code> 组织，便于其他工具直接读取并纳入既有备份策略；输出根可配置，不存在时自动创建（创建动作需记录）。<strong>产物目录不得建在源目录内部</strong>——在源目录下新建子目录同样属于\"改动了原数据\"。验收：① 一次完整分析的产物可在输出根下按上述层级查到；② <strong>源目录树结构与文件清单在分析前后完全一致（含无新增子目录）</strong>；③ 产物目录内含 manifest，记录本次 run 的输入版本与参数</td><td class=\"c\"><span class=\"chip c-p0\">P0</span></td></tr>"
  },
  {
    "asset": "requirements",
    "line": 566,
    "id": "Δ01",
    "old_fragment": "      <text x=\"829\" y=\"92\" text-anchor=\"middle\" font-size=\"10.4\" font-family=\"'SF Mono',Menlo,monospace\" fill=\"#29414c\">&lt;输出根&gt;/&lt;项目&gt;/&lt;dataset_version&gt;/&lt;run_id&gt;/&lt;run_id&gt;/</text>",
    "new_fragment": "      <text x=\"829\" y=\"92\" text-anchor=\"middle\" font-size=\"10.4\" font-family=\"'SF Mono',Menlo,monospace\" fill=\"#29414c\">&lt;输出根&gt;/&lt;项目&gt;/&lt;dataset_version&gt;/&lt;run_id&gt;/</text>"
  },
  {
    "asset": "requirements",
    "line": 3064,
    "id": "D12",
    "old_fragment": "        <tr><td>产物落盘合规率</td><td class=\"c\">100%</td><td>抽查历史 run：产物路径全部位于输出根白名单内、目录内含 manifest；审计日志中<strong>不存在任何写向源目录的记录</strong>（FR-A12 验收项）</td></tr>",
    "new_fragment": "        <tr><td>产物落盘合规率</td><td class=\"c\">100%</td><td>抽查历史 run：产物路径全部位于输出根白名单内、目录内含 manifest；审计日志中<strong>不存在任何成功写向源目录的记录</strong>；被拒写入尝试均完整留痕（DENY 记录与告警，FR-A11 验收项）</td></tr>"
  },
  {
    "asset": "requirements",
    "line": 3131,
    "id": "Δ01",
    "old_fragment": "        <tr><td class=\"mono\">输出根<br><span class=\"tag n\">v2.6</span></td><td>NAS 上<strong>独立于源目录</strong>的产物目录，按 <code>&lt;输出根&gt;/&lt;项目&gt;/&lt;dataset_version&gt;/&lt;run_id&gt;/&lt;run_id&gt;/</code> 组织。三条要点：① 只在输出根内写入；② <strong>绝不在源目录内新建子目录</strong>（那同样算改动原数据）；③ 产物目录内含 manifest，记录输入版本与参数（见 FR-A12）</td></tr>",
    "new_fragment": "        <tr><td class=\"mono\">输出根<br><span class=\"tag n\">v2.6</span></td><td>NAS 上<strong>独立于源目录</strong>的产物目录，按 <code>&lt;输出根&gt;/&lt;项目&gt;/&lt;dataset_version&gt;/&lt;run_id&gt;/</code> 组织。三条要点：① 只在输出根内写入；② <strong>绝不在源目录内新建子目录</strong>（那同样算改动原数据）；③ 产物目录内含 manifest，记录输入版本与参数（见 FR-A12）</td></tr>"
  },
  {
    "asset": "requirements",
    "line": 3196,
    "id": "Δ01",
    "old_fragment": "    v2.6 变更：<strong>新增\"数据来源与写保护\"要求——A 域扩 4 条（FR-A10~A13）</strong>。① <strong>数据集可直接从 NAS 共享目录中选择</strong>（SMB/CIFS、NFS，可扩展 S3 兼容网关），不必先用文件管理器手工拷到本机；② <strong>处理过程绝不修改原数据</strong>——只读挂载（<code>ro</code>）与应用层写白名单<strong>两层同时生效</strong>，明确禁止原地改写、<strong>在源目录内新建子目录</strong>、重命名与删除；③ <strong>产物写入 NAS 上独立于源目录的新建输出根</strong>，按 <code>&lt;输出根&gt;/&lt;项目&gt;/&lt;dataset_version&gt;/&lt;run_id&gt;/&lt;run_id&gt;/</code> 组织并附 manifest；④ 新增连接健壮性与凭据安全：NAS 不可达时 <strong>fail-closed</strong>（拒算而非回落到本地缓存），凭据加密存储，<strong>NAS 路径与文件名不得进入 LLM 上下文</strong>。⑤ 连带更新：1.1 痛点表、场景 S1 第 1 步、3.1 A 域（新增图 3-1）、5.2 数据流转图与图注、5.4 技术选型、6.7 存储分工、风险清单 <strong>R16</strong>、8 章阶段一交付物与验收、8.2 开发顺序①、9 章新增\"数据治理\"指标组、10.1 术语表、10.4 新增 <strong>Q12</strong>。⑥ <strong>需求条目 128 → 132 条（P0 83 / P1 40 / P2 9），阶段一交付 96 → 100 条。</strong>⑦ <strong>开放问题 Q12 已关闭</strong>（2026-10-14：共享侧可提供只读账号 → 两层只读成立），并已同步进工程交付规格包 stage5 <strong>v1.1</strong>：DDL 新增 <code>data_source</code> 表与 <code>dataset_version.data_source_id</code>、OpenAPI 新增数据源端点与 <code>write_guard</code>、贯穿字段由五扩为六、禁止清单由十条扩为十一条、新增 CI 作业 <code>test-source-readonly</code>。<br>",
    "new_fragment": "    v2.6 变更：<strong>新增\"数据来源与写保护\"要求——A 域扩 4 条（FR-A10~A13）</strong>。① <strong>数据集可直接从 NAS 共享目录中选择</strong>（SMB/CIFS、NFS，可扩展 S3 兼容网关），不必先用文件管理器手工拷到本机；② <strong>处理过程绝不修改原数据</strong>——只读挂载（<code>ro</code>）与应用层写白名单<strong>两层同时生效</strong>，明确禁止原地改写、<strong>在源目录内新建子目录</strong>、重命名与删除；③ <strong>产物写入 NAS 上独立于源目录的新建输出根</strong>，按 <code>&lt;输出根&gt;/&lt;项目&gt;/&lt;dataset_version&gt;/&lt;run_id&gt;/</code> 组织并附 manifest；④ 新增连接健壮性与凭据安全：NAS 不可达时 <strong>fail-closed</strong>（拒算而非回落到本地缓存），凭据加密存储，<strong>NAS 路径与文件名不得进入 LLM 上下文</strong>。⑤ 连带更新：1.1 痛点表、场景 S1 第 1 步、3.1 A 域（新增图 3-1）、5.2 数据流转图与图注、5.4 技术选型、6.7 存储分工、风险清单 <strong>R16</strong>、8 章阶段一交付物与验收、8.2 开发顺序①、9 章新增\"数据治理\"指标组、10.1 术语表、10.4 新增 <strong>Q12</strong>。⑥ <strong>需求条目 128 → 132 条（P0 83 / P1 40 / P2 9），阶段一交付 96 → 100 条。</strong>⑦ <strong>开放问题 Q12 已关闭</strong>（2026-10-14：共享侧可提供只读账号 → 两层只读成立），并已同步进工程交付规格包 stage5 <strong>v1.1</strong>：DDL 新增 <code>data_source</code> 表与 <code>dataset_version.data_source_id</code>、OpenAPI 新增数据源端点与 <code>write_guard</code>、贯穿字段由五扩为六、禁止清单由十条扩为十一条、新增 CI 作业 <code>test-source-readonly</code>。<br>"
  },
  {
    "asset": "prototype",
    "line": 2533,
    "id": "D12",
    "old_fragment": "        <tr><td class=\"c mono\">13</td><td><strong>源数据零改动</strong> <span class=\"p-badge b-mute\">v2.2</span></td><td>导入页明确显示数据源为<b>只读</b>与产物输出根；处理前后对源目录做文件清单与哈希比对须完全一致（<b>无新增子目录 / 无重命名 / 无删除</b>），且审计日志中不存在任何写向源目录的记录</td></tr>",
    "new_fragment": "        <tr><td class=\"c mono\">13</td><td><strong>源数据零改动</strong> <span class=\"p-badge b-mute\">v2.2</span></td><td>导入页明确显示数据源为<b>只读</b>与产物输出根；处理前后对源目录做文件清单与哈希比对须完全一致（<b>无新增子目录 / 无重命名 / 无删除</b>），且审计日志中不存在任何成功写向源目录的记录，被拒写入尝试均完整留痕</td></tr>"
  }
]
```

### 片段四项检查

| 检查项 | 结果 |
|---|---|
| 条目数 | 6：需求5条、原型1条 |
| 去重行数 | 6个asset+line，无重复 |
| 与diff行集合比对 | 需求{524,566,3064,3131,3196}，原型{2533}，与6条片段完全一致，无新增/删行 |
| old_fragment恰现一次 | 6/6在对应before全文及定位原行恰现一次 |

正向重放：两份before分别应用片段后与current逐字节相同；逆向重放：current反向替换后与两份before逐字节相同，哈希恢复。Δ01双层子串修改前全文4次、每指定行1次；修改后全文0次。

### 锚点全量对照

29个ID的prototype_lines完整保留；仅D12的L2533为授权内容替换，行号不动。Δ01作为29行外差异登记，不新增问题行；Δ02亦非29行内ID，本波未修。

| ID | 修改前prototype_lines | 修改后prototype_lines | 核对结果 |
|---|---|---|---|
| F01 | 1484 | 1484 | 行号及全部锚点行内容不变 |
| F02 | 1678/1714/1715/1716/1717/1718/1721 | 1678/1714/1715/1716/1717/1718/1721 | 行号及全部锚点行内容不变 |
| F03 | 1802/1810/1821/1830 | 1802/1810/1821/1830 | 行号及全部锚点行内容不变 |
| F04 | 1948/1955/1978/1983/2866/2872 | 1948/1955/1978/1983/2866/2872 | 行号及全部锚点行内容不变 |
| F05 | 1597/1810/1946/2361 | 1597/1810/1946/2361 | 行号及全部锚点行内容不变 |
| F06 | 2338/2339 | 2338/2339 | 行号及全部锚点行内容不变 |
| F07 | 2331/2359/2360 | 2331/2359/2360 | 行号及全部锚点行内容不变 |
| F08 | 1885 | 1885 | 行号及全部锚点行内容不变 |
| S01 | 546/1417 | 546/1417 | 行号及全部锚点行内容不变 |
| S02 | 1844 | 1844 | 行号及全部锚点行内容不变 |
| S03 | 2310 | 2310 | 行号及全部锚点行内容不变 |
| N01 | 2294/2531 | 2294/2531 | 行号及全部锚点行内容不变 |
| N02 | 163/204/206/2419 | 163/204/206/2419 | 行号及全部锚点行内容不变 |
| N03 | 1244/2423/2427/2940 | 1244/2423/2427/2940 | 行号及全部锚点行内容不变 |
| N04 | 1470/1478/1479 | 1470/1478/1479 | 行号及全部锚点行内容不变 |
| N05 | 894/258/1946 | 894/258/1946 | 行号及全部锚点行内容不变 |
| N06 | 1642/1647 | 1642/1647 | 行号及全部锚点行内容不变 |
| D01 | 1458/1524/1168 | 1458/1524/1168 | 行号及全部锚点行内容不变 |
| D02 | 843/2169 | 843/2169 | 行号及全部锚点行内容不变 |
| D03 | 1597/1608/1815 | 1597/1608/1815 | 行号及全部锚点行内容不变 |
| D04 | 1384/1386/1428/1435/2290/2291 | 1384/1386/1428/1435/2290/2291 | 行号及全部锚点行内容不变 |
| D05 | 2249/2269 | 2249/2269 | 行号及全部锚点行内容不变 |
| D06 | 771/2169/1923/1925/1926 | 771/2169/1923/1925/1926 | 行号及全部锚点行内容不变 |
| D07 | 1661/1726/1730/2361 | 1661/1726/1730/2361 | 行号及全部锚点行内容不变 |
| D08 | 1732/1862 | 1732/1862 | 行号及全部锚点行内容不变 |
| D09 | 1428/1461/1854 | 1428/1461/1854 | 行号及全部锚点行内容不变 |
| D10 | 2217/2254 | 2217/2254 | 行号及全部锚点行内容不变 |
| D11 | 766/770/772 | 766/770/772 | 行号及全部锚点行内容不变 |
| D12 | 2533 | 2533 | 行号不变；L2533授权同行措辞替换 |

### 双文件行数与SHA256

| 文件 | 修改前行数 / LF数 | 修改后行数 / LF数 | 行位移 |
|---|---|---|---|
| 需求HTML | 3211 / 3211 | 3211 / 3211 | 0 |
| 原型HTML | 2976 / 2976 | 2976 / 2976 | 0 |

- 需求HTML：`08408b0bd5dea317b4e17f365cde7b829804faf15defe96c1b8bf58ca1e29ead` → `c7b1b1ad0c302f180c9e19440ef6c4fbd1c09027bf66cd84f3065b1b499929a0`。
- 原型HTML：`a3eaf01a1dde04225c68760fedfe927d144d095f15d53984dd7061bc5aa737f3` → `b9a16e021f0265be6237f6012d940bd5765e74c37f796badebd2332ca780080b`。
- 两份before快照哈希保持第0步值不变。需求L523/3019/3194与原型L546/1438逐行保持；其余未授权行全部由完整差分集合排除验证。

### 结构自检与既有成果保留

```json
{
  "requirements": {
    "mismatched_before": 0,
    "mismatched_after": 0,
    "unclosed_before": 0,
    "unclosed_after": 0,
    "tag_counts_unchanged": true,
    "tr_div_p": {
      "tr": 641,
      "div": 174,
      "p": 68
    }
  },
  "prototype": {
    "mismatched_before": 0,
    "mismatched_after": 0,
    "unclosed_before": 0,
    "unclosed_after": 0,
    "tag_counts_unchanged": true,
    "tr_div_p": {
      "tr": 160,
      "div": 532,
      "p": 48
    }
  }
}
```

- 两份HTML全部标签计数、结构状态前后一致。本波只改既有文本与路径编码子串，不改控件、CSS、JS或数值。
- 批1全部49行、批2全部16行以及第一波L258/L1844/L2310逐行保持；第一波日志前缀与本波追加前逐字节相同。

### 状态登记与范围限制

- D12仅追加batch3-wave2的updates，状态为“覆盖某条需求的一部分”；拒写构造留痕验证归冒烟，不写需求全文通过。文件写保护审计与llm_call审计不互相代证。
- batch_updates仅追加本波条目，登记Δ01回写四处；注明Δ01/Δ02非29行内ID，Δ02保持现状。去掉上述两条追加记录后，完整JSON对象与起始HEAD一致。
- 其余28行、全部既有updates、根元数据、requirement_lines/prototype_lines不变。不改代码/测试/配置/TASK、其他evidence、历史版或release-notes，不运行项目测试/构建，不tag、不push。

### 正逆重放与最终落盘核验

六条片段正向重放与current字节一致，逆向重放精确恢复before。提交前将追加实际wc -l双验、受保护文件及Git提交范围复核结果。公司目录HTML和两份before快照不入Git，提交固定为batch3-changelog.md与status-matrix.json。

本波最终静态复核结果：

```json
{
  "protected_files_byte_identical": 4319,
  "protected_aggregate_sha256": "0be71ee7f931cbdf224a1ea9245c7dacf7fdb7ce2fee7c403a16ef24271aab44",
  "original_five_untracked_identical": true,
  "snapshots_unchanged": true,
  "first_wave_log_prefix_unchanged": true,
  "matrix_only_D12_update_and_one_batch_update": true,
  "other_28_rows_unchanged": true,
  "all_29_anchors_unchanged": true,
  "fragment_entries": 6,
  "unique_fragment_lines": 6,
  "fragment_diff_set_equal": true,
  "old_fragment_once_in_full_before_and_line": true,
  "forward_reverse_replay_byte_identical": true,
  "requirement_line_count": 3211,
  "prototype_line_count": 2976,
  "requirements_diff_lines": [
    524,
    566,
    3064,
    3131,
    3196
  ],
  "prototype_diff_lines": [
    2533
  ]
}
```

实际wc -l双验：

```text
3211 E:/中达瑞和公司/光谱数据AI-Agent处理平台_需求分析与设计.html
2976 E:/中达瑞和公司/光谱数据AI-Agent处理平台_第一阶段UI设计与高保真原型.html
```

- 两份before快照再次复算SHA256，与第0步值逐一一致。
- 受保护4319件已跟踪文件路径/字节哈希聚合一致，含代码、测试、配置、TASK、milestone证据及release-notes；五个原有未跟踪公司文档集合及字节一致。
- git diff --check通过；提交前仅batch3-changelog.md与status-matrix.json有差分。前述第一波日志整个前缀字节保持，未重写已有章节。
- 按精确路径逐文件force-add，仅提交上述两件登记工件；提交ID在回报中提供。公司目录两份HTML及两份快照不入Git。不tag、不push，提交后停手等待独立复核。
