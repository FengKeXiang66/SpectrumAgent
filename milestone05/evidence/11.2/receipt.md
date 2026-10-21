# 11.2 B05/B06/B07 + 配方存储回执

## 文件清单（根 E:/AI_Agent，逐路径）

- `src-python/spectrumagent/preprocess/README.md（删除，原文移动）`
- `src-python/spectrumagent/preprocess/registry.py`
- `src-python/spectrumagent/preprocess/schema/__init__.py`
- `src-python/spectrumagent/preprocess/__init__.py`
- `src-python/spectrumagent/preprocess/operators/standardize.py`
- `src-python/spectrumagent/preprocess/operators/crop.py`
- `src-python/spectrumagent/preprocess/operators/resample.py`
- `src-python/spectrumagent/preprocess/recipes.py`
- `src-python/spectrumagent/preprocess/migrations.py`
- `src-python/tests/preprocess/test_registry.py`
- `src-python/tests/preprocess/test_standardize.py`
- `src-python/tests/preprocess/test_resample.py`
- `src-python/tests/preprocess/test_axis_contract.py`
- `src-python/tests/preprocess/test_recipes.py`
- `src-python/tests/preprocess/test_migrations.py`
- `milestone05/evidence/11.1/receipt.md`
- `milestone05/evidence/11.1/pytest-full.txt`
- `milestone05/evidence/11.2/builtin-seed.json`
- `milestone05/evidence/11.2/capture.py`
- `milestone05/evidence/11.2/fingerprint.json`
- `milestone05/evidence/11.2/pytest-full.txt`
- `milestone05/evidence/11.2/registry.diff`
- `milestone05/evidence/11.2/table-info.json`
- `milestone05/evidence/11.2/test-registry.diff`
- `milestone05/evidence/11.2/receipt.md`

提交信息：`#05 11.2 标准化、变轴算子与配方存储`。本回执与上述文件同次提交，精确commit hash在提交后报告。任务卡为科祥R9修订，执行期未改动/暂存卡。

## 测试数与执行模式

最终完整回归：**510 passed / 0 failed / 0 skipped**，10条既有第三方弃用警告，44.93s（pytest-full.txt原始输出）。基线434+新增76；原11.1的94个测试全绿，仅获准的test_registry.py:15集合断言改一行（git numstat为1新增/1删除），其余断言与93个测试不动。预处理组先独立实跑170通过；最终全量按仓库根、同一PowerShell调用设置 `PYTEST_DEBUG_TEMPROOT=E:/AI_Agent/.runtime/pytest-tmp`，`.venv/Scripts/python.exe -m pytest backend/tests src-python/tests -q`，默认参数、无筛选/并行；未使用pytest.exe。首轮全量510通过后，仅将形状错误detail对齐开工令原文，再次全量得到上述最终结果。

## 卡§5逐条自验

| 关键词 | 测试落点（src-python/tests/preprocess/） | 实跑结果 |
|---|---|---|
| B05四法 / B05补充R8 | test_standardize.py | 四公式独立对拍；standard ddof=0、逐波段参数列表；area按band_index的trapezoid、vector按L2；每次输入重算；零分母zeros/nan/error及NORMALIZATION_DEGENERATE(400)+zero_scale_count全过 |
| B06 / B06补充R8 | test_resample.py | source/target来自params、不注入run轴；闭区间端点/单命中/空命中；linear与spline多项式对拍；越界NaN与计数；FWHM中位间隔及严格>5%边界通过 |
| 变轴契约R9 | test_axis_contract.py | crop→resample谱条数不变、最后工作轴正确；无输入轴也能返回声明轴；拒改变谱条数/空输出/坏dtype/缺axis/非递增/长度错/非有限轴；meta只有axis_len/hash，无保留键axis；同bands声明新轴亦替换 |
| B07 / B07补充R8 | test_recipes.py | 新建及max+1版本；旧版本内容/返回副本/首次时间不变；API无update/delete/overwrite；同一全局配方被两项目引用无副本；默认code/算子名/不含reflectance三要素通过 |
| 迁移双跑幂等 | test_migrations.py | 同一连接连跑两次migrate，schema与全部种子行逐项一致；RecipeStore构造亦幂等；#04先跑的依赖明确检查 |
| 指纹敏感性 | test_recipes.py::test_fingerprint_really_switches_annotation_version_then_restores_without_io | 同dataset/源/像素数，仅换annotation_version_id两值，指纹不同；换回还原；Path.open被禁止仍通过，函数不读源文件 |
| §3五表DDL / R7 FK | test_migrations.py::test_ddl_verbatim_and_all_table_columns_types_notnull_defaults_foreign_keys | 实现DDL逐字等于卡SQL；另在独立内存DB执行卡DDL，逐表PRAGMA列名/类型/NOTNULL/默认值/PK/FK与真实迁移DB完全一致；跨#04标注版本FK与NOTNULL实测生效 |
| 11.1既有94测试 | 原有四测试文件 | 全绿；六个算子实现、既有模型、resolve/parse/json_safe/多版本逻辑均未回改 |

### 实现边界

registry.py实际diff见registry.diff，仅替换原形状检查所在连续代码段：限定二维、谱条数不变、非空实数；处理/验证meta.axis并摘要，缺声明的变bands报错。旧段之前与之后逐字核验不变。schema文件旧内容为完整前缀、只追加三模型；注册文件仅追加import与三注册项。测试单行diff见test-registry.diff。

axis摘要针对meta保留键axis；声明params仍沿用11.1的原有记录逻辑，source/target是配方自包含参数。axis字节哈希为C-contiguous float64 bytes，完整输出工作轴在PipelineResult.wavelengths。重采样相邻间隔的中位代理值须至少两波段，模型据此校验；crop可输出单波段。NaN源谱不填充：spline不可拟合行输出NaN。

B05的fitted只在返回meta，未写入配方；run/scaler_params落库归11.3。RecipeStore只持久化配方及项目关联，不执行run。存储API没有update/delete方法，也没有新增历史修改触发器或任何DDL外的列。所有连接使用既有connect_database（foreign_keys=ON）。新建库须先调用#04 DatasetRegistry完成其迁移，本次未新增中央装配。

## 五表实际PRAGMA table_info + FK

来源：capture.py在E盘隔离SQLite库实跑。dflt_value=`null`表示PRAGMA返回None，`'0'`为SQLite记录的默认表达式。下列notnull/pk均保留SQLite原值（TEXT PRIMARY KEY的notnull可为0）；未擅自增加NOT NULL。完整foreign_key_list含on_update/on_delete/match等字段见table-info.json。

### preprocess_recipe

| cid | name | type | notnull | dflt_value | pk | FK |
|---:|---|---|---:|---|---:|---|
| 0 | id | TEXT | 0 | null | 1 | — |
| 1 | code | TEXT | 1 | null | 0 | — |
| 2 | name | TEXT | 1 | null | 0 | — |
| 3 | description | TEXT | 0 | null | 0 | — |
| 4 | builtin | INTEGER | 1 | '0' | 0 | — |
| 5 | created_at | TEXT | 1 | null | 0 | — |
### preprocess_recipe_version

| cid | name | type | notnull | dflt_value | pk | FK |
|---:|---|---|---:|---|---:|---|
| 0 | id | TEXT | 0 | null | 1 | — |
| 1 | recipe_id | TEXT | 1 | null | 0 | preprocess_recipe(id) |
| 2 | version_no | INTEGER | 1 | null | 0 | — |
| 3 | pipeline | TEXT | 1 | null | 0 | — |
| 4 | note | TEXT | 0 | null | 0 | — |
| 5 | created_at | TEXT | 1 | null | 0 | — |
### project_recipe

| cid | name | type | notnull | dflt_value | pk | FK |
|---:|---|---|---:|---|---:|---|
| 0 | project_id | TEXT | 1 | null | 1 | project(id) |
| 1 | recipe_id | TEXT | 1 | null | 2 | preprocess_recipe(id) |
| 2 | selected_at | TEXT | 1 | null | 0 | — |
### preprocess_run

| cid | name | type | notnull | dflt_value | pk | FK |
|---:|---|---|---:|---|---:|---|
| 0 | id | TEXT | 0 | null | 1 | — |
| 1 | cube_id | TEXT | 1 | null | 0 | — |
| 2 | annotation_version_id | TEXT | 1 | null | 0 | annotation_version(id) |
| 3 | recipe_version_id | TEXT | 1 | null | 0 | preprocess_recipe_version(id) |
| 4 | b01_branch | TEXT | 1 | null | 0 | — |
| 5 | input_fingerprint | TEXT | 1 | null | 0 | — |
| 6 | scaler_params | TEXT | 0 | null | 0 | — |
| 7 | metrics | TEXT | 0 | null | 0 | — |
| 8 | status | TEXT | 1 | null | 0 | — |
| 9 | error | TEXT | 0 | null | 0 | — |
| 10 | finished_at | TEXT | 0 | null | 0 | — |
| 11 | note | TEXT | 0 | null | 0 | — |
| 12 | created_at | TEXT | 1 | null | 0 | — |
### preprocess_artifact

| cid | name | type | notnull | dflt_value | pk | FK |
|---:|---|---|---:|---|---:|---|
| 0 | id | TEXT | 0 | null | 1 | — |
| 1 | run_id | TEXT | 1 | null | 0 | preprocess_run(id) |
| 2 | kind | TEXT | 1 | null | 0 | — |
| 3 | relative_path | TEXT | 1 | null | 0 | — |
| 4 | sha256 | TEXT | 1 | null | 0 | — |
| 5 | created_at | TEXT | 1 | null | 0 | — |

## 内置配方实际种子行

来源：capture.py创建的隔离DB；UUID/created_at为该次实际插入值，不是产品固定默认值。name是实现层展示文案；code、链及参数来自卡§2.2/R8/S1。没有reflectance步，没有数据集特定hdr，没有全量谱数组。

```json
{
  "id": "f0e8e5f2-d834-4199-b606-09a1512f4307",
  "code": "plastic-snv-sg1",
  "name": "塑料 SNV + SG 一阶导数",
  "description": "场景示例默认值、可改；需求场景 S1 第418行",
  "builtin": 1,
  "created_at": "2026-10-21T00:04:08.511377+00:00",
  "versions": [
    {
      "id": "d038db55-c0d5-46f7-8bec-f8aeea795e38",
      "recipe_id": "f0e8e5f2-d834-4199-b606-09a1512f4307",
      "version_no": 1,
      "pipeline": {
        "steps": [
          {
            "op": "snv",
            "version": 1,
            "params": {}
          },
          {
            "op": "sg_derivative",
            "version": 1,
            "params": {
              "order": 1,
              "window": 15,
              "polyorder": 2
            }
          }
        ]
      },
      "note": null,
      "created_at": "2026-10-21T00:04:08.511377+00:00"
    }
  ]
}
```

## 指纹敏感性实测

来源：纯函数测试夹具（synthetic IDs/source digests），没有冒充真实数据集登记哈希。source_hashes在函数外提供，不重新读源文件；按相对路径排序后依次取摘要，与dataset_id、annotation_version_id、像素数字符串用`|`连接、UTF-8后SHA256。11.2不实现run指纹持久化或读源校验。

```json
{
  "source_level": "pure function fixture measurement; synthetic IDs and source digests, no source file IO",
  "dataset_id": "11111111-1111-4111-8111-111111111111",
  "source_hashes": {
    "sample.raw": "84f0830dd690c0bd024941bb7f77cd4efb2d2ffb727ba026270f5d7d13db5585",
    "sample.hdr": "725c04b99900df65b488695a54f7fc37b20084576c575284c86f9cf270ccd4aa"
  },
  "n_pixels": 6,
  "annotation_version_a": "22222222-2222-4222-8222-222222222222",
  "annotation_version_b": "33333333-3333-4333-8333-333333333333",
  "fingerprint_a": "225690d9dc8343d744446b4a7a8fe62e5790075065fdbe3a01235989f7b2ac25",
  "fingerprint_b": "2942884fa49be93822336358df93318eaeb3e0da722249cdc05fde6996e0c765",
  "restored": "225690d9dc8343d744446b4a7a8fe62e5790075065fdbe3a01235989f7b2ac25"
}
```

## 11.1证据补档 / 纪律 / 就绪

11.1 receipt.md与HEAD原包README字节一致；pytest-full.txt与原.runtime/m05-11.1/pytest-full.txt字节一致，历史输出仍为434 passed。原包README已git rm，包目录不留回执。

任务卡未由执行者改动；依赖、旧六算子、路由、Rust、前端、compare/run引擎均未改。seeds_20.json已在#04入库，本轮保持跟踪状态及原字节，SHA256仍为388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2；公司文档保持未跟踪。所有git add均单独文件路径，无-A或点目录。

无未决口径问题；先前注册名集合冲突按科祥单行授权解决，未削弱其余校验。11.2交付后停止等复核，不进入11.3。无安装、下载、tag、push或Release操作。
