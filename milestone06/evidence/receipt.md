# TASK-06 S05 显示能力回执

D1–D7完成，按任务卡R10/R11及最终§6.6a更正。各子项分别提交，原hotfix a052b33未回退。本回执随D7提交，D7哈希见本提交的git log；前六项为c3d7bf6 /3729f3c /10db522 /bbb38b1 /3748f0a /592ce39。

## 产品与测试文件（逐路径）

- src-python/spectrumagent/api/datasets.py：扩展preview、独立spectra/mean；gray编码器、旧band/region函数AST保持不变。
- src-python/spectrumagent/display/falsecolor.py（新）：共享范围映射、RGB编码、本项目自动选波段算法版本1。
- src-python/spectrumagent/api/openapi.json：由真实app程序化生成，完整相等断言保留。
- src-python/tests/test_display_falsecolor.py（新）：57个参数化用例；全部名称见summary.json。
- src-python/tests/data/test_api.py：只将旧像素测试的请求补stretch=none；其余代码与断言逐字不动。
- src-tauri/src/datasets_dev.rs：Preview.band Option与三个可选参数、新SpectraMean变体；新增2测试。原forward安全函数体逐字不变。
- src/components/datasets/api.ts：类型化preview/spectra_mean请求投影，仍只有datasets_forward出口。
- src/components/datasets/types.ts：扩展Preview/transport/取谱类型，保留S04旧调用。
- src/components/annotation/display/DisplayToolbar.tsx（新）：模式/波段/RGB/拉伸与只读取谱控件，当前波长标注与光谱原值/断线显示。
- src/components/annotation/display/display.ts（新）：请求互斥、半开选区、LUT纯函数。
- src/components/annotation/display/display.test.ts（新）：13个node测试；既有61个node测试不改。
- src/components/annotation/canvas/AnnotationCanvas.tsx：任意Preview底图、本地LUT、只读点/框谱分派；onload/onerror hotfix逐字保留。
- src/components/annotation/AnnotationWorkbench.tsx：独立显示state与取谱请求；不自持label_map或undo栈，显示参数不进入sidecar。
- docs/release-notes-v0.1.2.md：默认2/98映射变更、自己的自动算法口径、D1–D7交付记账。

## 测试和证据

改前624 Python /56 Rust（含doctest）/61 node，改后681 /58 /74，全部0 failed、0 skipped。执行命令、模式、原始输出见D1–D7.md与summary.json；十条既有Python依赖弃用警告原样保留。最终tsc exit0、clippy --all-targets -- -D warnings零警告、边界审计exit0。

证据目录内容分组：

- preflight.py /preflight-output.json /preflight-blocked.md：首次读卡、量化冲突的真实诊断，保留历史过程。
- baseline-*.txt：改前四套检查原始输出。
- D1.md–D7.md、d1-*–d7-*：每子项命令、结果及模式（未重复的套件明确注明）。
- generate_openapi.py：从真实app导出快照的可复算入口。
- performance.py：启动真实独立sidecar、loopback HTTP、身份校验与真实PE测量；不mock引擎。
- d4-performance.* /final-performance.json /performance.txt：两轮成功测量；d4-performance-attempt1.*保留PID探针失败原因与未计时事实。
- d4-auto-rgb.png /d4-manual-rgb.png /final-auto-rgb.png /final-manual-rgb.png：真实PE图像；字节数和SHA256见summary.json。
- pytest-full.txt /cargo-full.txt /node-full.txt /tsc.txt /clippy.txt /audit-boundary.txt：最终全量检查输出。
- acceptance-map.md：§6十二条及子条逐条对位。
- check_scope.py /scope-check.json /scope-check.txt：机械白名单、旧接口AST、hotfix、安全函数、依赖不变与seeds哈希检查。
- summary.json：套件数字、执行模式、测试名称、性能原值、产物哈希和人工未测项。

真实PE自动结果RGB=[177,148,103]，波长=[1622.12,1500.83,1312.63]nm；只记录本机观测，不把该组合写死在测试。降采样2、候选corr为100×100，独立band-index矩阵复算一致，max|corr|=0.6876864141308303。完整命令与原始数值见D4/D7和performance.txt。none-PNG与a052b33的旧灰度PNG SHA256相同；真实点/区域谱最大绝对误差均0。显示前后working/versions、源文件哈希均不变。

## 冲突、裁定与未执行项

首次四项冲突在R10闭环（none截断、RGB不要求递增、四文件授权、RGB none联合min/max）。D4三分位位置与退化异常在R11闭环。最终发现R11的§6.6a措辞错误，用户确认主算法实现正确并修卡；执行方没有自行挑条款，也没有修改任务卡。当前无未决算法口径。

只按§4及明确授权文件改动；app.py、SessionStore、annotation routes、S04组件、Rust命令注册/ACL、依赖、版本、审计脚本均不改。公司文档、.workbuddy-ai/与用户.workbuddy/未动；所有TASK卡不修改、不暂存。seeds_20 SHA256保持388ED3A86BDF60C5054E8DF9A5EB197A96A112B0BF2FC59EFA1BCF1A29F648D2。

未执行实机WebView/安装态UI冒烟，未重新打安装包，不声称这些通过。拖动无IPC按卡§6.9以纯函数测试加代码审查验收。没有新增全波段伪彩、导数/SG显示、反差对比、坏波段/坏像元标记；没有改标注编辑/保存/校验语义。需求文档回写归备卡方。本次不打tag、不push、不建Release。
