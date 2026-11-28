# Study 实物级选优 v1

## 对话使用

新 Study 默认继续用观测级评分。实物任务必须先明确选择 `IMAGE` 或 `MAPPED`，再选择实物评分。例如：

> 基于此数据寻优 <实验编号>，按实物评分，一图一物，折数3，潜变量1-2；预处理候选：原谱；归一化候选：无

多图一物先通过现有分组 CSV／JSON 明确完整逐图 sample_id 表，或在已完成实验的实物表单中填写映射；随后可说“按实物评分，多图一物，复用已确认sample_id完整表”。MAPPED 空 mapping 是显式选择复用该完整表，不能复用缺省 HDR 路径或 batch。归档实验已有的报告声明会被继承，只读取声明，不读取留出集预测。混合场景 `MIXED` 和 NPZ 不能启用实物排序。

寻优方案卡可切换“实物评分／观测评分”，切换后必须重新审阅确认。缺少实物定义时保留原方案并提示补充，不猜测。首次验证建议3折、小候选集，再按需扩大范围；本改动不自动重跑真实数据。

## 定义与划分

- `config.sample_evaluation` 保存 IMAGE/MAPPED/MIXED、最低有效观测数（默认100）及显式映射。样品身份复用 sample_id，不从 batch 或 NPZ groups 推断。
- `config.study_selection` 保存 Study 编号、`evaluation_target`、实际划分组类型 `grouping`、评分口径及训练定义摘要；采用候选后原样带入正式训练。
- 实物目标按同一显式实物定义划分及评价。同一实物全部图不跨折；实物模式拒绝另一套图像／批次分组，不混用两种身份。
- 总体每类可评价实物数须不少于折数。排除真值冲突及有效观测不足后再次检查；不足明确拒绝，不自动降折。分折仍使用已有 StratifiedGroupKFold，并保存实际种子及 fold_assignment。
- 所有预处理只在折内训练侧拟合，验证侧只 transform；留出测试数据不参与取谱、拟合、评分或推荐。

## 两种评分协议

| 目标 | 主指标 | 折间波动 | 推荐规则 |
| --- | --- | --- | --- |
| pixel / `study_pixel_fold_v1` | 既有观测 CV 折均值 Macro-F1 | 原折 SD | 保留1-SE |
| sample / `study_sample_oof_v1` | 拼接全部验证预测后，按实物合并投票的 pooled OOF Macro-F1 | 单列折均值与SD，仅辅助 | pooled OOF最高分；同分按较少LV、较少算子、较小候选编号 |

实物评分复用 `sample_vote_v1` 报告算法：真值必须唯一，全部视图观测合并后投票；平票、真值冲突、有效观测不足单独列出并排除。保存的观测可能经过质量筛选、步长和抽样，不等于原图全部前景像元。不同候选因平票可能纳入数不同，必须一起查看覆盖率，不能只看F1。

任一验证折排除后缺少配置中的任一类别，则整个候选标记 `sample_metric_undefined`，主分数留空，不降级、不参与实物排名或采用。仍保留完整折记录、观测辅助成绩和逐实物 OOF 投票供诊断。全部候选无效时保存诊断结果，best/recommended为空，不提供采用按钮。

## 双排名与历史

实物 Study 同时给出实物 pooled OOF 排名和观测 pooled OOF 排名，使用同一候选、同一折和同一验证预测，主排序以实物为准；两者差异可以通过每个实物的真值、预测、投票数及排除原因逐条核对。还保存观测折均值与SD，不把两个统计口径混成一个误差条。

结果表展示双排名、纳入实物数、折间辅助波动，并展开逐实物结果和每折排除名单。41件实物、30/11类别不均衡时，名次差异不代表显著优劣；SD不是pooled OOF的置信区间。

旧结果缺少目标字段时，在读取投影中补 `evaluation_target: pixel`、`fold_mean_macro_f1` 和旧协议标记，不覆写结果文件或校验值、不换算实物排名。前端和采用入口均拒绝与结果目标不匹配的候选。报告默认继承训练配置；用户覆盖定义或阈值后与选优摘要不一致时明确提示重新寻优。

## 验证

固定全量命令见 [testing.md](testing.md)，使用 `--basetemp=.tmp-sample-suite`。

专项：`python -m pytest tests/test_study_sample_scoring.py tests/test_experiment_study.py tests/test_evaluation_definition.py tests/test_sample_evaluation.py -q --basetemp=.tmp-study-suite`。

验证包含可手算的双排名反转、pooled OOF与折均值不同、平票导致整类缺失、候选无效、折数不足、MAPPED多视图合并及同组不跨折、NPZ/MIXED拒绝、真实3折小候选对话→采用→训练→报告继承、重启读取及历史文件不变。脚本模型只验证路由和工具协议，不代表外部模型的自然语言规划质量。
