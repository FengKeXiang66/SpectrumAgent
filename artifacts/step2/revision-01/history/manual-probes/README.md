# 历史人工探针

历史人工复现脚本，会删除本机 %LOCALAPPDATA% 握手、taskkill /F、注入控制台信号、把 token 放在 curl 命令行；非规范验收入口，禁止在 CI 或正式回归中直接运行。

正式回归入口只有受版本控制的 artifacts/step2/lifecycle_regression.py 与 artifacts/step2/selfcheck_step2.ps1。
来源与原字节 SHA256 见上级 manual-probes-manifest.txt。同名不同内容必须追加时间戳或短 SHA，绝不覆盖旧文件。
