# SpectrumAgent Release Manifest

安装包二进制不进入 git 仓库（.gitignore 已排除），统一托管于夸克网盘；本文件是唯一权威的「版本 ↔ commit ↔ 安装包哈希 ↔ 归档位置」映射表。夸克分享保持提取码访问模式，不要改为完全公开。即便网盘链接失效，仓库内留存的 SHA256 与 commit 映射依然可用于版本溯源校验。

> **仓库可见性变更（2026-10-22）**：GitHub 仓库 `FengKeXiang66/SpectrumAgent` 已由私有改为**公开**（经公司允许）。公开前已完成敏感信息扫描：无硬编码密钥/token、无内部 IP 或 NAS 路径、无客户/实验数据（`.img/.hdr/.npy/.mat` 等均未入库）、git 历史中无已删除的敏感文件；仓库 pack 仅 3.65 MiB。**本条仅记录该事实，不改变上面关于夸克网盘提取码访问的要求**——两者是独立的分享渠道。

| Version | Commit SHA | Installer File | File Bytes | SHA256 | Archive Location |
|---|---|---|---|---|---|
| v0.1.3 | 9f6e253 | SpectrumAgent_0.1.3_x64-setup.exe | 297,284,045 | E97CBC68F731E703EEF42064F43E1525920AB7B359253D2C4E44E0B38EE45948 | 夸克网盘 [https://pan.quark.cn/s/d5c01c0a111c](https://pan.quark.cn/s/d5c01c0a111c) 提取码：eyBL |
| v0.1.2 |  | SpectrumAgent_0.1.2_x64-setup.exe（**未发布，已被 v0.1.3 取代，见下方说明**） | 待负责人复算 | 待负责人复算 | 未归档 |
| v0.1.1 | 29a4cdf | SpectrumAgent_0.1.1_x64-setup.exe | 287,410,501 | 93c717284866562b8986bd1ad06bdcdb11d0adeb0fa7b47bfcb1646fc21888e7 | 夸克网盘 [https://pan.quark.cn/s/11a84306ed1d](https://pan.quark.cn/s/11a84306ed1d) 提取码：3q9g |
| v0.1.0 | 205f0ad | setup.exe | 287,156,790 | d849253611c1ac985cb08a60a7073e17ed6c89b74e8230532d0c3d2157cc8107 | 夸克网盘 [https://pan.quark.cn/s/b0fc57fc4a75](https://pan.quark.cn/s/b0fc57fc4a75) 提取码：peHG |

## 版本说明

- **v0.1.3**（milestone 06 + 一次 P0 hotfix）：**S05 标注画布显示能力**（TASK-06）。画布底图不再固定 band 0 灰度，新增单波段可选 / 拉伸 auto(2/98 分位)|none / 手动伪彩 / 后端自动选三波段伪彩 / 前端 LUT 三滑块 / 点图取谱 / 框选区域均值谱。tag `v0.1.3` → commit **`9f6e253`**（已 force 重打，原指向 `c1e4942`）。安装包 **297,284,045 字节**，SHA256 `E97CBC68…594848`（已由负责人独立复算，非转录构建脚本自报值），冻结/捆绑冒烟均 passed，**未签名**（SmartScreen 会拦，属已知缓测项）。**重打原因（务必留痕）**：`c1e4942` 那次打包存在 **P0 缺陷——安装态标注画布报"后端 PNG 加载失败（base 图层）"**。根因是 `tauri.conf.json` 的 CSP 无显式 `img-src`，fallback 到 `default-src 'self'`，而 `'self'` 不含 `data:`，导致 `img.src="data:image/png;base64,..."` 被拦；dev 态不复发是因为 CSP 只对 `tauri://` 自定义协议注入，dev 走 `http://127.0.0.1:1420`。修复为 csp 插入 `img-src 'self' data:; `（`audit_boundary.py` 同步深层豁免 + 双向反证）。网盘归档：[夸克网盘](https://pan.quark.cn/s/d5c01c0a111c) 提取码 `eyBL`（符合维护规则第 3 条）。
- **v0.1.2**（milestone 04+05，**版本号未随功能升级，属历史遗留，已被 v0.1.3 取代**）：含 L1 人工标注工作台、候选区域、版本快照与样本谱聚合（#04）+ 光谱预处理 B 域线性算子链与对比引擎（#05）。原计划 tag v0.1.2，但期间构建过三个 0.1.2 安装包（对应 commit `bfa19958` 与 `a052b335`），且未打 tag；TASK-06 功能另行升版为 **v0.1.3**，故本行不再归档。相关验收证据见 `milestone04/evidence/10.7/` 与 `milestone05/evidence/11.7/`。
- **v0.1.1**（milestone 02+03）：数据接入 + release 打包。新增 ENVI/纯二进制读取、目录原子导入、波段/区域预览；release 开放受限 datasets IPC；引擎冻结尾像含 spectrumagent 组合入口。tag `v0.1.1` → commit `29a4cdf`。
- **v0.1.0**（milestone 01）：基础演示封版，核心框架定型。tag `v0.1.0` → commit `205f0ad`。

## 维护规则（每个里程碑过闸后执行）

1. 里程碑过闸后：`git tag -a vX.Y.Z <封账/过闸commit>` 并 `git push origin vX.Y.Z`；
2. GitHub Release 页面对应发布，描述引用本表条目（安装包走网盘链接，不上传资产）；
3. 安装包上传网盘后，将「版本 / commit / 文件名 / 字节数 / SHA256 / 网盘链接+提取码」追加一行到本文件；
4. 本文件的提交随该里程碑的收尾提交一并推送；
5. 安装包哈希以负责人独立复算为准，不从构建方自报转录。
