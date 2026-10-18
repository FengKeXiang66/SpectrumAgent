## 完成到哪一步

检查点 2 已由负责人复核通过。已完成本轮授权的 Windows 握手路径显示修复及针对性回归，并提交前端/Tauri 工具链审批方案；此处停下等待安装授权，尚未开始四态 UI 实现。

详细版本、理由、命令、缓存路径、lock 纪律及固定 run_smoke 范围申请见 [TOOLCHAIN-PROPOSAL.md](/E:/AI_Agent/artifacts/step3/checkpoint-3/TOOLCHAIN-PROPOSAL.md)。完整拟用前端 manifest 见 package.proposed.json。正式 package.json 尚不存在；Cargo.toml/Cargo.lock、Python requirements-lock.txt 均未修改，没有安装任何包。

## 命令与原始输出

生产代码仅将 supervisor 的三处 `join("run/handshake.json")` 改为 `join("run").join("handshake.json")`，用于诊断路径、启动前读取和轮询读取。目录、文件名、字段、身份判定及生命周期均不变；不动封版后端或冻结产物。

针对性回归加强既有不存在 exe 用例：断言失败对象的握手路径以原生 `run\handshake.json` 结束且显示字符串无 `/`；同时保留原有 SpawnFailed/code=2/立即失败/非法握手原字节不变断言。现有用例总数不增加，本轮只重跑这一项，不把上轮 20 项结果冒称本轮新跑全量。

```powershell
$env:CARGO_HOME='E:\AI_Agent\.cargo-home'
$env:CARGO_TARGET_DIR='E:\AI_Agent\src-tauri\target'
$env:TEMP='E:\AI_Agent\artifacts\step3\checkpoint-3\temp'
$env:TMP=$env:TEMP
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' test --manifest-path src-tauri/Cargo.toml --locked --offline --all-features --test supervisor_stubs absent_executable_immediately_fails_and_does_not_clean_invalid_old_handshake -- --exact --nocapture
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' clippy --manifest-path src-tauri/Cargo.toml --locked --offline --all-targets --all-features -- -D warnings
```

最终针对性回归 exit=0，1 passed/0 failed；clippy exit=0，无 warning。完整原始输出附后，未删节。

Node/npm 实测来源是项目固定路径的现有二进制/CLI，未运行安装：PATH 为 20.18.0/10.8.2，应用自带 Node 为 24.19.0；24.19.0 驱动已有 npm CLI 返回 10.8.2。Node 二进制 SHA256 已记录。只读核验 WebView2 注册表、BuildTools 路径及 rustc/cargo 版本；未安装系统组件。

官方 npm/crates 元数据通过只读 HTTPS GET 获取，不下载归档包。所选 10 个 npm 与 4 个 crate 均取得了实际版本/engines/peer/MSRV/features；compatibility-matrix.json 用已有 npm 自带 semver 做了判定。Vite 8.3.4 的 Node 约束排除 PATH 20.18.0、包含 24.19.0；所选必需 peer/类型约束全部满足。Tauri/Vite/tsc 实际整套构建仍未验证，等安装批准后执行。

## 遇到的问题

1. 首轮新回归 0 passed/1 failed：`assertion failed: !displayed_path.contains('/')`。既有夹具用 `target/stub-runtime` 字符串建立根路径，因此全路径断言也查到了夹具旧分隔符。将该用例的夹具根按 Windows Path components 重新构造，保留完整断言；第二轮 1 passed。首轮原文保存在 path-regression-output.txt，未改写。
2. Python urllib 元数据探针报 `[SSL: UNEXPECTED_EOF_WHILE_READING]`；系统 curl 的默认撤销校验报 `CRYPT_E_REVOCATION_OFFLINE (0x80092013)`。随后仅对官方元数据读取使用系统 curl 的 `--ssl-revoke-best-effort`，保留服务器证书验证，成功取得 JSON。没有改系统或 npm TLS 配置。首轮 Python 完整报错见 registry-probe-output.txt，成功输出见 registry-probe-fixed-output.txt。
3. 所选 CLI 尚未安装，本地 add --help 的实际参数未验证；按 CLI 的 gitHead 读取官方 add.rs 源码也在 20 秒后超时。未据记忆编造插件精确版本参数，方案明确该处待本地帮助核对，并保留任务卡的官方 single-instance 接入命令。不能在精确审批版本外浮动下载直接依赖。

以上没有改变接口契约。现有 reqwest 仍只请求 /health；固定 /smoke 扩围已明列为审批项，没有实施。旧 exit code=70 的内部原因继续“未验证”；本轮路径断言失败是验收测试失败，不是引擎 code=70 证据。

第 2 步继续“待实机验证”。20 项验收状态继续以检查点 2 已复核表为准；本轮只补路径显示的代码/回归证据，没有把 Tauri Resource resolver、--no-bundle、FaultFixture/Canonical 双模式、UI 或最终强杀矩阵写成已通过。

## 下一步打算

等待负责人批准工具链/依赖清单及固定本机 /smoke 范围；获批后按方案安装归档两份 lock，再按序实现四态 UI、中文失败页与常驻对话条，完成下一检查点自检后停下汇报。

以下为本轮原始输出。


**路径针对性回归（最终）**

```text
cargo test --manifest-path src-tauri/Cargo.toml --locked --offline --all-features --test supervisor_stubs absent_executable_immediately_fails_and_does_not_clean_invalid_old_handshake -- --exact --nocapture

   Compiling spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
    Finished `test` profile [unoptimized + debuginfo] target(s) in 0.83s
     Running tests\supervisor_stubs.rs (src-tauri\target\debug\deps\supervisor_stubs-f1904bb8bb35a89b.exe)

running 1 test
FAILURE DISPLAY handshake_path=E:\AI_Agent\src-tauri\target\stub-runtime\19148-1792312104237-1\run\handshake.json
MISSING PATH (constructor injection): kind=SpawnFailed elapsed_ms=11 preexisting_handshake_invalid=retained bytes_unchanged=true
test absent_executable_immediately_fails_and_does_not_clean_invalid_old_handshake ... ok

test result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 7 filtered out; finished in 0.01s


```


**clippy**

```text
cargo clippy --manifest-path src-tauri/Cargo.toml --locked --offline --all-targets --all-features -- -D warnings

    Checking spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 0.70s

```


**fmt 执行元数据**

```text
cargo fmt --manifest-path src-tauri/Cargo.toml --check

{
  "command": "cargo fmt --manifest-path src-tauri/Cargo.toml --check",
  "exit_code": 0,
  "output": []
}

```


**现有 Node/npm 只读探针**

```text
explicit Node 24.19.0 + existing npm-cli.js --version; Get-FileHash; npm package engines

READ ONLY: explicit Node 24 + existing npm CLI --version; no install
v24.19.0

10.8.2


Algorithm : SHA256
Hash      : 3602F2BB1A10F2CBAB4C36886218A33C1AB3DB87290E73B033C46C77147D0237
Path      : C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe


npm package engines.node:
^18.17.0 || >=20.5.0

```


**注册表成功探针**

```text
E:\AI_Agent\.venv\Scripts\python.exe artifacts/step3/checkpoint-3/probe_registry.py

{"ecosystem": "npm", "name": "react", "url": "https://registry.npmjs.org/react/latest", "version": "19.3.1", "engines": {"node": ">=0.10.0"}, "peerDependencies": null, "peerDependenciesMeta": null, "dependencies": null, "optionalDependencies": null}
{"ecosystem": "npm", "name": "react-dom", "url": "https://registry.npmjs.org/react-dom/latest", "version": "19.3.1", "engines": null, "peerDependencies": {"react": "^19.3.1"}, "peerDependenciesMeta": null, "dependencies": {"scheduler": "^0.28.0"}, "optionalDependencies": null}
{"ecosystem": "npm", "name": "@tauri-apps/api", "url": "https://registry.npmjs.org/%40tauri-apps%2Fapi/latest", "version": "2.12.4", "engines": null, "peerDependencies": null, "peerDependenciesMeta": null, "dependencies": null, "optionalDependencies": null}
{"ecosystem": "npm", "name": "vite", "url": "https://registry.npmjs.org/vite/latest", "version": "8.3.4", "engines": {"node": "^20.19.0 || >=22.12.0"}, "peerDependencies": {"tsx": "^4.8.1", "jiti": ">=1.21.0", "less": "^4.0.0", "sass": "^1.70.0", "yaml": "^2.4.2", "stylus": ">=0.54.8", "terser": "^5.16.0", "esbuild": "^0.27.0 || ^0.28.0", "sugarss": "^5.0.0", "@types/node": "^20.19.0 || >=22.12.0", "sass-embedded": "^1.70.0", "@vitejs/devtools": "^0.7.1"}, "peerDependenciesMeta": {"tsx": {"optional": true}, "jiti": {"optional": true}, "less": {"optional": true}, "sass": {"optional": true}, "yaml": {"optional": true}, "stylus": {"optional": true}, "terser": {"optional": true}, "esbuild": {"optional": true}, "sugarss": {"optional": true}, "@types/node": {"optional": true}, "sass-embedded": {"optional": true}, "@vitejs/devtools": {"optional": true}}, "dependencies": {"postcss": "^8.5.29", "rolldown": "~1.2.12", "picomatch": "^4.0.7", "tinyglobby": "^0.2.17", "lightningcss": "^1.33.0"}, "optionalDependencies": {"fsevents": "~2.3.3"}}
{"ecosystem": "npm", "name": "typescript", "url": "https://registry.npmjs.org/typescript/5.9.3", "version": "5.9.3", "engines": {"node": ">=14.17"}, "peerDependencies": null, "peerDependenciesMeta": null, "dependencies": null, "optionalDependencies": null}
{"ecosystem": "npm", "name": "@vitejs/plugin-react", "url": "https://registry.npmjs.org/%40vitejs%2Fplugin-react/latest", "version": "6.1.2", "engines": {"node": "^20.19.0 || >=22.12.0"}, "peerDependencies": {"vite": "^8.0.0", "oxc-transform-react": "^0.152.0", "@rolldown/plugin-babel": "^0.1.7 || ^0.2.0", "babel-plugin-react-compiler": "^1.0.0"}, "peerDependenciesMeta": {"oxc-transform-react": {"optional": true}, "@rolldown/plugin-babel": {"optional": true}, "babel-plugin-react-compiler": {"optional": true}}, "dependencies": {"@rolldown/pluginutils": "^1.0.1"}, "optionalDependencies": null}
{"ecosystem": "npm", "name": "@types/react", "url": "https://registry.npmjs.org/%40types%2Freact/latest", "version": "19.3.0", "engines": null, "peerDependencies": {}, "peerDependenciesMeta": null, "dependencies": {"csstype": "^3.2.2"}, "optionalDependencies": null}
{"ecosystem": "npm", "name": "@types/react-dom", "url": "https://registry.npmjs.org/%40types%2Freact-dom/latest", "version": "19.3.0", "engines": null, "peerDependencies": {"@types/react": "^19.3.0"}, "peerDependenciesMeta": null, "dependencies": {}, "optionalDependencies": null}
{"ecosystem": "npm", "name": "@types/node", "url": "https://registry.npmjs.org/%40types%2Fnode/24.10.1", "version": "24.10.1", "engines": null, "peerDependencies": {}, "peerDependenciesMeta": null, "dependencies": {"undici-types": "~7.16.0"}, "optionalDependencies": null}
{"ecosystem": "npm", "name": "@tauri-apps/cli", "url": "https://registry.npmjs.org/%40tauri-apps%2Fcli/latest", "version": "2.12.3", "engines": {"node": ">= 10"}, "peerDependencies": null, "peerDependenciesMeta": null, "dependencies": null, "optionalDependencies": {"@tauri-apps/cli-darwin-x64": "2.12.3", "@tauri-apps/cli-darwin-arm64": "2.12.3", "@tauri-apps/cli-linux-x64-gnu": "2.12.3", "@tauri-apps/cli-linux-x64-musl": "2.12.3", "@tauri-apps/cli-win32-x64-msvc": "2.12.3", "@tauri-apps/cli-linux-arm64-gnu": "2.12.3", "@tauri-apps/cli-win32-ia32-msvc": "2.12.3", "@tauri-apps/cli-linux-arm64-musl": "2.12.3", "@tauri-apps/cli-win32-arm64-msvc": "2.12.3", "@tauri-apps/cli-linux-riscv64-gnu": "2.12.3", "@tauri-apps/cli-linux-arm-gnueabihf": "2.12.3"}}
{"ecosystem": "cargo", "name": "tauri", "url": "https://crates.io/api/v1/crates/tauri/2.12.4", "version": "2.12.4", "rust_version": "1.90"}
{"ecosystem": "cargo", "name": "tauri-build", "url": "https://crates.io/api/v1/crates/tauri-build/2.7.3", "version": "2.7.3", "rust_version": "1.90"}
{"ecosystem": "cargo", "name": "tauri-plugin-single-instance", "url": "https://crates.io/api/v1/crates/tauri-plugin-single-instance/2.5.4", "version": "2.5.4", "rust_version": "1.90"}
{"ecosystem": "cargo", "name": "tauri-plugin-opener", "url": "https://crates.io/api/v1/crates/tauri-plugin-opener/2.7.2", "version": "2.7.2", "rust_version": "1.90"}
metadata_file=E:\AI_Agent\artifacts\step3\checkpoint-3\registry-metadata-20261018-163332-870623.json

```


**兼容性矩阵**

```text
explicit Node 24.19.0 check_compatibility.cjs registry-metadata-20261018-163332-870623.json

{
  "node": "v24.19.0",
  "platform": "win32",
  "arch": "x64",
  "PATH_Node_20_18_0_satisfies_vite": false,
  "rows": [
    {
      "package": "react",
      "kind": "node-engine",
      "required": ">=0.10.0",
      "actual": "24.19.0",
      "passed": true
    },
    {
      "package": "react-dom",
      "kind": "peer",
      "peer": "react",
      "required": "^19.3.1",
      "actual": "19.3.1",
      "optional": false,
      "passed": true
    },
    {
      "package": "vite",
      "kind": "node-engine",
      "required": "^20.19.0 || >=22.12.0",
      "actual": "24.19.0",
      "passed": true
    },
    {
      "package": "vite",
      "kind": "peer",
      "peer": "tsx",
      "required": "^4.8.1",
      "actual": null,
      "optional": true,
      "passed": true
    },
    {
      "package": "vite",
      "kind": "peer",
      "peer": "jiti",
      "required": ">=1.21.0",
      "actual": null,
      "optional": true,
      "passed": true
    },
    {
      "package": "vite",
      "kind": "peer",
      "peer": "less",
      "required": "^4.0.0",
      "actual": null,
      "optional": true,
      "passed": true
    },
    {
      "package": "vite",
      "kind": "peer",
      "peer": "sass",
      "required": "^1.70.0",
      "actual": null,
      "optional": true,
      "passed": true
    },
    {
      "package": "vite",
      "kind": "peer",
      "peer": "yaml",
      "required": "^2.4.2",
      "actual": null,
      "optional": true,
      "passed": true
    },
    {
      "package": "vite",
      "kind": "peer",
      "peer": "stylus",
      "required": ">=0.54.8",
      "actual": null,
      "optional": true,
      "passed": true
    },
    {
      "package": "vite",
      "kind": "peer",
      "peer": "terser",
      "required": "^5.16.0",
      "actual": null,
      "optional": true,
      "passed": true
    },
    {
      "package": "vite",
      "kind": "peer",
      "peer": "esbuild",
      "required": "^0.27.0 || ^0.28.0",
      "actual": null,
      "optional": true,
      "passed": true
    },
    {
      "package": "vite",
      "kind": "peer",
      "peer": "sugarss",
      "required": "^5.0.0",
      "actual": null,
      "optional": true,
      "passed": true
    },
    {
      "package": "vite",
      "kind": "peer",
      "peer": "@types/node",
      "required": "^20.19.0 || >=22.12.0",
      "actual": "24.10.1",
      "optional": true,
      "passed": true
    },
    {
      "package": "vite",
      "kind": "peer",
      "peer": "sass-embedded",
      "required": "^1.70.0",
      "actual": null,
      "optional": true,
      "passed": true
    },
    {
      "package": "vite",
      "kind": "peer",
      "peer": "@vitejs/devtools",
      "required": "^0.7.1",
      "actual": null,
      "optional": true,
      "passed": true
    },
    {
      "package": "typescript",
      "kind": "node-engine",
      "required": ">=14.17",
      "actual": "24.19.0",
      "passed": true
    },
    {
      "package": "@vitejs/plugin-react",
      "kind": "node-engine",
      "required": "^20.19.0 || >=22.12.0",
      "actual": "24.19.0",
      "passed": true
    },
    {
      "package": "@vitejs/plugin-react",
      "kind": "peer",
      "peer": "vite",
      "required": "^8.0.0",
      "actual": "8.3.4",
      "optional": false,
      "passed": true
    },
    {
      "package": "@vitejs/plugin-react",
      "kind": "peer",
      "peer": "oxc-transform-react",
      "required": "^0.152.0",
      "actual": null,
      "optional": true,
      "passed": true
    },
    {
      "package": "@vitejs/plugin-react",
      "kind": "peer",
      "peer": "@rolldown/plugin-babel",
      "required": "^0.1.7 || ^0.2.0",
      "actual": null,
      "optional": true,
      "passed": true
    },
    {
      "package": "@vitejs/plugin-react",
      "kind": "peer",
      "peer": "babel-plugin-react-compiler",
      "required": "^1.0.0",
      "actual": null,
      "optional": true,
      "passed": true
    },
    {
      "package": "@types/react",
      "kind": "minimum-typescript",
      "required": "5.6",
      "actual": "5.9.3",
      "passed": true
    },
    {
      "package": "@types/react-dom",
      "kind": "peer",
      "peer": "@types/react",
      "required": "^19.3.0",
      "actual": "19.3.0",
      "optional": false,
      "passed": true
    },
    {
      "package": "@types/react-dom",
      "kind": "minimum-typescript",
      "required": "5.6",
      "actual": "5.9.3",
      "passed": true
    },
    {
      "package": "@types/node",
      "kind": "minimum-typescript",
      "required": "5.2",
      "actual": "5.9.3",
      "passed": true
    },
    {
      "package": "@tauri-apps/cli",
      "kind": "node-engine",
      "required": ">= 10",
      "actual": "24.19.0",
      "passed": true
    },
    {
      "package": "npm",
      "kind": "node-engine",
      "version": "10.8.2",
      "required": "^18.17.0 || >=20.5.0",
      "actual": "24.19.0",
      "passed": true
    }
  ]
}

```


**跨 crate 依赖元数据**

```text
read-only metadata GET /api/v1/crates/<name>/<version>/dependencies

{"name": "@types/react", "typeScriptVersion": "5.6", "typesVersions": {"<=5.0": {"*": ["ts5.0/*"]}}}
{"name": "@types/react-dom", "typeScriptVersion": "5.6", "typesVersions": null}
{"name": "@types/node", "typeScriptVersion": "5.2", "typesVersions": {"<=5.6": {"*": ["ts5.6/*"]}, "<=5.7": {"*": ["ts5.7/*"]}}}
{"name": "tauri", "relevant_dependencies": [{"id": 39717791, "version_id": 3496724, "crate_id": "reqwest", "req": "^0.13", "optional": false, "default_features": false, "features": ["json", "stream"], "target": "cfg(any(target_os = \"android\", all(target_vendor = \"apple\", not(target_os = \"macos\"))))", "kind": "normal", "downloads": 0}, {"id": 39717785, "version_id": 3496724, "crate_id": "tauri-build", "req": "^2.7.3", "optional": false, "default_features": false, "features": [], "target": null, "kind": "build", "downloads": 0}, {"id": 39717769, "version_id": 3496724, "crate_id": "tauri-utils", "req": "~2.10.2", "optional": false, "default_features": true, "features": ["resources"], "target": null, "kind": "normal", "downloads": 0}, {"id": 39717786, "version_id": 3496724, "crate_id": "tauri-utils", "req": "~2.10.2", "optional": false, "default_features": true, "features": ["build-2"], "target": null, "kind": "build", "downloads": 0}]}
{"name": "tauri-build", "relevant_dependencies": [{"id": 39717708, "version_id": 3496720, "crate_id": "tauri-utils", "req": "~2.10.2", "optional": false, "default_features": true, "features": ["build-2", "resources"], "target": null, "kind": "normal", "downloads": 0}]}
{"name": "tauri-plugin-single-instance", "relevant_dependencies": [{"id": 39720508, "version_id": 3496919, "crate_id": "tauri", "req": "^2.12", "optional": false, "default_features": false, "features": [], "target": null, "kind": "normal", "downloads": 0}, {"id": 39720513, "version_id": 3496919, "crate_id": "tauri", "req": "^2.12", "optional": false, "default_features": false, "features": ["test"], "target": null, "kind": "dev", "downloads": 0}]}
{"name": "tauri-plugin-opener", "relevant_dependencies": [{"id": 39720386, "version_id": 3496909, "crate_id": "tauri", "req": "^2.12", "optional": false, "default_features": false, "features": ["wry"], "target": "cfg(target_os = \"ios\")", "kind": "normal", "downloads": 0}, {"id": 39720380, "version_id": 3496909, "crate_id": "tauri", "req": "^2.12", "optional": false, "default_features": false, "features": ["wry"], "target": null, "kind": "dev", "downloads": 0}, {"id": 39720378, "version_id": 3496909, "crate_id": "tauri", "req": "^2.12", "optional": false, "default_features": false, "features": [], "target": null, "kind": "normal", "downloads": 0}, {"id": 39720383, "version_id": 3496909, "crate_id": "tauri-plugin", "req": "^2.7.1", "optional": false, "default_features": true, "features": ["build"], "target": null, "kind": "build", "downloads": 0}]}

```


**现有 Windows 组件及 Rust 工具链**

```text
rustc --version; cargo --version; Get-ItemProperty WebView2; vswhere -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath

rustc 1.99.1 (58cf8f9c3 2026-10-13)

cargo 1.99.1 (5f94df478 2026-08-27)

{
  "path": "HKEY_LOCAL_MACHINE\\SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
  "name": "Microsoft Edge WebView2 Runtime",
  "version": "155.0.4283.62"
}
C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools


```
