# 第二批原型说明修复变更日志

授权：用户第二批六项范围提示词、第0步通过后的开始编辑指令、F05引用处理的追加确认。起始HEAD：d0d7900；原型标题保持ui-v2.3。

## 第0步结果

- Git HEAD=d0d7900；核验前后仅原有5个未跟踪公司文档，无其他M或??；本批无证据恢复动作。
- 指定备份batch2-original.html已在第0步创建，旧原型与备份逐字节一致，SHA256均为`78de8b003efa53e80b5231df27b2ed1d407e7bd2faaa9cd83106698d13fb1a8f`，2976行。备份不覆盖、不修改。
- 需求v2.7复算为`08408b0bd5dea317b4e17f365cde7b829804faf15defe96c1b8bf58ca1e29ead`，与授权基线一致，未编辑。
- 批1日志53条替换片段覆盖49行；由批1原件正向重放与反向验证全部通过。

```text
?? SpecMetis_vs_SpectrumAgent_架构对比_20261022.md
?? 光谱Agent_D域编排_讨论交接摘要_20261022.md
?? 光谱平台_阶段一_代码审查与进度分析_20261018.md
?? 光谱平台_阶段一_需求符合度与质量评估_20261022.md
?? 光谱数据AI-Agent处理平台_阶段一技术选型_定稿v1.1_1792327262075_csvb.md
```

## 修改清单

仅F01/F05/F07/N03/D04/D09；其余23个ID及Δ01/Δ02不作修改。只改公司目录当前原型和两件登记工件；不修改需求、历史版、TASK、业务代码、外壳CSS/JS、release-notes或milestone证据。无build、项目测试、打包、发布或push。

## 每项old→new

| ID | old→new | 结论与限制 |
|---|---|---|
| F01 | 插值修复选中 → 剔除选中；控件附近补“阶段二/不适用，尚未交付”及FR-A05默认说明 | 覆盖某条需求的一部分；不宣称检测/掩膜交付；联动补偿卡仅登记待办 |
| F05 | ROI“此数值来自算子” → 无已绑定metric_id/run_id、出处待绑定、非真实结果凭据；OA后补既有metrics.oa · v1.3 · run_…0412示例引用 | 按用户追加确认执行；无前端造ID。原型OA引用已补，ROI明确待绑定；metric_id形式化随指标台账，不全文销账 |
| F07 | 参数无来源 → 用户指定与场景示例默认值可改分别标注；补FR-D01应先追问的行为要求 | 当前缺必填参数调用拒绝，拒绝后统一追问待后续D域；不宣称已实现结构化澄清 |
| N03 | 输入/发送无状态及目标说明 → 输入标签外补成功/失败/禁用、就地发送与展开S01说明，助手页也补静态说明；发送按钮仅新增title | 原型自身约束满足；不接服务、不改JS、不实际启用新交互；输入原始标签及属性逐字一致 |
| D04 | share级“只读”含糊 → 来源批次目录只读；输出根为§8.1可写根，与批次源同级且不在任何来源批次子树内 | 仅说明层部分覆盖；路径值不改，NAS挂载、守卫及审计不裁定，不新增里程碑声明 |
| D09 | 路径/转换/回归缺分支说明 → 拒绝/补凭据后重试、缺白板暗电流禁用及补输入、缺连续真值拒绝及标签来源补真值路径 | 仅静态分支设计；NAS需实机验证，未交付回归随PLS验收；不改控件行为、位置或属性 |

说明定位：用户所称ROI注记“L1598”在当前原型实际为L1600，按明确的文本内容锚定修改L1600；L1597数值行和L1598结构行均不改。导入屏已正确的挂载/分离说明实际为L1432/L1438（用户称L1430/L1437）；这些正确行全部保持。

## 可重放片段

一条记录对应一个完整原行（不含末尾LF），按line定位。old_fragment必须在该原行恰现一次，替换后保留该行末尾LF。公司目录原型不入Git，此处完整存档外部修改。

```json
[
  {
    "line": 1484,
    "ids": [
      "F01"
    ],
    "old_fragment": "                        <div class=\"p-seg\"><button>剔除</button><button class=\"on\">插值修复</button><button>保留并标记</button></div>",
    "new_fragment": "                        <div class=\"p-seg\"><button class=\"on\">剔除</button><button>插值修复</button><button>保留并标记</button></div>"
  },
  {
    "line": 1487,
    "ids": [
      "F01"
    ],
    "old_fragment": "                      </div>",
    "new_fragment": "                      </div><small style=\"display:block; margin-top:8px; color:var(--ink3);\">坏波段剔除：<b>阶段二 / 不适用，尚未交付</b>。默认处置按 FR-A05 对齐为剔除；不表示检测或掩膜能力已交付。</small>"
  },
  {
    "line": 1384,
    "ids": [
      "D04"
    ],
    "old_fragment": "                        <li><span class=\"k\">NAS 数据源</span><span class=\"v mono\">nas-01/spectral <b style=\"color:var(--ok);\">只读</b></span></li>",
    "new_fragment": "                        <li><span class=\"k\">NAS 数据源</span><span class=\"v mono\">nas-01/spectral <b style=\"color:var(--ok);\">来源批次只读</b><small style=\"display:block; margin-top:4px; color:var(--ink3);\">只读作用于共享根下的来源批次目录（如 2026-plastic-batch3）。</small></span></li>"
  },
  {
    "line": 1386,
    "ids": [
      "D04"
    ],
    "old_fragment": "                        <li><span class=\"k\">产物输出根</span><span class=\"v mono\">nas-01/spectral/_agent_out</span></li>",
    "new_fragment": "                        <li><span class=\"k\">产物输出根</span><span class=\"v mono\">nas-01/spectral/_agent_out<small style=\"display:block; margin-top:4px; color:var(--ink3);\">§8.1：该输出根为可写根，与各来源批次目录同级，不在任何来源批次目录之内；源目录与输出根物理分离。</small></span></li>"
  },
  {
    "line": 2290,
    "ids": [
      "D04"
    ],
    "old_fragment": "                      <li><span class=\"k\">NAS 数据源</span><span class=\"v mono\">nas-01/spectral <b style=\"color:var(--ok);\">只读</b> · 凭据加密存储</span></li>",
    "new_fragment": "                      <li><span class=\"k\">NAS 数据源</span><span class=\"v mono\">nas-01/spectral <b style=\"color:var(--ok);\">来源批次只读</b> · 凭据加密存储<small style=\"display:block; margin-top:4px; color:var(--ink3);\">只读作用于共享根下的来源批次目录（如 2026-plastic-batch3）。</small></span></li>"
  },
  {
    "line": 2291,
    "ids": [
      "D04"
    ],
    "old_fragment": "                      <li><span class=\"k\">产物输出根</span><span class=\"v mono\">nas-01/spectral/_agent_out</span></li>",
    "new_fragment": "                      <li><span class=\"k\">产物输出根</span><span class=\"v mono\">nas-01/spectral/_agent_out<small style=\"display:block; margin-top:4px; color:var(--ink3);\">§8.1：该输出根为可写根，与各来源批次目录同级，不在任何来源批次目录之内；源目录与输出根物理分离。</small></span></li>"
  },
  {
    "line": 1431,
    "ids": [
      "D09"
    ],
    "old_fragment": "                      </div>",
    "new_fragment": "                      </div><small style=\"display:block; margin-bottom:8px; color:var(--ink3);\">连接分支说明（静态）：路径不可达或凭据缺失时拒绝开始，提示检查路径并补齐连接凭据；修正后通过现有“浏览…”重新选择并重试。此处仅说明拒绝与重试状态，NAS 连接分支仍需实机验证。</small>"
  },
  {
    "line": 1461,
    "ids": [
      "D09"
    ],
    "old_fragment": "                          <span class=\"p-cbx\"><i></i>立即做反射率转换（需同时提供白板与暗电流）</span>",
    "new_fragment": "                          <span class=\"p-cbx\"><i></i>立即做反射率转换（需同时提供白板与暗电流）</span><small style=\"display:block; margin-top:4px; color:var(--ink3);\">转换分支说明（静态）：缺少白板或暗电流时应禁用该转换选项，并提示补齐白板与暗电流，补齐后重试；仅说明分支状态，未接真实转换服务。</small>"
  },
  {
    "line": 1855,
    "ids": [
      "D09"
    ],
    "old_fragment": "                      </div>",
    "new_fragment": "                      </div><small style=\"display:block; margin-bottom:8px; color:var(--ink3);\">回归分支说明（静态）：缺少连续量真值时拒绝开始；补输入路径为本页“标签来源”补充按样品关联的含量或浓度真值，再选择 PLS 回归重试。未交付部分随 PLS 里程碑验收。</small>"
  },
  {
    "line": 1600,
    "ids": [
      "F05"
    ],
    "old_fragment": "                      <div class=\"p-note info\" style=\"margin-top:10px; font-size:10.9px;\"><span class=\"ic\">i</span><span>判别指数 0.71 &lt; 0.8 → 提示可能为 <b>PET</b>。此数值来自算子，模型仅做解读。</span></div>",
    "new_fragment": "                      <div class=\"p-note info\" style=\"margin-top:10px; font-size:10.9px;\"><span class=\"ic\">i</span><span>判别指数 0.71 &lt; 0.8 → 提示可能为 <b>PET</b>。本卡为设计示意：ROI 统计与判别指数无已绑定的 metric_id / run_id，出处待绑定，非真实结果凭据；定稿后由算子返回并附双 ID，模型仅做解读。</span></div>"
  },
  {
    "line": 2361,
    "ids": [
      "F05"
    ],
    "old_fragment": "                          <div style=\"font-size:12.2px; margin-top:8px;\">训练中，预计 18 秒。当前 fold 3/5，OA 0.941–0.952。<br>统计按范围分开：S05 ps_032 / ann-ui-fixture-v1 的像素标注率为 <b>88,000/107,520=81.85%</b>（含背景5）；-1留白15,520、-2不确定4,000均排除。超像素确认率504/812=62.07%；自动来源比例0/88,000=0%。S08另用ann-eval-fixture-v1的8图OOF子集782,500像素，不能共用分母。</div>",
    "new_fragment": "                          <div style=\"font-size:12.2px; margin-top:8px;\">训练中，预计 18 秒。当前 fold 3/5，OA 0.941–0.952。<small style=\"color:var(--ink3);\">出处：<code>metrics.oa · v1.3 · run_…0412</code>（原型既有示例引用）</small><br>统计按范围分开：S05 ps_032 / ann-ui-fixture-v1 的像素标注率为 <b>88,000/107,520=81.85%</b>（含背景5）；-1留白15,520、-2不确定4,000均排除。超像素确认率504/812=62.07%；自动来源比例0/88,000=0%。S08另用ann-eval-fixture-v1的8图OOF子集782,500像素，不能共用分母。</div>"
  },
  {
    "line": 2359,
    "ids": [
      "F07"
    ],
    "old_fragment": "                          <div class=\"p-tool\"><span>apply_pipeline</span><span>plastic-snv-sg1 · w15/p2/d1</span><span class=\"st\">✓ 完成</span></div>",
    "new_fragment": "                          <div class=\"p-tool\"><span>apply_pipeline</span><span>plastic-snv-sg1 · w15/p2/d1</span><span class=\"st\">✓ 完成</span></div><small style=\"display:block; margin:5px 0; color:var(--ink3);\">参数来源：SNV + SG 一阶导为用户指定；w15/p2/d1 为场景示例默认值，可改（d1 对应用户指定的一阶导）。</small>"
  },
  {
    "line": 2360,
    "ids": [
      "F07"
    ],
    "old_fragment": "                          <div class=\"p-tool\"><span>train_plsda</span><span>分组 5-fold · iPLS 6 区间</span><span class=\"st\" style=\"color:var(--warn);\">运行中 64%</span></div>",
    "new_fragment": "                          <div class=\"p-tool\"><span>train_plsda</span><span>分组 5-fold · iPLS 6 区间</span><span class=\"st\" style=\"color:var(--warn);\">运行中 64%</span></div><small style=\"display:block; margin:5px 0; color:var(--ink3);\">参数来源：按样品分组交叉验证为用户指定；5-fold、iPLS 6 区间为场景示例默认值，可改。FR-D01 交互要求：必填参数缺失时先追问确认，不静默取默认值执行。当前未补齐必填参数的调用会被拒绝；拒绝后的统一追问仍待后续 D 域补齐。</small>"
  },
  {
    "line": 2423,
    "ids": [
      "N03"
    ],
    "old_fragment": "                <input class=\"p-input\" id=\"pcomposerinput\" placeholder=\"对智能助手说：导入 /data/2026-plastic-batch3，做 SNV + SG 一阶导，再训一个 PLS-DA…\">",
    "new_fragment": "                <input class=\"p-input\" id=\"pcomposerinput\" placeholder=\"对智能助手说：导入 /data/2026-plastic-batch3，做 SNV + SG 一阶导，再训一个 PLS-DA…\"><small style=\"display:block; margin-top:4px; color:var(--ink3);\">状态说明（静态）：空输入或处理中禁用发送；成功就地显示，失败保留输入并提示修正重试。发送留在当前页会话区；“展开助手页”进入 S01 同一会话；未接真实服务。</small>"
  },
  {
    "line": 2427,
    "ids": [
      "N03"
    ],
    "old_fragment": "              <button class=\"p-btn sm pri\">发送</button>",
    "new_fragment": "              <button class=\"p-btn sm pri\" title=\"静态状态说明：成功在当前页显示；失败保留输入可重试；空输入或处理中禁用。\">发送</button>"
  },
  {
    "line": 2377,
    "ids": [
      "N03"
    ],
    "old_fragment": "                    </div>",
    "new_fragment": "                    </div><small style=\"display:block; margin-top:6px; color:var(--ink3);\">发送状态说明（静态）：留在 S01 当前会话；成功显示工具轨迹与结果，失败保留输入并提示修正重试；空输入或处理中禁用发送。此处仅补状态与目标页面说明，未接真实服务。</small>"
  }
]
```

### 片段节四项检查

| 检查 | 结果 |
|---|---|
| 条目数 | 16 |
| 去重行数 | 16（每行一条原子替换） |
| 与diff行集合比对 | 完全一致：1384, 1386, 1431, 1461, 1484, 1487, 1600, 1855, 2290, 2291, 2359, 2360, 2361, 2377, 2423, 2427 |
| old_fragment恰现一次 | 16/16；逐条按其原始行核验，不以全文件模糊匹配替代 |

全部片段正向重放精确得到候选字节；最终源文件也须与候选逐字节相同。输入框相关片段L2423中，新增small说明在完整input结束符>之后，不写进placeholder/value属性。

## Fixture一致性核对

- 沿用批1ui-self-consistency-v1、ann-ui-fixture-v1与ann-eval-fixture-v1；本批不建新fixture、不改其任何计数/矩阵/参数值。
- 导入报告L1469–1470、候选行L1714–1718、CM_ROWS、Kappa卡L1947、用户消息L2331、正确NAS说明L1432/L1438逐字节保持。
- 批1共49行中，48个非交集行原字节保持；唯一交集L2361只在OA后插入既有引用，其首个br后的全部批1统计文字逐字保持。
- L1594–1599表格数值与结构不动；0.71/0.8及1724nm原冲突保持，ROI注记只撤回含糊出处声明，不对波长真实性下结论。
- 无新增数值结果、参数默认值或ID格式。F05引用来源为原型L1946已有metrics.oa/v1.3/run_…0412示例；ROI按用户明确要求不用metrics.xxx占位，也不新增metric_id。OA引用不是实测凭据。
- F07数值w15/p2/d1、5-fold、iPLS6区间完全保留；来源标签沿用用户指定与场景示例默认值措辞。d1与用户的一阶导语义一致，同时按授权将其数值展示标为场景示例可改。
- 路径nas-01/spectral、nas-01/spectral/_agent_out与输入框smb路径不变；新增说明中的2026-plastic-batch3为既有批次名，§8.1为既有章节号，不是新参数。
- F01两个未选项文字与ps_032的2坏波段告警不变；仅切换class=on并说明尚未交付。

### 输入框属性核对

全部11个input的原始起始标签逐字一致，HTMLParser解析出的属性键/值及行号也全部一致。重点项：

```json
[
  {
    "line": 1428,
    "attributes": [
      [
        "class",
        "p-input mono"
      ],
      [
        "value",
        "smb://nas-01/spectral/2026-plastic-batch3"
      ],
      [
        "style",
        "font-size:11.8px;"
      ]
    ]
  },
  {
    "line": 1435,
    "attributes": [
      [
        "class",
        "p-input mono"
      ],
      [
        "value",
        "smb://nas-01/spectral/_agent_out"
      ],
      [
        "style",
        "font-size:11.8px;"
      ]
    ]
  },
  {
    "line": 2374,
    "attributes": [
      [
        "class",
        "p-input ph"
      ],
      [
        "placeholder",
        "输入指令或提问…（⌘Enter 发送）"
      ],
      [
        "style",
        "font-size:12.4px;"
      ]
    ]
  },
  {
    "line": 2423,
    "attributes": [
      [
        "class",
        "p-input"
      ],
      [
        "id",
        "pcomposerinput"
      ],
      [
        "placeholder",
        "对智能助手说：导入 /data/2026-plastic-batch3，做 SNV + SG 一阶导，再训一个 PLS-DA…"
      ]
    ]
  }
]
```

按钮属性仅3处变动：L1484剔除新增on、插值修复移除on；L2427发送新增说明性title。不改data-go/事件/disabled，不改既有按钮文本及位置。

## 锚点全量对照

原型2976→2976行，无行号位移。29项prototype_lines全部保持；完整对照如下。

| ID | old prototype_lines | new prototype_lines |
|---|---|---|
| F01 | [1484] | [1484] |
| F02 | [1678, 1714, 1715, 1716, 1717, 1718, 1721] | [1678, 1714, 1715, 1716, 1717, 1718, 1721] |
| F03 | [1802, 1810, 1821, 1830] | [1802, 1810, 1821, 1830] |
| F04 | [1948, 1955, 1978, 1983, 2866, 2872] | [1948, 1955, 1978, 1983, 2866, 2872] |
| F05 | [1597, 1810, 1946, 2361] | [1597, 1810, 1946, 2361] |
| F06 | [2338, 2339] | [2338, 2339] |
| F07 | [2331, 2359, 2360] | [2331, 2359, 2360] |
| F08 | [1885] | [1885] |
| S01 | [546, 1417] | [546, 1417] |
| S02 | [1844] | [1844] |
| S03 | [2310] | [2310] |
| N01 | [2294, 2531] | [2294, 2531] |
| N02 | [163, 204, 206, 2419] | [163, 204, 206, 2419] |
| N03 | [1244, 2423, 2427, 2940] | [1244, 2423, 2427, 2940] |
| N04 | [1470, 1478, 1479] | [1470, 1478, 1479] |
| N05 | [894, 258, 1946] | [894, 258, 1946] |
| N06 | [1642, 1647] | [1642, 1647] |
| D01 | [1458, 1524, 1168] | [1458, 1524, 1168] |
| D02 | [843, 2169] | [843, 2169] |
| D03 | [1597, 1608, 1815] | [1597, 1608, 1815] |
| D04 | [1384, 1386, 1428, 1435, 2290, 2291] | [1384, 1386, 1428, 1435, 2290, 2291] |
| D05 | [2249, 2269] | [2249, 2269] |
| D06 | [771, 2169, 1923, 1925, 1926] | [771, 2169, 1923, 1925, 1926] |
| D07 | [1661, 1726, 1730, 2361] | [1661, 1726, 1730, 2361] |
| D08 | [1732, 1862] | [1732, 1862] |
| D09 | [1428, 1461, 1854] | [1428, 1461, 1854] |
| D10 | [2217, 2254] | [2217, 2254] |
| D11 | [766, 770, 772] | [766, 770, 772] |
| D12 | [2533] | [2533] |

## 结构自检与SHA256

| 项目 | 原件 | 候选 |
|---|---|---|
| 错配结束标签 | 0 | 0 |
| 未闭合标签 | 0 | 0 |
| tr / div / p | 160 / 532 / 48 | 160 / 532 / 48 |
| 物理行数 | 2976 | 2976 |

- 原型：`78de8b003efa53e80b5231df27b2ed1d407e7bd2faaa9cd83106698d13fb1a8f` → 候选`11b6c2839bed04866e9b32cf5829ef45e8042ab440649594aa21a728f8b8889a`。
- 需求：`08408b0bd5dea317b4e17f365cde7b829804faf15defe96c1b8bf58ca1e29ead` → 同值，未编辑。
- batch2-original.html：`78de8b003efa53e80b5231df27b2ed1d407e7bd2faaa9cd83106698d13fb1a8f`，保持第0步备份字节不变。
- HTML内所有style/script块逐字一致；输入框属性全部一致；仅上列16行文字/说明性title/选中标记有差分。

## 需要科祥确认或范围限制

- F05引用歧义已由用户追加确认解决：ROI诚实标待绑定，OA沿用现有引用；指标ID形式化随台账，不算全文通过。
- FR-A05检测/掩膜→B域消费联动补偿卡仅登记待办，本批不备卡、不改代码。
- F07拒绝后统一追问为后续D域事项；D09 NAS实机与回归验收、D04 NAS只读/守卫证据均保留原边界。
- N05、D02/D03/D05/D06/D10/D12、S02/S03、Δ01/Δ02、Kappa冲突、N01/F06、F08、N02、发布与五件12.7.1证据待办均不触及。
- 公司目录HTML仅外部落盘；预期commit只含batch2-changelog.md及status-matrix.json，5个公司文档保持未跟踪。

## 最终落盘核验

候选生成阶段已完成上述自检；落盘、静态浏览器检查与最终Git范围核对结果将在提交前追加本节。

已完成：公司目录原型已落盘；源文件与静态检查的候选逐字节相同。临时localhost静态服务及检查页均已关闭，未启动项目开发服务。静态查看S01/S03及补充S02/S04/S07/S11，新增说明可见，未发现新增遮挡；未改既有窄幅密集换行。

最终复核结果：

```json
{
  "authorized_ids": [
    "F01",
    "F05",
    "F07",
    "N03",
    "D04",
    "D09"
  ],
  "unchanged_other_row_count": 23,
  "root_register_metadata_unchanged": true,
  "batch1_updates_unchanged": true,
  "ui_sha256": "11b6c2839bed04866e9b32cf5829ef45e8042ab440649594aa21a728f8b8889a",
  "requirement_sha256": "08408b0bd5dea317b4e17f365cde7b829804faf15defe96c1b8bf58ca1e29ead",
  "batch2_backup_sha256": "78de8b003efa53e80b5231df27b2ed1d407e7bd2faaa9cd83106698d13fb1a8f",
  "ui_lines": 2976,
  "all_29_prototype_lines_unchanged": true,
  "fragment_entries": 16,
  "fragment_unique_lines": 16,
  "diff_lines": [
    1384,
    1386,
    1431,
    1461,
    1484,
    1487,
    1600,
    1855,
    2290,
    2291,
    2359,
    2360,
    2361,
    2377,
    2423,
    2427
  ],
  "fragment_diff_sets_equal": true,
  "old_fragment_once_in_each_original_line": true,
  "forward_replay_byte_identical": true,
  "reverse_replay_recovers_backup": true,
  "all_11_input_tags_and_attributes_identical": true,
  "batch1_nonintersection_lines_unchanged": 48,
  "batch1_intersection": [
    2361
  ],
  "batch1_statistics_suffix_unchanged": true,
  "html_structure": {
    "mismatched_end_tags": 0,
    "unclosed_tags": 0,
    "counts": {
      "tr": 160,
      "div": 532,
      "p": 48
    }
  },
  "style_script_blocks_unchanged": true,
  "project_tests_build_package_push": false,
  "static_browser_review": {
    "server": "localhost temporary static files only; closed",
    "source_matches_inspected_fixture": true,
    "screens": [
      "S01助手",
      "S02汇总卡",
      "S03导入/全局composer",
      "S04 ROI",
      "S07回归分支",
      "S11汇总卡"
    ],
    "result": "新增说明可见，未发现新增遮挡或标签结构破损；原型既有窄幅密集换行未改；未调用真实服务"
  }
}
```

- 输入框特别核对：L2423原始input结束符及全部属性完整保留，说明在标签外；全11个input原始起始标签和解析属性完全一致。
- Git登记：仅本批6个ID各追加一条updates（batch/date/asset/status/detail/changelog）；去掉这6条新增字段后，整个JSON对象与d0d7900完全一致，含批1全部updates和根元数据。未改变任何prototype_lines。
- 零改动：批2第0步备份保持；批1日志与备份未改、矩阵中批1updates不变；原型批1的48个非交集行保持，L2361统计后缀保持；CSS/JS、所有既有结果数值、参数值及路径值、队列、矩阵、Kappa及待拍板条款保持。需求与历史HTML哈希不变。
- release-notes、源码、TASK、milestone证据均无Git差分；无证据恢复动作。提交前只有status-matrix.json为已跟踪改动，batch2-changelog.md按精确路径force-add；提交集合固定为这2个文件。5个公司文档不提交；不push。提交ID在交付回报中给出。
