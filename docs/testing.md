# 本地回归固定命令

在仓库根目录、已激活项目 Python 虚拟环境的正常 Windows 用户终端执行：

```powershell
python -m pytest -q --basetemp=.tmp-sample-suite
node --test --test-concurrency=1 tests/*.test.mjs
npm run build
```

`.tmp-sample-suite` 是专用测试临时目录，匹配仓库忽略规则；pytest 会管理并清空它，不可改成已有数据目录。固定短路径避免默认用户临时目录叠加测试名、模型和推理 UUID 以及原子写入临时文件名后触及 Windows 传统长路径限制。不能将这一类文件写入失败解释为模型数值回归。

后端测试还包含仅针对临时测试密钥的 DPAPI 往返，需要正常 Windows 用户上下文。项目数据、实际模型服务密钥和真实训练任务不参与测试。

源码测试与前端构建通过不等于已经重打包安装版；桌面交付仍需验证打包后的后端、前端及真实窗口行为。
