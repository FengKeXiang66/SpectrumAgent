# 检查点4修正批次：生产特性与安装目录

负责人本轮明确批准下载NSIS3.13、nsis_tauri_utils0.5.3、微软WebView2 x64 Evergreen离线安装器，工具缓存E:\AI_Agent\src-tauri\target\.tauri。不开证书校验绕过、不增依赖、三锁前后逐项复算。

## 事实更正

本批次**外壳 exe 重新编译**，命令显式带 `--features custom-protocol`，记录构建日志、bin/lib/build-script特性指纹和新SHA。旧36fb指纹是features=[]；本地tauri2.12.4源码is_dev()为!cfg!(feature="custom-protocol")。旧批次生命周期数据保留为历史进程证据，不能迁移为本批次发布态UI或资源加载证据。本批次重新跑30轮矩阵、真实UI、完整DOM/存储审计、两RT_MANIFEST和布局验证，不靠迁移论证省测。

上一报告关于保留外壳SHA及编译行为的申请理由撤回，由本记录及本批次REPORT取代；旧原始记录保留供审计。本次只保留引擎SHA及冻结批次：revision-20261018-smoke-headers/product-manifest.json，完整544文件不改。先显式custom-protocol的--no-bundle构建与实测，再相同特性bundle --no-binary-patching，防止bundle阶段原地修改已测新外壳。未启用test-probes，probe/stub不得进入安装包。

## 模板单行变更

官方raw GET遇ECONNRESET，原错误已落盘。改为从已安装CLI2.12.3原生二进制提取完整内嵌installer.nsi：唯一Unicode/ManifestDPIAware开头、NUL边界、末尾完整CreateOrUpdateDesktopShortcut函数交叉校验。原件33780字节，SHA256=c36f2746493870577c584db49ca99cf5ee77ab211d893ff6851ccc4375866cf3；原生CLI SHA256=96b97801111a86b78811fee887e4e361c37b57239509a002f0fad493a6da12a5，偏移12279896。网上tag全文与本地内嵌原件的逐字节比对未验证，不冒称一致。

仅第524行增加`Programs\`，新模板33789字节，SHA256=e78b55ce753c8ef4ff99554a9fd4f8b29c287cda890b5aad64ee8ee3e9205a89；完整diff恰一行。守卫509行、perMachine514–521行、卸载段保持。配置指向src-tauri/nsis/installer.nsi；installMode=currentUser，无管理员权限；不使用hooks：实际SetOutPath655行，PREINSTALL657–658行。

路径事实：主机Rust数据根继续LOCALAPPDATA/SpectrumAgent；默认程序目录只改成LOCALAPPDATA/Programs/SpectrumAgent。上游实际834行是`RMDir /REBOOTOK "$INSTDIR\\{{this}}"`、836行是`RMDir "$INSTDIR"`；本记录不把`/REBOOTOK`单独解释成递归删除，实际`/r`位于898–899行的BUNDLEID用户数据复选框分支。无论该细节如何，程序与用户数据根分离的已批准要求不变，卸载逻辑一字不改。

VM-BUILD-Win11Clean.md已补两项：首次默认Programs路径的注册表/日志实证；卸载程序目录消失且SpectrumAgent下run/logs/testdata完整。未执行前安装/卸载都保持“待 VM 实机”。当前pristine只用f7ea81cf-6c3a-4823-9a7b-5fe77f4c2300。

## 有界观察补充

现有验收探针新增window.location.href和script.src，用于记录真实文档来源。只在SPECTRUM_ACCEPTANCE_PROBE=1时，在引擎清理完成后给已有100ms观察器留350ms关闭观察窗口，捕获Stopping对话条DOM；不阻塞UI、不延后引擎清理，普通启动无该延迟，不增加命令、权限、HTTP路径或依赖。30轮常规矩阵不启用探针；探针关闭观测与正常关闭计时分列。

旧exit70内部原因未验证，stderr1412继续观测；第2步VM待实机，不提前关闭。所有新输出写本目录，旧REPORT/manifest/验收输出不改写。
