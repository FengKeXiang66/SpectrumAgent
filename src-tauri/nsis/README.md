# NSIS 固定模板

`installer.nsi` 来自已安装的 @tauri-apps/cli-win32-x64-msvc 2.12.3 原生二进制内嵌模板，完整原件和提取边界/二进制 SHA/模板 SHA 见 `artifacts/step3/checkpoint-4/release-custom-protocol-20261018/template-provenance.json`。网络 GET 失败记录保留；未以关闭证书验证绕过。

仅第524行改变：currentUser 默认 `$LOCALAPPDATA\${PRODUCTNAME}` 改为 `$LOCALAPPDATA\Programs\${PRODUCTNAME}`。509行的 PLACEHOLDER_INSTALL_DIR 守卫、perMachine 分支及卸载段逐字节保持。`/D=` 的命令行优先机制保留，实际安装结果仍须验收。bundle.windows.nsis.template 指向本文件；installMode 仍 currentUser，无需管理员，不采用 installerHooks（原模板 SetOutPath 在 PREINSTALL 之前）。

程序目录按只读对待；Rust 的数据根仍 `%LOCALAPPDATA%\SpectrumAgent`，没有改为 Programs。卸载后数据完整性、首次默认目录两项必须在干净 VM 取证；未执行前保持“待 VM 实机”。

CLI 升级纪律：重新提取新 CLI 的内嵌上游模板 → 重新算 SHA256 → 重新做完整字节 diff → 仅重新应用同一处 currentUser 默认目录修改。禁止凭记忆编辑或沿用旧模板；如上游结构改变，先报告再决定，不自动扩大修改范围。
