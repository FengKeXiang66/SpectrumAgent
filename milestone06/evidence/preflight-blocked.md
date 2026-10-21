# TASK-06 开工前契约冲突（待裁定，未实现功能）

任务卡 §0–§11 已完整读取。基准 HEAD 为 a052b3353b2e353acbe4e522d02b7e188c2a05fd，未回退 hotfix。没有修改任务卡、实现或既有测试，没有提交。

## 命令与实测输出

仓库根、PowerShell，默认沙箱；非 pytest，不涉及 pytest 临时目录清理：

```powershell
& 'C:/Program Files/Git/usr/bin/wc.exe' -l -- 'TASK-06-标注显示能力.md'
& .venv/Scripts/python.exe milestone06/evidence/preflight.py
```

第一条原始输出：

```text
539 TASK-06-标注显示能力.md
```

第二条通过 Registry.readable(raw=False) 读取真实 pe，不猜 interleave、不读全立方体，只取与 HEAD 默认预览完全相同的降采样 band 0。采用当前 png_gray 编码，原始输出摘录如下；完整 JSON 见 preflight-output.json：

```json
{
  "cube_shape": [231, 640, 200],
  "preview_shape": [116, 320],
  "stride": 2,
  "round_vs_head_different_pixels": 8502,
  "head_png_sha256": "6165fcd12361926afe59e780f2008f5a44c065f666909d6785a92b579e857203",
  "round_png_sha256": "aec2b87fad9964859b237bef7140d8f9327c6879bc78d1f1cfe26b14abdf5a78",
  "png_bytes_equal": false,
  "card_explicit_bands_example": [186, 124, 62],
  "example_satisfies_strict_increasing": false
}
```

## 停工点与需裁定的条款

1. §2.1 要求 round，§2.1/§6.1 同时要求与 HEAD min/max 截断映射逐字节相同。HEAD api/datasets.py 使用 astype(np.uint8)，并未 round；实测不相同。需决定 none 保留截断，或修订回归锚点；不能自行挑选。
2. §3.1 要求显式 bands 严格递增，§6.2/§6.10 的成功请求却为 186,124,62；§2.3 第8步返回 RGB=(c,b,a)，§6.5 又要求“三个波段严格递增”。需区分内部搜索 a<b<c 与输出通道顺序，并裁定手动RGB参数是否只要求三者不同而保留传入顺序。
3. §4 文件白名单遗漏以下联动：api/openapi.json（src-python/tests/data/test_api.py:207–210 完整相等断言）；src-python/tests/data/test_api.py:132（该旧测试请求默认预览，但147–149断言旧min/max截断，默认改auto后冲突）；annotation/display/display.ts（§6.9指定，但§4未列）；docs/release-notes-v0.1.2.md（§2.1要求记账，但§4未列）。需授权最小同步范围；不会删除、过滤或弱化断言。
4. §2.2 只给出伪彩联合2/98分位映射，未给 stretch=none 分支；§2.4 却要求手动LUT基于伪彩 stretch=none 的未拉伸图。需钉死该分支是否为三通道共用联合min/max；不会自行选择。

## 验收状态

D1–D7 尚未实现；没有新增功能测试，三套全量回归与静态检查尚未执行，未把卡头基线冒充本轮实测。仅新增本目录的诊断脚本、JSON与本说明；正式实现等待以上口径裁定。当前不产生子项 commit，也不修改 TASK 文件。
