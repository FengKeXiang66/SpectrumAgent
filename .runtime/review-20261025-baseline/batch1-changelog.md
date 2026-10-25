# 第一批原型自洽修复变更日志

授权：2026-10-25用户本批提示词；起始HEAD：1757ee6。只修改获准原型、发布说明及本批登记工件。

## 12.7.1 证据摘录

摘录自 **18:49 第二次独立重跑**（文件started_at=2026-10-24T10:49:45.973857+00:00，UTC；北京时间18:49）。已提交的 **18:40版本（106/106）才是12.7.1的结构化原件**，本摘录仅作重复确认数据点留存，不替换原件；本批不重跑测试。

- 工作区e2e：断言总数 106，通过数 106，success=true。
- 统计复核：assertions列表长度 106，passed=true数量 106。

| performance场景 | seconds | confirm_seconds | file_bytes | db_row.sha256 |
|---|---:|---:|---:|---|
| small | 0.8262554999964777 | 1.5794312999933027 | 23016 | `e5bd1041e557f16be0f0ce80c6dcefad4efdaa65d5ab852865a9bf5adccadf86` |
| large | 1.44131340002059 | 3.6616022000089288 | 120049512 | `ccd387e4aadaf60cefd0d7a59c4407f390fea74dc1bda17b1d0adb5c74e0ae09` |

对话额外摘录：confirm_seconds=1.4299219000095036；mat_generation_seconds=0.7616726000269409；savemat_seconds=0.006315400009043515。这些跨度嵌套，不能相加。

五件待办（**本批仅登记，不修、不重跑**）：

1. `node-test.txt`为补丁前95/95，需重跑至107基线。
2. `acceptance-map` G1-06对该文件的引用需勘误。
3. `build.txt`需在下次打包时刷新。
4. `summary.json`仍记12.7旧基线（node95/e2e92）。
5. `receipt.md`同上，且无12.7.1回执。

恢复前git status：

```text
 M milestone07/evidence/12.7/e2e-result.json
 M milestone07/evidence/12.7/performance.json
?? SpecMetis_vs_SpectrumAgent_架构对比_20261022.md
?? 光谱Agent_D域编排_讨论交接摘要_20261022.md
?? 光谱平台_阶段一_代码审查与进度分析_20261018.md
?? 光谱平台_阶段一_需求符合度与质量评估_20261022.md
?? 光谱数据AI-Agent处理平台_阶段一技术选型_定稿v1.1_1792327262075_csvb.md
```

后续执行指定的git checkout恢复两份证据；恢复后的状态将在下一小节登记。

## 第0步恢复结果

已执行用户指定的`git checkout -- milestone07/evidence/12.7/e2e-result.json milestone07/evidence/12.7/performance.json`。恢复后仅剩5个未跟踪公司文档，两份证据均回到已提交状态：

```text
?? SpecMetis_vs_SpectrumAgent_架构对比_20261022.md
?? 光谱Agent_D域编排_讨论交接摘要_20261022.md
?? 光谱平台_阶段一_代码审查与进度分析_20261018.md
?? 光谱平台_阶段一_需求符合度与质量评估_20261022.md
?? 光谱数据AI-Agent处理平台_阶段一技术选型_定稿v1.1_1792327262075_csvb.md
```

## 本批修改清单（候选已生成，最终落盘核验另记）

范围对应：①F04；②N04；③D07；④N06；⑤F02仅术语；⑥F03；⑦D11；⑧D08+D01已裁定回写；⑨release-notes唯一字符串替换。对应状态登记ID共9个：F04/N04/D07/N06/F02/F03/D11/D08/D01。

- 原型版本标题保持ui-v2.3，本批以fixture版本和文件哈希识别修订，不自行升级文档基线版本。
- 全部采用等行数原位替换：2976→2976行，换行仍为LF、UTF-8无BOM；不增删tr/div/p行，标签总数亦保持tr160/div532/p48。F03在原1803行容器内使用两列section/dl说明，未增加tr/div/p。
- 未改需求v2.7、历史版、TASK、源码、外壳、算法、阈值、队列示例数、待裁定条款、训练MAT导出、milestone证据（除第0步获授权恢复两份文件）。
- 不运行build、项目测试或打包；下述是获授权的文档算术/结构/锚点自检。

### 每项old→new

| 项目 | old→new | 状态边界 |
|---|---|---|
| F04 | 未分层21.6万/782500/单图43200 → 八图OOF汇总782500、误分43200、OA94.5%；ps_032单图100000评价/5600误分/94.4%，7520排除 | 授权算术范围完成；新增Kappa不一致单列待裁定，F04不全文关闭 |
| N04 | 3偏小但只展示1个且折叠全通过 → 240解析成功=236无告警+4带告警；展示5=3+2，折叠235=233+2 | 失败/未处理均0；3偏小为mix_221/222/223，ps_032另有2坏波段 |
| D07 | 超像素/像素共用62%与不同范围782500 → SP504/812=62.07%；单图像素88000/107520=81.85%；自动来源0/88000=0% | 12为待确认候选区域数，不是未确认或不确定超像素数；不与812作同层统计 |
| N06 | 标签1–4但含背景5 → 1–5；背景为本fixture已选择可训练类，计入类数和标注像素 | -1/-2不作为背景、不训练；快捷键不等于存储label_index；不扩成全项目新策略 |
| F02 | cos参照未写清 → cos_uv相邻对增长0.92；cos_s种子参照报告；入队0.80 | 所有阈值及1714–1718五个候选数值保持；未改任何算法 |
| F03 | 单配方前后图与dB值 → 同cube/同确认标注版本的两配方并排，列Fisher、原值指标、SNR分布、排除/未排名原因 | 无算子出参不编数，显示未获得数值结果；Fisher主排序；历史Kappa原值保留并标阶段二/不适用 |
| D11 | E14、F05~F08/H01、NFR07错映射 → E18、F01/H02、NFR06/I01/L10 | 仅改§2.2三个FR单元格 |
| D08 | 聚合规则不明 → cube×label均值/标准差、granularity=sample、主标签只读多数类、排除-1/-2 | 回写TASK04既定规则；B10仍逐像素，不用聚合谱代算 |
| D01（仅已裁定部分） | SG规则不全/推荐字样 → 正奇数窗、0≤p<w、interp窗≤输入bands、导数按band_index、delta1.0；15/2/1注明场景示例可改 | TASK05早期≤笔误由§5.1与现有schema的严格<澄清；未改SNR8dB/波长容差等未裁定阈值 |
| release-notes | 当前产品配置仍为0.1.3 → 当前产品配置为 0.3.0（tauri.conf.json） | 按用户指定完整字符串匹配替换1次；后半句及其他字节不变，最终核验另记 |

### 所有改动的原行片段（可重放）

原型在E:/AI_Agent仓库之外，无法直接纳入该Git提交。此处完整登记每次替换的行号、old/new片段；候选与原件的全部差分均由这些替换组成。每行old_fragment在该行必须恰好出现一次，按表列顺序重放。此为存档说明，不自行把公司HTML复制为另一份受控基线。

```json
[
  {
    "line": 766,
    "ids": [
      "D11"
    ],
    "old_fragment": "FR-E01~E10 · E14",
    "new_fragment": "FR-E01~E10 · <strong>E18</strong>"
  },
  {
    "line": 770,
    "ids": [
      "D11"
    ],
    "old_fragment": "FR-F05~F08 · H01",
    "new_fragment": "FR-F01 · H02"
  },
  {
    "line": 772,
    "ids": [
      "D11"
    ],
    "old_fragment": "FR-L10 · <strong>NFR-07</strong>",
    "new_fragment": "FR-L10 · FR-I01 · <strong>NFR-06</strong>"
  },
  {
    "line": 1168,
    "ids": [
      "D01"
    ],
    "old_fragment": "SG 窗口必须为奇数且 ≤ 波段数（当前 224）",
    "new_fragment": "SG 窗口 w 必须为正奇数；p 为非负整数且 p &lt; w；mode=interp 时 w ≤ 当前输入波段数（示例 224）；导数 d=1/2，d=0 切换仅平滑算子"
  },
  {
    "line": 1768,
    "ids": [
      "D01"
    ],
    "old_fragment": "平滑窗口 w（奇数）",
    "new_fragment": "拟合窗口 w（正奇数）"
  },
  {
    "line": 1770,
    "ids": [
      "D01"
    ],
    "old_fragment": "窗口越大越平滑，但会钝化 1724 nm 附近的窄特征",
    "new_fragment": "窗口越大越平滑，但会钝化 1724 nm 附近的窄特征。TASK-05：w=15、p=2、d=1 为场景示例默认值，可改；p 为非负整数且 p &lt; w；mode 默认 interp（此时 w 不超过当前输入波段数）；导数按波段序号计算，delta=1.0、unit=band_index，不按 nm 归一"
  },
  {
    "line": 1774,
    "ids": [
      "D01"
    ],
    "old_fragment": "2（推荐）",
    "new_fragment": "2（场景示例，可改）"
  },
  {
    "line": 1778,
    "ids": [
      "D01"
    ],
    "old_fragment": "0（仅平滑）",
    "new_fragment": "0（切换 sg_smooth，仅平滑）"
  },
  {
    "line": 1469,
    "ids": [
      "N04",
      "F04"
    ],
    "old_fragment": "240 个立方体 · 耗时 38 s",
    "new_fragment": "ui-self-consistency-v1 · 240 个立方体 · 耗时 38 s"
  },
  {
    "line": 1470,
    "ids": [
      "N04"
    ],
    "old_fragment": "<b>可导入。</b>波长轴与位深一致，未发现重复文件；有 <b>2 个波段</b>需处置、<b>3 个立方体</b>体积偏小（可能采集不完整）。",
    "new_fragment": "<b>可导入 240 / 240。</b>成功解析 240（236 个无告警、4 个带告警），失败 0、未处理 0；未发现重复文件。ps_032 有 <b>2 个波段</b>需处置；mix_221 / mix_222 / mix_223 共 <b>3 个立方体</b>体积偏小；本 fixture 中告警不阻断导入。"
  },
  {
    "line": 1479,
    "ids": [
      "N04"
    ],
    "old_fragment": "… 其余 235 个文件已折叠（全部通过）",
    "new_fragment": "… 其余 235 个已折叠：233 个无告警 + mix_222 / mix_223 共 2 个偏小告警；均可导入。已展示 5 个：3 个无告警 + 2 个带告警。"
  },
  {
    "line": 1636,
    "ids": [
      "D07"
    ],
    "old_fragment": "积累一批已确认标注（当前 62%）",
    "new_fragment": "积累一批已确认标注（本图超像素确认率 504/812=62.07%，不是像素标注率）"
  },
  {
    "line": 1642,
    "ids": [
      "N06"
    ],
    "old_fragment": "1–4",
    "new_fragment": "1–5（含背景）"
  },
  {
    "line": 1648,
    "ids": [
      "N06",
      "D08"
    ],
    "old_fragment": "按数字键切换；当前选中 <b style=\"color:var(--brand-d);\">PP</b>",
    "new_fragment": "按数字键 1–5 切换；当前选中 <b style=\"color:var(--brand-d);\">PP</b>。本 fixture 的背景5是显式标注的可训练类，计入5类与已标注像素；-1 留白、-2 不确定不属于背景，也不计入训练。快捷键序号不等于存储 label_index。"
  },
  {
    "line": 1658,
    "ids": [
      "D07"
    ],
    "old_fragment": "本图统计",
    "new_fragment": "本图统计 · ps_032"
  },
  {
    "line": 1661,
    "ids": [
      "D07"
    ],
    "old_fragment": "<span class=\"k\">已确认</span><span class=\"v mono\">504 个 · 62%</span>",
    "new_fragment": "<span class=\"k\">超像素确认率</span><span class=\"v mono\">504 / 812 · 62.07%</span>"
  },
  {
    "line": 1662,
    "ids": [
      "D07"
    ],
    "old_fragment": "<span class=\"k\">待确认</span><span class=\"v mono\">12 个</span>",
    "new_fragment": "<span class=\"k\">待确认候选</span><span class=\"v mono\">12 个区域（队列）</span>"
  },
  {
    "line": 1664,
    "ids": [
      "D07"
    ],
    "old_fragment": "width:62%",
    "new_fragment": "width:62.07%"
  },
  {
    "line": 1665,
    "ids": [
      "D07"
    ],
    "old_fragment": "预计剩余 <b>8 分钟</b>（按当前确认速度）",
    "new_fragment": "预计剩余 <b>8 分钟</b>（按当前确认速度）。<br>ann-ui-fixture-v1：像素标注率（含背景）88,000 / 107,520 = <b>81.85%</b>；不确定 -2：4,000 px；留白 -1：15,520 px。<br>自动来源比例：0 / 88,000 = <b>0%</b>（分母为本图已标注像素，均由人工确认赋标）。"
  },
  {
    "line": 1692,
    "ids": [
      "D07"
    ],
    "old_fragment": "ps_032.hdr · 已确认 504 / 812 超像素",
    "new_fragment": "ps_032.hdr · 超像素确认 504 / 812 = 62.07%"
  },
  {
    "line": 1678,
    "ids": [
      "F02"
    ],
    "old_fragment": "cos ≥ 0.92",
    "new_fragment": "cos_uv ≥ 0.92"
  },
  {
    "line": 1721,
    "ids": [
      "F02"
    ],
    "old_fragment": "相似度低于 0.80 的区域<b>不进入队列</b>，按\"不确定就留白\"处理。",
    "new_fragment": "TASK-04 §5.3：增长按相邻超像素对的 <b>cos_uv ≥ 0.92</b>；报告 min_similarity 是区域成员对<b>种子谱 cos_s</b>的最小值，可因沿链增长低于 0.92；入队另以 <b>min_similarity ≥ 0.80</b>为下限，低于 0.80 不进入队列、按\"不确定就留白\"处理。队列所列相似度采用种子参照 cos_s，三个概念不混用。"
  },
  {
    "line": 1724,
    "ids": [
      "D07",
      "N06"
    ],
    "old_fragment": "已标注像素分布",
    "new_fragment": "ps_032 像素分布 · 5类与状态"
  },
  {
    "line": 1726,
    "ids": [
      "D07"
    ],
    "old_fragment": "124,600 px",
    "new_fragment": "12,000 px"
  },
  {
    "line": 1727,
    "ids": [
      "D07"
    ],
    "old_fragment": "94,100 px",
    "new_fragment": "18,000 px"
  },
  {
    "line": 1728,
    "ids": [
      "D07"
    ],
    "old_fragment": "78,300 px",
    "new_fragment": "30,000 px"
  },
  {
    "line": 1729,
    "ids": [
      "D07"
    ],
    "old_fragment": "64,900 px",
    "new_fragment": "8,000 px"
  },
  {
    "line": 1730,
    "ids": [
      "D07",
      "N06"
    ],
    "old_fragment": "<span class=\"k\">留白</span><span class=\"v mono\" style=\"color:var(--warn);\">420,600 px</span>",
    "new_fragment": "<span class=\"k\">背景5 / 状态</span><span class=\"v mono\" style=\"font-size:10.9px;\">背景 20,000 px<br>-2 不确定 4,000 px<br>-1 留白 15,520 px</span>"
  },
  {
    "line": 1732,
    "ids": [
      "D08",
      "D01",
      "N06"
    ],
    "old_fragment": ">聚合为样本级标签</button>",
    "new_fragment": ">聚合为样本级标签</button><small style=\"display:block; margin-top:8px; color:var(--ink3);\">TASK-04：按 cube×label 有界聚合均值/标准差谱；annotation.granularity=sample；样品主标签由像素数最多的 label 只读推导（本图 PS）；-1/-2 排除，背景5按普通类计数。</small>"
  },
  {
    "line": 1802,
    "ids": [
      "F03"
    ],
    "old_fragment": "处理前后对比 <span class=\"r\">上：原始反射率　下：SNV + SG 一阶导</span>",
    "new_fragment": "同输入多配方对比 <span class=\"r\">ps_032 · ann-ui-fixture-v1 · 4类共68,000像素</span>"
  },
  {
    "line": 1803,
    "ids": [
      "F03"
    ],
    "old_fragment": "<div data-gen=\"compare\" data-w=\"620\" data-h=\"240\"></div>",
    "new_fragment": "<div style=\"display:flex; gap:12px; flex-wrap:wrap;\" aria-label=\"同cube同标注版本配方并排对比\"><section style=\"flex:1 1 160px; min-width:0; margin:0; box-sizing:border-box; overflow-wrap:anywhere; border:1px solid var(--line); padding:10px; border-radius:8px;\"><b>plastic-snv-sg1</b><small style=\"display:block;\">SNV + SG一阶导（w15/p2/d1，场景示例）</small><dl style=\"font-size:11.4px; line-height:1.7;\"><dt>Fisher（主排序，降序）</dt><dd>未获得数值结果；运行后由已有引擎返回</dd><dt>类间距离 / 类内方差</dt><dd>未获得数值结果</dd><dt>SNR：均值 / 中位数 / P10 / P90</dt><dd>未获得数值结果</dd><dt>排除类 / 未排名原因</dt><dd>由 excluded_classes、错误与 limitations 回显；无有效 Fisher 不排名</dd></dl></section><section style=\"flex:1 1 160px; min-width:0; margin:0; box-sizing:border-box; overflow-wrap:anywhere; border:1px solid var(--line); padding:10px; border-radius:8px;\"><b>plastic-snv-only</b><small style=\"display:block;\">SNV</small><dl style=\"font-size:11.4px; line-height:1.7;\"><dt>Fisher（主排序，降序）</dt><dd>未获得数值结果；运行后由已有引擎返回</dd><dt>类间距离 / 类内方差</dt><dd>未获得数值结果</dd><dt>SNR：均值 / 中位数 / P10 / P90</dt><dd>未获得数值结果</dd><dt>排除类 / 未排名原因</dt><dd>由 excluded_classes、错误与 limitations 回显；无有效 Fisher 不排名</dd></dl></section></div>"
  },
  {
    "line": 1808,
    "ids": [
      "F03"
    ],
    "old_fragment": "处理质量评估",
    "new_fragment": "逐像素指标与适用边界"
  },
  {
    "line": 1810,
    "ids": [
      "F03"
    ],
    "old_fragment": "18.6<span style=\"font-size:13px;\"> dB</span>",
    "new_fragment": "未获得数值结果"
  },
  {
    "line": 1811,
    "ids": [
      "F03"
    ],
    "old_fragment": "处理后整体信噪比（原始 12.4 dB）",
    "new_fragment": "SNR为逐像素谱均值/相邻波段一阶差分RMS，再汇总均值、中位数及P10/P90；不使用dB口径"
  },
  {
    "line": 1818,
    "ids": [
      "F03"
    ],
    "old_fragment": "链路可复现：<b>配方哈希 + 数据集哈希 + 算子版本</b>三者固定即可完全还原输出。",
    "new_fragment": "TASK-05 §2.5：同 cube、同 annotation_version，按选中类的逐像素 B01 后反射率运行多配方；不使用聚合均值谱代算。<b>Fisher=类间距离/类内方差，确定性主排序，LLM不选优。</b>类间距离为两两类均值谱欧氏距离均值；类内方差按类像素数加权。零方差/单样本类排除并说明、不加epsilon；SNR仅同类算子间可比，类间距离原值不跨配方比较；无标签仅展示SNR并提示局限。"
  },
  {
    "line": 1821,
    "ids": [
      "F03"
    ],
    "old_fragment": "这一步在本项目里的历史效果",
    "new_fragment": "历史 Kappa 表 · 阶段二 / 不适用"
  },
  {
    "line": 1830,
    "ids": [
      "F03"
    ],
    "old_fragment": "数据来自本项目历史实验的聚合，不是模型推荐。",
    "new_fragment": "阶段二历史实验示意，保留原示例值；不参与本次Fisher选优。本次比较复用已有CompareEngine，均须显式指定同cube、同annotation_version及多个recipe_version。"
  },
  {
    "line": 1858,
    "ids": [
      "D07"
    ],
    "old_fragment": "ds-v3（240 立方体 · 已标注 62%）",
    "new_fragment": "ds-v3（240 立方体；标注率按cube/版本查看）"
  },
  {
    "line": 1862,
    "ids": [
      "D08"
    ],
    "old_fragment": "像素级标注（已聚合为样本级）",
    "new_fragment": "按 cube×label 聚合为样本级"
  },
  {
    "line": 1862,
    "ids": [
      "D08"
    ],
    "old_fragment": "</select>",
    "new_fragment": "</select><small style=\"display:block; color:var(--ink3);\">聚合产物为均值/标准差谱，annotation.granularity=sample；主标签按像素数最多类只读推导，-1/-2 排除。此处样本级产物不替代B10逐像素比较输入。</small>"
  },
  {
    "line": 1899,
    "ids": [
      "D07",
      "N06"
    ],
    "old_fragment": "420,600 px 未标注像素不参与训练，不当作背景类",
    "new_fragment": "-1 留白与 -2 不确定不参与训练，不当作背景5；S05 ps_032 对应15,520 / 4,000 px，本批次不共用该单图分母"
  },
  {
    "line": 1939,
    "ids": [
      "F04"
    ],
    "old_fragment": "run_20261011_0412 · ds-v3 · plastic-snv-sg1 · plsda-v7 —— 所有数值来自算子层返回，模型只做解读。",
    "new_fragment": "ui-self-consistency-v1 · run_20261011_0412 · ds-v3 · ann-eval-fixture-v1 · plastic-snv-sg1 · plsda-v7。示例评价集：8图的5折OOF子集，共782,500像素，每像素只计一次；非240图全量，也非S05标注快照。以下为版本化mock展示，非真实NAS实测。"
  },
  {
    "line": 1946,
    "ids": [
      "F04"
    ],
    "old_fragment": "总体精度 OA（交叉验证均值）",
    "new_fragment": "总体精度 OA（OOF子集汇总，按像素加权）"
  },
  {
    "line": 1947,
    "ids": [
      "F04"
    ],
    "old_fragment": "Kappa 系数",
    "new_fragment": "既有Kappa例值 · 待核对"
  },
  {
    "line": 1947,
    "ids": [
      "F04"
    ],
    "old_fragment": "metrics.kappa · v1.3 · run_…0412",
    "new_fragment": "metrics.kappa · v1.3 · run_…0412；本矩阵推导≈0.918089，与0.921不一致，保留数值待科祥确认"
  },
  {
    "line": 1948,
    "ids": [
      "F04"
    ],
    "old_fragment": "21.6<span style=\"font-size:13px;\"> 万</span>",
    "new_fragment": "782,500"
  },
  {
    "line": 1948,
    "ids": [
      "F04"
    ],
    "old_fragment": "参与评估像素（留白已排除）",
    "new_fragment": "8图OOF评价子集像素（排除-1/-2）"
  },
  {
    "line": 1948,
    "ids": [
      "F04"
    ],
    "old_fragment": "sample.split · v1.1 · run_…0412",
    "new_fragment": "ui-self-consistency-v1 · eval-oof-8 · run_…0412"
  },
  {
    "line": 1955,
    "ids": [
      "F04"
    ],
    "old_fragment": "行 = 真实 · 列 = 预测 · 格内为像素数 / 行占比",
    "new_fragment": "8图OOF汇总 · 行=真实/列=预测 · 合计782,500/误分43,200"
  },
  {
    "line": 1978,
    "ids": [
      "F04"
    ],
    "old_fragment": "<span class=\"r\">ps_032.hdr</span>",
    "new_fragment": "<span class=\"r\">ps_032.hdr · 640×168=107,520<br>评价100,000；排除7,520；图为布局示意</span>"
  },
  {
    "line": 1982,
    "ids": [
      "F04"
    ],
    "old_fragment": "<span>正确 <b>94.5%</b></span>",
    "new_fragment": "<span>本图正确 <b>94.4%</b></span>"
  },
  {
    "line": 1983,
    "ids": [
      "F04"
    ],
    "old_fragment": "误分 <b>43,200 px</b>",
    "new_fragment": "本图误分 <b>5,600 / 100,000 px</b>"
  },
  {
    "line": 2361,
    "ids": [
      "D07",
      "N06",
      "F04"
    ],
    "old_fragment": "另：这个数据集的像素级标注只覆盖了 <b>62%</b>，剩余 420,600 px 我按<b>留白</b>处理，没有当作背景类 —— 否则模型会把\"没看过\"当成\"背景\"来学。",
    "new_fragment": "统计按范围分开：S05 ps_032 / ann-ui-fixture-v1 的像素标注率为 <b>88,000/107,520=81.85%</b>（含背景5）；-1留白15,520、-2不确定4,000均排除。超像素确认率504/812=62.07%；自动来源比例0/88,000=0%。S08另用ann-eval-fixture-v1的8图OOF子集782,500像素，不能共用分母。"
  }
]
```

## Fixture定义全文

fixture仅为用户授权的原型示例数据合同，不是业务需求或新默认值。所有240个cube完整展开如下；尺寸按lines×samples×bands登记。S03导入快照、S05标注版本、S06确认版输入和S08另一标注版OOF评价子集明确分层。S07整批240样品的训练日志仅为既有流程示意；S08只汇总其中8图的OOF评价子集，不宣称代表240图全量指标。

```json
{
  "id": "ui-self-consistency-v1",
  "kind": "authorized static UI mock; not real NAS measurements or new engine output",
  "dataset_version": "ds-v3",
  "import": {
    "total": 240,
    "displayed": 5,
    "folded": 235,
    "clean": 236,
    "accepted_with_warnings": 4,
    "parsed_success": 240,
    "failed": 0,
    "unprocessed": 0,
    "small_cube_ordinals": [
      221,
      222,
      223
    ],
    "bad_band_cube_ordinal": 32,
    "bad_band_count": 2,
    "cubes": [
      {
        "ordinal": 1,
        "file": "batch3/pp_001.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 2,
        "file": "batch3/cube_002.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 3,
        "file": "batch3/cube_003.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 4,
        "file": "batch3/cube_004.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 5,
        "file": "batch3/cube_005.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 6,
        "file": "batch3/cube_006.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 7,
        "file": "batch3/cube_007.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 8,
        "file": "batch3/cube_008.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 9,
        "file": "batch3/cube_009.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 10,
        "file": "batch3/cube_010.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 11,
        "file": "batch3/cube_011.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 12,
        "file": "batch3/cube_012.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 13,
        "file": "batch3/cube_013.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 14,
        "file": "batch3/pet_014.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 15,
        "file": "batch3/cube_015.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 16,
        "file": "batch3/cube_016.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 17,
        "file": "batch3/cube_017.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 18,
        "file": "batch3/cube_018.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 19,
        "file": "batch3/cube_019.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 20,
        "file": "batch3/cube_020.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 21,
        "file": "batch3/cube_021.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 22,
        "file": "batch3/cube_022.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 23,
        "file": "batch3/cube_023.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 24,
        "file": "batch3/cube_024.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 25,
        "file": "batch3/cube_025.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 26,
        "file": "batch3/cube_026.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 27,
        "file": "batch3/cube_027.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 28,
        "file": "batch3/cube_028.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 29,
        "file": "batch3/cube_029.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 30,
        "file": "batch3/cube_030.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 31,
        "file": "batch3/cube_031.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 32,
        "file": "batch3/ps_032.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": [
          "two_bad_bands"
        ]
      },
      {
        "ordinal": 33,
        "file": "batch3/cube_033.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 34,
        "file": "batch3/cube_034.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 35,
        "file": "batch3/cube_035.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 36,
        "file": "batch3/cube_036.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 37,
        "file": "batch3/cube_037.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 38,
        "file": "batch3/cube_038.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 39,
        "file": "batch3/cube_039.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 40,
        "file": "batch3/cube_040.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 41,
        "file": "batch3/cube_041.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 42,
        "file": "batch3/cube_042.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 43,
        "file": "batch3/cube_043.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 44,
        "file": "batch3/cube_044.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 45,
        "file": "batch3/cube_045.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 46,
        "file": "batch3/cube_046.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 47,
        "file": "batch3/abs_047.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 48,
        "file": "batch3/cube_048.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 49,
        "file": "batch3/cube_049.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 50,
        "file": "batch3/cube_050.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 51,
        "file": "batch3/cube_051.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 52,
        "file": "batch3/cube_052.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 53,
        "file": "batch3/cube_053.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 54,
        "file": "batch3/cube_054.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 55,
        "file": "batch3/cube_055.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 56,
        "file": "batch3/cube_056.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 57,
        "file": "batch3/cube_057.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 58,
        "file": "batch3/cube_058.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 59,
        "file": "batch3/cube_059.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 60,
        "file": "batch3/cube_060.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 61,
        "file": "batch3/cube_061.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 62,
        "file": "batch3/cube_062.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 63,
        "file": "batch3/cube_063.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 64,
        "file": "batch3/cube_064.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 65,
        "file": "batch3/cube_065.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 66,
        "file": "batch3/cube_066.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 67,
        "file": "batch3/cube_067.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 68,
        "file": "batch3/cube_068.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 69,
        "file": "batch3/cube_069.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 70,
        "file": "batch3/cube_070.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 71,
        "file": "batch3/cube_071.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 72,
        "file": "batch3/cube_072.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 73,
        "file": "batch3/cube_073.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 74,
        "file": "batch3/cube_074.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 75,
        "file": "batch3/cube_075.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 76,
        "file": "batch3/cube_076.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 77,
        "file": "batch3/cube_077.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 78,
        "file": "batch3/cube_078.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 79,
        "file": "batch3/cube_079.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 80,
        "file": "batch3/cube_080.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 81,
        "file": "batch3/cube_081.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 82,
        "file": "batch3/cube_082.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 83,
        "file": "batch3/cube_083.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 84,
        "file": "batch3/cube_084.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 85,
        "file": "batch3/cube_085.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 86,
        "file": "batch3/cube_086.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 87,
        "file": "batch3/cube_087.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 88,
        "file": "batch3/cube_088.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 89,
        "file": "batch3/cube_089.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 90,
        "file": "batch3/cube_090.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 91,
        "file": "batch3/cube_091.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 92,
        "file": "batch3/cube_092.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 93,
        "file": "batch3/cube_093.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 94,
        "file": "batch3/cube_094.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 95,
        "file": "batch3/cube_095.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 96,
        "file": "batch3/cube_096.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 97,
        "file": "batch3/cube_097.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 98,
        "file": "batch3/cube_098.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 99,
        "file": "batch3/cube_099.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 100,
        "file": "batch3/cube_100.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 101,
        "file": "batch3/cube_101.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 102,
        "file": "batch3/cube_102.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 103,
        "file": "batch3/cube_103.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 104,
        "file": "batch3/cube_104.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 105,
        "file": "batch3/cube_105.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 106,
        "file": "batch3/cube_106.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 107,
        "file": "batch3/cube_107.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 108,
        "file": "batch3/cube_108.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 109,
        "file": "batch3/cube_109.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 110,
        "file": "batch3/cube_110.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 111,
        "file": "batch3/cube_111.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 112,
        "file": "batch3/cube_112.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 113,
        "file": "batch3/cube_113.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 114,
        "file": "batch3/cube_114.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 115,
        "file": "batch3/cube_115.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 116,
        "file": "batch3/cube_116.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 117,
        "file": "batch3/cube_117.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 118,
        "file": "batch3/cube_118.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 119,
        "file": "batch3/cube_119.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 120,
        "file": "batch3/cube_120.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 121,
        "file": "batch3/cube_121.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 122,
        "file": "batch3/cube_122.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 123,
        "file": "batch3/cube_123.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 124,
        "file": "batch3/cube_124.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 125,
        "file": "batch3/cube_125.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 126,
        "file": "batch3/cube_126.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 127,
        "file": "batch3/cube_127.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 128,
        "file": "batch3/cube_128.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 129,
        "file": "batch3/cube_129.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 130,
        "file": "batch3/cube_130.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 131,
        "file": "batch3/cube_131.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 132,
        "file": "batch3/cube_132.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 133,
        "file": "batch3/cube_133.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 134,
        "file": "batch3/cube_134.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 135,
        "file": "batch3/cube_135.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 136,
        "file": "batch3/cube_136.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 137,
        "file": "batch3/cube_137.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 138,
        "file": "batch3/cube_138.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 139,
        "file": "batch3/cube_139.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 140,
        "file": "batch3/cube_140.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 141,
        "file": "batch3/cube_141.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 142,
        "file": "batch3/cube_142.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 143,
        "file": "batch3/cube_143.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 144,
        "file": "batch3/cube_144.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 145,
        "file": "batch3/cube_145.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 146,
        "file": "batch3/cube_146.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 147,
        "file": "batch3/cube_147.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 148,
        "file": "batch3/cube_148.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 149,
        "file": "batch3/cube_149.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 150,
        "file": "batch3/cube_150.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 151,
        "file": "batch3/cube_151.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 152,
        "file": "batch3/cube_152.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 153,
        "file": "batch3/cube_153.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 154,
        "file": "batch3/cube_154.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 155,
        "file": "batch3/cube_155.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 156,
        "file": "batch3/cube_156.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 157,
        "file": "batch3/cube_157.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 158,
        "file": "batch3/cube_158.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 159,
        "file": "batch3/cube_159.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 160,
        "file": "batch3/cube_160.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 161,
        "file": "batch3/cube_161.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 162,
        "file": "batch3/cube_162.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 163,
        "file": "batch3/cube_163.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 164,
        "file": "batch3/cube_164.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 165,
        "file": "batch3/cube_165.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 166,
        "file": "batch3/cube_166.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 167,
        "file": "batch3/cube_167.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 168,
        "file": "batch3/cube_168.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 169,
        "file": "batch3/cube_169.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 170,
        "file": "batch3/cube_170.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 171,
        "file": "batch3/cube_171.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 172,
        "file": "batch3/cube_172.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 173,
        "file": "batch3/cube_173.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 174,
        "file": "batch3/cube_174.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 175,
        "file": "batch3/cube_175.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 176,
        "file": "batch3/cube_176.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 177,
        "file": "batch3/cube_177.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 178,
        "file": "batch3/cube_178.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 179,
        "file": "batch3/cube_179.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 180,
        "file": "batch3/cube_180.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 181,
        "file": "batch3/cube_181.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 182,
        "file": "batch3/cube_182.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 183,
        "file": "batch3/cube_183.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 184,
        "file": "batch3/cube_184.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 185,
        "file": "batch3/cube_185.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 186,
        "file": "batch3/cube_186.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 187,
        "file": "batch3/cube_187.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 188,
        "file": "batch3/cube_188.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 189,
        "file": "batch3/cube_189.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 190,
        "file": "batch3/cube_190.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 191,
        "file": "batch3/cube_191.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 192,
        "file": "batch3/cube_192.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 193,
        "file": "batch3/cube_193.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 194,
        "file": "batch3/cube_194.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 195,
        "file": "batch3/cube_195.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 196,
        "file": "batch3/cube_196.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 197,
        "file": "batch3/cube_197.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 198,
        "file": "batch3/cube_198.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 199,
        "file": "batch3/cube_199.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 200,
        "file": "batch3/cube_200.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 201,
        "file": "batch3/cube_201.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 202,
        "file": "batch3/cube_202.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 203,
        "file": "batch3/cube_203.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 204,
        "file": "batch3/cube_204.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 205,
        "file": "batch3/cube_205.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 206,
        "file": "batch3/cube_206.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 207,
        "file": "batch3/cube_207.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 208,
        "file": "batch3/cube_208.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 209,
        "file": "batch3/cube_209.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 210,
        "file": "batch3/cube_210.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 211,
        "file": "batch3/cube_211.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 212,
        "file": "batch3/cube_212.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 213,
        "file": "batch3/cube_213.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 214,
        "file": "batch3/cube_214.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 215,
        "file": "batch3/cube_215.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 216,
        "file": "batch3/cube_216.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 217,
        "file": "batch3/cube_217.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 218,
        "file": "batch3/cube_218.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 219,
        "file": "batch3/cube_219.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 220,
        "file": "batch3/cube_220.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 221,
        "file": "batch3/mix_221.hdr",
        "lines": 96,
        "samples": 420,
        "bands": 224,
        "pixels": 40320,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": [
          "small_size"
        ]
      },
      {
        "ordinal": 222,
        "file": "batch3/mix_222.hdr",
        "lines": 96,
        "samples": 420,
        "bands": 224,
        "pixels": 40320,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": [
          "small_size"
        ]
      },
      {
        "ordinal": 223,
        "file": "batch3/mix_223.hdr",
        "lines": 96,
        "samples": 420,
        "bands": 224,
        "pixels": 40320,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": [
          "small_size"
        ]
      },
      {
        "ordinal": 224,
        "file": "batch3/cube_224.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 225,
        "file": "batch3/cube_225.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 226,
        "file": "batch3/cube_226.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 227,
        "file": "batch3/cube_227.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 228,
        "file": "batch3/cube_228.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 229,
        "file": "batch3/cube_229.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 230,
        "file": "batch3/cube_230.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 231,
        "file": "batch3/cube_231.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 232,
        "file": "batch3/cube_232.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 233,
        "file": "batch3/cube_233.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 234,
        "file": "batch3/cube_234.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 235,
        "file": "batch3/cube_235.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 236,
        "file": "batch3/cube_236.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 237,
        "file": "batch3/cube_237.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 238,
        "file": "batch3/cube_238.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 239,
        "file": "batch3/cube_239.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      },
      {
        "ordinal": 240,
        "file": "batch3/cube_240.hdr",
        "lines": 168,
        "samples": 640,
        "bands": 224,
        "pixels": 107520,
        "dtype": "uint16",
        "import_status": "accepted",
        "warnings": []
      }
    ]
  },
  "labels": {
    "shortcut_order": [
      "PP",
      "PET",
      "PS",
      "ABS",
      "背景"
    ],
    "background": {
      "shortcut": 5,
      "trainable": true,
      "included_in_class_count": true,
      "included_in_labeled_pixel_count": true
    },
    "excluded_states": {
      "-1": "unlabeled",
      "-2": "uncertain"
    },
    "shortcut_is_not_persisted_label_index": true
  },
  "working_snapshot": {
    "cube": "batch3/ps_032.hdr",
    "annotation_version": "ann-ui-fixture-v1",
    "source_for_S06": "confirmed snapshot only; never directly consume draft",
    "pixels": 107520,
    "label_pixels": {
      "PP": 12000,
      "PET": 18000,
      "PS": 30000,
      "ABS": 8000,
      "背景": 20000
    },
    "labeled_pixels": 88000,
    "uncertain_pixels": 4000,
    "unlabeled_pixels": 15520,
    "labeled_pixel_ratio": 0.8184523809523809,
    "total_superpixels": 812,
    "confirmed_superpixels": 504,
    "pending_candidate_regions": 12,
    "superpixel_confirmation_ratio": 0.6206896551724138,
    "automatic_source_labeled_pixels": 0,
    "automatic_source_ratio": 0.0,
    "readonly_main_label": "PS"
  },
  "aggregation": {
    "group_by": [
      "cube",
      "label"
    ],
    "spectra": [
      "mean",
      "std"
    ],
    "annotation.granularity": "sample",
    "sample_code": "cube name",
    "main_label": "argmax(label pixel count), readonly",
    "exclude": [
      -1,
      -2
    ]
  },
  "preprocess_comparison": {
    "cube": "batch3/ps_032.hdr",
    "annotation_version": "ann-ui-fixture-v1",
    "selected_labels": [
      "PP",
      "PET",
      "PS",
      "ABS"
    ],
    "selected_pixels": 68000,
    "recipe_codes": [
      "plastic-snv-sg1",
      "plastic-snv-only"
    ],
    "numeric_metrics": null,
    "metric_display_state": "not obtained; run existing CompareEngine to populate, no invented numbers",
    "ranking": "Fisher descending; failed/null-Fisher rows not ranked; show exclusions and limitations",
    "input": "per-pixel B01-converted reflectance; not aggregated mean spectrum",
    "sg_example": {
      "window": 15,
      "polyorder": 2,
      "order": 1,
      "mode": "interp",
      "delta": 1.0,
      "unit": "band_index"
    },
    "historical_kappa_table": "unchanged values; phase two/not applicable"
  },
  "evaluation": {
    "id": "eval-oof-8",
    "annotation_version": "ann-eval-fixture-v1",
    "different_from_S05_working_snapshot": true,
    "scope": "OOF evaluation subset of eight cubes within 240-cube dataset; not all training samples; each included pixel occurs once in one held-out fold",
    "cubes": [
      {
        "file": "batch3/pp_001.hdr",
        "fold": 1,
        "pixels": 100000,
        "errors": 5900,
        "total_pixels": 107520,
        "excluded_pixels": 7520,
        "correct": 94100
      },
      {
        "file": "batch3/cube_002.hdr",
        "fold": 1,
        "pixels": 100000,
        "errors": 5900,
        "total_pixels": 107520,
        "excluded_pixels": 7520,
        "correct": 94100
      },
      {
        "file": "batch3/cube_003.hdr",
        "fold": 2,
        "pixels": 100000,
        "errors": 4800,
        "total_pixels": 107520,
        "excluded_pixels": 7520,
        "correct": 95200
      },
      {
        "file": "batch3/cube_004.hdr",
        "fold": 2,
        "pixels": 100000,
        "errors": 4800,
        "total_pixels": 107520,
        "excluded_pixels": 7520,
        "correct": 95200
      },
      {
        "file": "batch3/cube_005.hdr",
        "fold": 3,
        "pixels": 100000,
        "errors": 5500,
        "total_pixels": 107520,
        "excluded_pixels": 7520,
        "correct": 94500
      },
      {
        "file": "batch3/pet_014.hdr",
        "fold": 3,
        "pixels": 100000,
        "errors": 5500,
        "total_pixels": 107520,
        "excluded_pixels": 7520,
        "correct": 94500
      },
      {
        "file": "batch3/ps_032.hdr",
        "fold": 4,
        "pixels": 100000,
        "errors": 5600,
        "total_pixels": 107520,
        "excluded_pixels": 7520,
        "correct": 94400
      },
      {
        "file": "batch3/abs_047.hdr",
        "fold": 5,
        "pixels": 82500,
        "errors": 5200,
        "total_pixels": 107520,
        "excluded_pixels": 25020,
        "correct": 77300
      }
    ],
    "folds": [
      {
        "fold": 1,
        "evaluation_subset_cubes": [
          "batch3/pp_001.hdr",
          "batch3/cube_002.hdr"
        ],
        "pixels": 200000,
        "errors": 11800,
        "correct": 188200,
        "oa": 0.941
      },
      {
        "fold": 2,
        "evaluation_subset_cubes": [
          "batch3/cube_003.hdr",
          "batch3/cube_004.hdr"
        ],
        "pixels": 200000,
        "errors": 9600,
        "correct": 190400,
        "oa": 0.952
      },
      {
        "fold": 3,
        "evaluation_subset_cubes": [
          "batch3/cube_005.hdr",
          "batch3/pet_014.hdr"
        ],
        "pixels": 200000,
        "errors": 11000,
        "correct": 189000,
        "oa": 0.945
      },
      {
        "fold": 4,
        "evaluation_subset_cubes": [
          "batch3/ps_032.hdr"
        ],
        "pixels": 100000,
        "errors": 5600,
        "correct": 94400,
        "oa": 0.944
      },
      {
        "fold": 5,
        "evaluation_subset_cubes": [
          "batch3/abs_047.hdr"
        ],
        "pixels": 82500,
        "errors": 5200,
        "correct": 77300,
        "oa": 0.936969696969697
      }
    ],
    "total_pixels": 782500,
    "correct_pixels": 739300,
    "error_pixels": 43200,
    "oa": 0.9447923322683706,
    "display_oa_percent": "94.5%",
    "row_labels": [
      "PP",
      "PET",
      "PS",
      "ABS",
      "背景"
    ],
    "confusion_matrix": [
      [
        121300,
        1300,
        2100,
        3200,
        500
      ],
      [
        2200,
        91500,
        1500,
        700,
        300
      ],
      [
        800,
        1400,
        70500,
        11600,
        300
      ],
      [
        900,
        1600,
        13400,
        55000,
        400
      ],
      [
        120,
        210,
        320,
        350,
        401000
      ]
    ],
    "row_totals": [
      128400,
      96200,
      84600,
      71300,
      402000
    ],
    "column_totals": [
      125320,
      96010,
      87820,
      70850,
      402500
    ],
    "single_map": "ps_032:100000 evaluated +7520 excluded out of107520;5600 errors;94.4% correct",
    "graphics": "generated classmap is layout illustration; counts come from fixture, not reverse-calculated from image",
    "existing_kappa": 0.921,
    "matrix_implied_kappa": 0.9180891982703563,
    "kappa_status": "newly identified disagreement; preserve existing values, flag for owner decision; do not relabel as verified fold mean"
  }
}
```

## 数字变化与算式验证

| 范围/数字 | 算式与结果 |
|---|---|
| 导入完整批次像素数 | 237×(640×168)+3×(420×96)=25,603,200；不是S08评价分母 |
| 导入状态 | 236无告警+4带告警=240解析成功；成功240+失败0+未处理0=240 |
| 展示/折叠 | 3无告警+2带告警=5；233无告警+2带告警=235；5+235=240；1展示偏小+2折叠偏小=3 |
| S05像素 | 12000+18000+30000+8000+20000=88000；88000+4000+15520=107520=640×168 |
| S05超像素 | 504/812×100=62.0689655…%，显示62.07%，进度条62.07%；812−504=308未确认超像素，不能与候选队列12区域相混 |
| S05像素标注率 | 88000/107520×100=81.845238…%，显示81.85%；背景20000计入 |
| S05自动来源比例 | 0自动来源已标注像素/88000全部已标注像素=0%；均由人工确认赋标，机器产生候选不算自动赋标 |
| S06四类输入 | 12000+18000+30000+8000=68000；同cube、同ann-ui-fixture-v1；不选背景不等于把背景当留白 |
| 主标签 | max(PP12000,PET18000,PS30000,ABS8000,背景20000)=PS30000，只读推导 |
| S08评价集合 | 7×100000+82500=782500；8×107520=860160；860160−782500=77660排除 |
| 矩阵行和 | 128400+96200+84600+71300+402000=782500；列和125320+96010+87820+70850+402500=782500 |
| 矩阵正确/误分 | 对角121300+91500+70500+55000+401000=739300；非对角=782500−739300=43200 |
| 汇总OA | 739300/782500×100=94.4792332…%，按1位小数显示94.5%；不是未加权折均 |
| 按cube误分 | 5900+5900+4800+4800+5500+5500+5600+5200=43200 |
| 五折子集 | 像素200000+200000+200000+100000+82500=782500；误分11800+9600+11000+5600+5200=43200；每像素只属一个OOF折 |
| 单图ps_032 | 100000评价+7520排除=107520；100000−5600=94400正确；94400/100000=94.4%；整体43200误分包含本图5600，不能全部贴在本图 |
| 新发现Kappa差异 | pe=Σ(行和×列和)/782500²；κ=(739300/782500−pe)/(1−pe)=0.91808919827…；不同于既有0.921。原0.921保留并标待核对，不发明折均值解释差异 |
| 旧数字移除 | S05四类124600/94100/78300/64900及留白420600属于未定义范围，替换为上列单图计数；跨页420600及62%混用删除，改用同一单图定义；21.6万替换前已定义eval-oof-8分母 |
| SG既定数值 | 15为正奇数、0≤2<15、d=1属于1/2；delta=1.0与mode=interp沿用TASK05；不引入新默认或波长阈值 |
| F03旧SNR展示 | 原18.6dB/12.4dB不是TASK05规定的逐像素比值口径，改为未获得数值结果；未计算、未伪造新SNR或Fisher数值 |

## 29项锚点全量对照

采用等行数替换，无行号位移；仍给出全量对照便于验收。prototype_lines数组不改。

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

## 结构自检与候选SHA256

- 原型原件与候选均由HTMLParser按嵌套栈检查：错配结束标签0，未闭合标签0。tr/div/p总数分别160/532/48，前后相同；全部29项锚点行号保持。
- 五个候选相似度行1714–1718与原件逐字节相同；混淆矩阵CM_ROWS不变。
- 原型旧SHA256：`59f7ef4b77b764fc667d562f626311f21abba7a277c3dc9daba9d2cdca295022` → 候选新SHA256：`78de8b003efa53e80b5231df27b2ed1d407e7bd2faaa9cd83106698d13fb1a8f`。
- 需求v2.7旧SHA256：`08408b0bd5dea317b4e17f365cde7b829804faf15defe96c1b8bf58ca1e29ead` → 当前同值（未编辑）；落盘后再重算确认。

## 需要科祥确认／范围限制

1. 新增Kappa冲突：矩阵κ≈0.918089，原卡/历史表/解读/台账等多处为0.921。本批不扩展更改各页指标，仅在S08该卡标明不一致；请决定后续是否以同一评价集合统一Kappa及关联解读。F04不登记为全文关闭。
2. 外部原型不属于E:/AI_Agent Git工作树：实际HTML单独落盘，仓库commit仅收发布说明、此日志及状态登记；日志保存全部old/new片段和哈希以便追溯。未另造受控HTML基线。
3. D10/D12、S02/S03、Δ01/Δ02、F06语义、v0.3.0门槛均保留待裁定，本批未改。D03的1724nm等旧问题也未顺手修改。

## 最终落盘核验

- 公司目录原型已落盘，字节与已检查候选一致；2976行不变，实际修改49行，全部原行替换片段已在上文完整登记。
- 当前源文件SHA256：需求 `08408b0bd5dea317b4e17f365cde7b829804faf15defe96c1b8bf58ca1e29ead`（旧→新不变）；原型 `59f7ef4b77b764fc667d562f626311f21abba7a277c3dc9daba9d2cdca295022` → `78de8b003efa53e80b5231df27b2ed1d407e7bd2faaa9cd83106698d13fb1a8f`。
- release-notes SHA256：`f1cd2ae349b26c9f898134f0d9df6959c3c5aa5b7837c69111f1baf3f60a476d` → `ed1c13ba2508a3acdcd6cae48662c1b0f38ce231d01f2a9628eeff8e1b1ec191`；28→28行，只有指定字符串替换1次，后半句及其他字节不变。
- status-matrix仅9个授权ID追加updates，20个其他ID逐对象不变；全部29个prototype_lines数组不变。
- 原型HTML最终字节与通过栈式结构检查的候选完全一致：标签错配0，未闭合0；tr160/div532/p48与原件相同。1714–1718候选数值行、CM_ROWS及所有待拍板条款对应行保持原字节。
- 静态浏览器检查S05/S06/S08：两配方可并排；新统计、阈值参照和评价范围可见。只启动了临时localhost静态文件服务，检查页与服务已关闭；未启动项目开发服务、build、项目测试或打包。
- 范围外显示问题：当前窄预览宽度下，S08混淆矩阵超出左卡边界；已对照原件确认同样存在，本批未改布局。后续如需修须另行授权；与N02安装态复现分开登记。
- 暂存前git diff仅docs/release-notes-v0.3.0.md；两份12.7证据与其余受禁源码/TASK均无工作区差分。原有5个未跟踪公司文档保留且不纳入提交。
- 提交范围固定3件仓库工件：docs/release-notes-v0.3.0.md、.runtime/review-20261025-baseline/batch1-changelog.md、.runtime/review-20261025-baseline/status-matrix.json。后两件由精确路径force-add（.runtime被忽略）；公司目录HTML无法直接纳入此仓库，完整差分已存于日志。提交ID见交付回报。
