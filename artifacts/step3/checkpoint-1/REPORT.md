# 第 3 步检查点 1：Rust 监督器与测试（2026-10-18）

## 完成到哪一步

完成 EngineSupervisor 核心、Win32 生产实现与可注入替身、严格握手解析、四态/代次保护、只读日志归属和确定性子进程 stub。本检查点仅验证 Rust 库与测试进程，尚未接真实冻结引擎，尚无 Tauri 宿主/React 页面；本报告不作为 release 外壳验收结论。

第 2 步项 1/3/4/5/7 引用原有结果，未重跑或改写旧输出。按负责人本轮授权进入第 3 步，第 2 步仍保留“待实机验证”及未正式关闭状态。执行依据和已有提交索引见 ../preflight/HANDOFF.md。

本检查点结果：fmt --check 通过；clippy 全目标/全功能且 -D warnings 通过；18 项测试通过（日志归属 2、契约/状态 6、原生子进程 stub 7、注入清理 3）。测试后按完整路径查询 supervisor-stub.exe，残留 0。

首次 src-tauri 提交包含 Cargo.lock。直接依赖为获批准的 5 项，lock 含 103 个第三方包及项目本身（metadata 共 104）；transitive 不是额外手动选型。Cargo.lock=25,117 字节，SHA256=24a4beb3d9a41b6b483da938dc00d28ebd04c7fa2208d0626e863104b07dc51d。

## 命令与原始输出

实际生效路径：CARGO_HOME=E:\AI_Agent\.cargo-home；CARGO_TARGET_DIR=E:\AI_Agent\src-tauri\target。cargo metadata 的 target_directory 与之相同。TEMP/TMP 也显式落 E:\AI_Agent\artifacts\step3\checkpoint-1\temp。只读探针确认默认 C:\Users\Administrator\.cargo\registry 不存在。

已按负责人批准执行的下载命令与首次输出保存在 fetch-output.txt；完整依赖树为 cargo-tree.txt。reqwest 实际功能仅 blocking/json，无默认 TLS；源码唯一请求入口固定为 127.0.0.1 的 /health，无代理、无重定向，没有 /smoke 或外网请求。

本次正式检查的完整命令：

```powershell
$env:CARGO_HOME = 'E:\AI_Agent\.cargo-home'
$env:CARGO_TARGET_DIR = 'E:\AI_Agent\src-tauri\target'
$env:TEMP = 'E:\AI_Agent\artifacts\step3\checkpoint-1\temp'
$env:TMP = $env:TEMP
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' fmt --manifest-path 'E:\AI_Agent\src-tauri\Cargo.toml' --check
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' clippy --manifest-path 'E:\AI_Agent\src-tauri\Cargo.toml' --all-targets --all-features --locked --offline -- -D warnings
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' test --manifest-path 'E:\AI_Agent\src-tauri\Cargo.toml' --all-features --locked --offline -- --nocapture --test-threads=1
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' tree --manifest-path 'E:\AI_Agent\src-tauri\Cargo.toml' --all-features --locked --offline
```

以下完整粘贴 checks-final-output.txt；其中注入测试的调用参数与关闭顺序、退出码、毫秒数均为原始输出：

```text
**********************
PowerShell transcript start
Start time: 20261018151500
Username: WIN-RTKE72PB5BE\CodexSandboxOffline
RunAs User: WIN-RTKE72PB5BE\CodexSandboxOffline
Configuration Name: 
Machine: WIN-RTKE72PB5BE (Microsoft Windows NT 10.0.26100.0)
Host Application: C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.dll -NoProfile -Command try { [Console]::OutputEncoding=[System.Text.Encoding]::UTF8 } catch {}
$ErrorActionPreference = 'Stop'
$env:CARGO_HOME = 'E:\AI_Agent\.cargo-home'
$env:CARGO_TARGET_DIR = 'E:\AI_Agent\src-tauri\target'
$env:TEMP = 'E:\AI_Agent\artifacts\step3\checkpoint-1\temp'
$env:TMP = $env:TEMP
& 'C:\Users\Administrator\.cargo\bin\cargo.exe' fmt --manifest-path 'E:\AI_Agent\src-tauri\Cargo.toml'
Start-Transcript -Path 'E:\AI_Agent\artifacts\step3\checkpoint-1\checks-final-output.txt' | Out-Host
try {
  Get-Item -LiteralPath Env:CARGO_HOME,Env:CARGO_TARGET_DIR,Env:TEMP,Env:TMP | Format-List Name,Value
  'COMMAND: cargo fmt --check'
  & 'C:\Users\Administrator\.cargo\bin\cargo.exe' fmt --manifest-path 'E:\AI_Agent\src-tauri\Cargo.toml' --check
  if ($LASTEXITCODE -ne 0) { throw 'cargo fmt --check failed' }
  'COMMAND: cargo clippy --all-targets --all-features --locked --offline -- -D warnings'
  & 'C:\Users\Administrator\.cargo\bin\cargo.exe' clippy --manifest-path 'E:\AI_Agent\src-tauri\Cargo.toml' --all-targets --all-features --locked --offline -- -D warnings
  if ($LASTEXITCODE -ne 0) { throw 'cargo clippy failed' }
  'COMMAND: cargo test --all-features --locked --offline -- --nocapture --test-threads=1'
  & 'C:\Users\Administrator\.cargo\bin\cargo.exe' test --manifest-path 'E:\AI_Agent\src-tauri\Cargo.toml' --all-features --locked --offline -- --nocapture --test-threads=1
  if ($LASTEXITCODE -ne 0) { throw 'cargo test failed' }
  'COMMAND: cargo tree --all-features --locked --offline --edges features -i reqwest'
  & 'C:\Users\Administrator\.cargo\bin\cargo.exe' tree --manifest-path 'E:\AI_Agent\src-tauri\Cargo.toml' --all-features --locked --offline --edges features -i reqwest
  if ($LASTEXITCODE -ne 0) { throw 'reqwest feature tree failed' }
} finally { Stop-Transcript | Out-Host }
Process ID: 20104
PSVersion: 7.6.5
PSEdition: Core
GitCommitId: 7.6.5
OS: Microsoft Windows 10.0.26100
Platform: Win32NT
PSCompatibleVersions: 1.0, 2.0, 3.0, 4.0, 5.0, 5.1, 6.0, 7.0
PSRemotingProtocolVersion: 2.4
SerializationVersion: 1.1.0.1
WSManStackVersion: 3.0
**********************
Transcript started, output file is E:\AI_Agent\artifacts\step3\checkpoint-1\checks-final-output.txt

Name  : CARGO_HOME
Value : E:\AI_Agent\.cargo-home

Name  : CARGO_TARGET_DIR
Value : E:\AI_Agent\src-tauri\target

Name  : TEMP
Value : E:\AI_Agent\artifacts\step3\checkpoint-1\temp

Name  : TMP
Value : E:\AI_Agent\artifacts\step3\checkpoint-1\temp

COMMAND: cargo fmt --check

COMMAND: cargo clippy --all-targets --all-features --locked --offline -- -D warnings

COMMAND: cargo test --all-features --locked --offline -- --nocapture --test-threads=1

COMMAND: cargo tree --all-features --locked --offline --edges features -i reqwest

**********************
PowerShell transcript end
End time: 20261018151536
**********************

```

实际依赖树全文（cargo-tree.txt）：

```text
spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
├── chrono v0.4.45
│   ├── num-traits v0.2.19
│   │   [build-dependencies]
│   │   └── autocfg v1.5.1
│   └── windows-link v0.2.1
├── reqwest v0.13.5
│   ├── base64 v0.23.1
│   ├── bytes v1.12.1
│   ├── futures-channel v0.3.34
│   │   ├── futures-core v0.3.34
│   │   └── futures-sink v0.3.34
│   ├── futures-core v0.3.34
│   ├── futures-util v0.3.34
│   │   ├── futures-core v0.3.34
│   │   ├── futures-io v0.3.34
│   │   ├── futures-sink v0.3.34
│   │   ├── futures-task v0.3.34
│   │   ├── memchr v2.8.3
│   │   ├── pin-project-lite v0.2.17
│   │   └── slab v0.4.12
│   ├── http v1.5.0
│   │   ├── bytes v1.12.1
│   │   └── itoa v1.0.18
│   ├── http-body v1.1.0
│   │   ├── bytes v1.12.1
│   │   └── http v1.5.0 (*)
│   ├── http-body-util v0.1.5
│   │   ├── bytes v1.12.1
│   │   ├── futures-core v0.3.34
│   │   ├── http v1.5.0 (*)
│   │   ├── http-body v1.1.0 (*)
│   │   └── pin-project-lite v0.2.17
│   ├── hyper v1.12.0
│   │   ├── atomic-waker v1.1.2
│   │   ├── bytes v1.12.1
│   │   ├── futures-core v0.3.34
│   │   ├── http v1.5.0 (*)
│   │   ├── http-body v1.1.0 (*)
│   │   ├── httparse v1.10.1
│   │   ├── itoa v1.0.18
│   │   ├── pin-project-lite v0.2.17
│   │   ├── smallvec v1.16.3
│   │   ├── tokio v1.53.3
│   │   │   ├── mio v1.2.4
│   │   │   │   └── windows-sys v0.61.2
│   │   │   │       └── windows-link v0.2.1
│   │   │   ├── pin-project-lite v0.2.17
│   │   │   ├── socket2 v0.6.5
│   │   │   │   └── windows-sys v0.61.2 (*)
│   │   │   └── windows-sys v0.61.2 (*)
│   │   └── want v0.3.2
│   │       └── try-lock v0.2.5
│   ├── hyper-util v0.1.21
│   │   ├── base64 v0.23.1
│   │   ├── bytes v1.12.1
│   │   ├── futures-channel v0.3.34 (*)
│   │   ├── futures-util v0.3.34 (*)
│   │   ├── http v1.5.0 (*)
│   │   ├── http-body v1.1.0 (*)
│   │   ├── httparse v1.10.1
│   │   ├── hyper v1.12.0 (*)
│   │   ├── ipnet v2.12.2
│   │   ├── libc v0.2.191
│   │   ├── percent-encoding v2.3.2
│   │   ├── pin-project-lite v0.2.17
│   │   ├── socket2 v0.6.5 (*)
│   │   ├── tokio v1.53.3 (*)
│   │   ├── tower-service v0.3.3
│   │   └── tracing v0.1.44
│   │       ├── pin-project-lite v0.2.17
│   │       └── tracing-core v0.1.36
│   │           └── once_cell v1.21.4
│   ├── log v0.4.34
│   ├── percent-encoding v2.3.2
│   ├── pin-project-lite v0.2.17
│   ├── serde v1.0.229
│   │   ├── serde_core v1.0.229
│   │   └── serde_derive v1.0.229 (proc-macro)
│   │       ├── proc-macro2 v1.0.107
│   │       │   └── unicode-ident v1.0.27
│   │       ├── quote v1.0.47
│   │       │   └── proc-macro2 v1.0.107 (*)
│   │       └── syn v3.0.9
│   │           ├── proc-macro2 v1.0.107 (*)
│   │           ├── quote v1.0.47 (*)
│   │           └── unicode-ident v1.0.27
│   ├── serde_json v1.0.154
│   │   ├── itoa v1.0.18
│   │   ├── memchr v2.8.3
│   │   ├── serde_core v1.0.229
│   │   └── zmij v1.0.23
│   ├── sync_wrapper v1.0.2
│   │   └── futures-core v0.3.34
│   ├── tokio v1.53.3 (*)
│   ├── tower v0.5.3
│   │   ├── futures-core v0.3.34
│   │   ├── futures-util v0.3.34 (*)
│   │   ├── pin-project-lite v0.2.17
│   │   ├── sync_wrapper v1.0.2 (*)
│   │   ├── tokio v1.53.3 (*)
│   │   ├── tower-layer v0.3.3
│   │   └── tower-service v0.3.3
│   ├── tower-http v0.6.11
│   │   ├── bitflags v2.13.2
│   │   ├── bytes v1.12.1
│   │   ├── futures-util v0.3.34 (*)
│   │   ├── http v1.5.0 (*)
│   │   ├── http-body v1.1.0 (*)
│   │   ├── pin-project-lite v0.2.17
│   │   ├── tower v0.5.3 (*)
│   │   ├── tower-layer v0.3.3
│   │   ├── tower-service v0.3.3
│   │   └── url v2.5.8
│   │       ├── form_urlencoded v1.2.2
│   │       │   └── percent-encoding v2.3.2
│   │       ├── idna v1.1.0
│   │       │   ├── idna_adapter v1.2.2
│   │       │   │   ├── icu_normalizer v2.3.0
│   │       │   │   │   ├── icu_collections v2.3.0
│   │       │   │   │   │   ├── displaydoc v0.2.7 (proc-macro)
│   │       │   │   │   │   │   ├── proc-macro2 v1.0.107 (*)
│   │       │   │   │   │   │   ├── quote v1.0.47 (*)
│   │       │   │   │   │   │   └── syn v3.0.9 (*)
│   │       │   │   │   │   ├── potential_utf v0.1.6
│   │       │   │   │   │   │   └── zerovec v0.11.8
│   │       │   │   │   │   │       ├── yoke v0.8.3
│   │       │   │   │   │   │       │   ├── stable_deref_trait v1.2.1
│   │       │   │   │   │   │       │   ├── yoke-derive v0.8.4 (proc-macro)
│   │       │   │   │   │   │       │   │   ├── proc-macro2 v1.0.107 (*)
│   │       │   │   │   │   │       │   │   ├── quote v1.0.47 (*)
│   │       │   │   │   │   │       │   │   ├── syn v3.0.9 (*)
│   │       │   │   │   │   │       │   │   └── synstructure v0.14.0
│   │       │   │   │   │   │       │   │       ├── proc-macro2 v1.0.107 (*)
│   │       │   │   │   │   │       │   │       ├── quote v1.0.47 (*)
│   │       │   │   │   │   │       │   │       └── syn v3.0.9 (*)
│   │       │   │   │   │   │       │   └── zerofrom v0.1.8
│   │       │   │   │   │   │       │       └── zerofrom-derive v0.1.8 (proc-macro)
│   │       │   │   │   │   │       │           ├── proc-macro2 v1.0.107 (*)
│   │       │   │   │   │   │       │           ├── quote v1.0.47 (*)
│   │       │   │   │   │   │       │           ├── syn v3.0.9 (*)
│   │       │   │   │   │   │       │           └── synstructure v0.14.0 (*)
│   │       │   │   │   │   │       ├── zerofrom v0.1.8 (*)
│   │       │   │   │   │   │       └── zerovec-derive v0.11.6 (proc-macro)
│   │       │   │   │   │   │           ├── proc-macro2 v1.0.107 (*)
│   │       │   │   │   │   │           ├── quote v1.0.47 (*)
│   │       │   │   │   │   │           └── syn v3.0.9 (*)
│   │       │   │   │   │   ├── utf8_iter v1.0.4
│   │       │   │   │   │   ├── yoke v0.8.3 (*)
│   │       │   │   │   │   ├── zerofrom v0.1.8 (*)
│   │       │   │   │   │   └── zerovec v0.11.8 (*)
│   │       │   │   │   ├── icu_normalizer_data v2.3.0
│   │       │   │   │   ├── icu_provider v2.3.1
│   │       │   │   │   │   ├── displaydoc v0.2.7 (proc-macro) (*)
│   │       │   │   │   │   ├── icu_locale_core v2.3.0
│   │       │   │   │   │   │   ├── displaydoc v0.2.7 (proc-macro) (*)
│   │       │   │   │   │   │   ├── litemap v0.8.3
│   │       │   │   │   │   │   ├── tinystr v0.8.4
│   │       │   │   │   │   │   │   ├── displaydoc v0.2.7 (proc-macro) (*)
│   │       │   │   │   │   │   │   └── zerovec v0.11.8 (*)
│   │       │   │   │   │   │   ├── writeable v0.6.4
│   │       │   │   │   │   │   └── zerovec v0.11.8 (*)
│   │       │   │   │   │   ├── writeable v0.6.4
│   │       │   │   │   │   ├── yoke v0.8.3 (*)
│   │       │   │   │   │   ├── zerofrom v0.1.8 (*)
│   │       │   │   │   │   ├── zerotrie v0.2.5
│   │       │   │   │   │   │   ├── displaydoc v0.2.7 (proc-macro) (*)
│   │       │   │   │   │   │   ├── yoke v0.8.3 (*)
│   │       │   │   │   │   │   └── zerofrom v0.1.8 (*)
│   │       │   │   │   │   └── zerovec v0.11.8 (*)
│   │       │   │   │   ├── smallvec v1.16.3
│   │       │   │   │   └── zerovec v0.11.8 (*)
│   │       │   │   └── icu_properties v2.3.0
│   │       │   │       ├── displaydoc v0.2.7 (proc-macro) (*)
│   │       │   │       ├── icu_collections v2.3.0 (*)
│   │       │   │       ├── icu_locale_core v2.3.0 (*)
│   │       │   │       ├── icu_properties_data v2.3.0
│   │       │   │       ├── icu_provider v2.3.1 (*)
│   │       │   │       ├── zerotrie v0.2.5 (*)
│   │       │   │       └── zerovec v0.11.8 (*)
│   │       │   ├── smallvec v1.16.3
│   │       │   └── utf8_iter v1.0.4
│   │       └── percent-encoding v2.3.2
│   ├── tower-service v0.3.3
│   └── url v2.5.8 (*)
├── serde v1.0.229 (*)
├── serde_json v1.0.154 (*)
└── windows-sys v0.61.2 (*)

```

可复核文件：verification-receipt.json 保存 lock、实际 target、直接依赖功能和被测源文件哈希；final-inventory-output.txt 保存残留进程 0、锁哈希与 Step-2 基线 diff 为空。stub 数据/完整握手只在被忽略的 E 盘 target 中，未提交。

原始数据的含义与边界：启动即退的 code=23 来自本次原生 CreateProcessW 子进程；假 health 用例先有 handshake_identity_verified，主因层为 health_boot_id；30 秒计时实际运行完整时长，没有缩短超时假测。重试用例证明 A 清理完后才启动 B，迟到的 A 退出事件被丢弃。Stopping 的退出不计为 EngineExitedAfterReady，app_exit 为独立事件。以上均是 stub/库层证据，不能代替真实引擎、Tauri 事件循环、release 强杀矩阵或 VM 冷启动。

验收项逐条状态（未到的检查点不冒报通过）：

| 编号 | 本检查点结果 |
|---|---|
| 1 | Rust fmt/clippy/test 通过；npm build、tsc、Tauri --no-bundle 未验证 |
| 2a | 5 种确定性原生子进程 stub 行为通过；另加重试与无效路径用例 |
| 2b | 5 种 Win32 启动失败注入通过；成功与失败的实际句柄关闭恰好一次；清理错误阻止重试 |
| 2c | 真实冻结引擎/release 集成未验证 |
| 2d | 纯解析通过所列字段、类型、范围、格式、日历及 token 不泄漏用例 |
| 3 | 仅构造参数注入的无效路径即时 SpawnFailed 已验证；SPECTRUM_ENGINE_EXE 尚未定义，不冒充环境变量验收 |
| 4 | 专用 DLL 副本、release 故障夹具、最终 Canonical 暂存均未实施 |
| 5 | ResumeThread 失败的 TerminateJobObject → Wait → Close 顺序已验证 |
| 6 | A→B 代次竞态与 Stopping 预期退出的库层用例通过 |
| 7 | Tauri 主事件循环 heartbeat/invoke/激活响应未验证；库层测试不能替代 |
| 8 | 窗口尚未实现，未验证 |
| 9 | 单实例插件与激活尚未实现，未验证 |
| 10 | 前端 smoke/对话条/快捷键未实现，未验证 |
| 11 | dev/release 三段计时未验证；VM 冷启动继续延期 |
| 12 | 真实外壳正常关窗 10 轮未验证 |
| 13 | 直接 release 外壳强杀 10 轮未验证 |
| 14 | 真实启动窗口强杀 10 轮未验证 |
| 15 | 真实冻结引擎陈旧握手恢复未验证 |
| 16 | stub 用例中实际 token 原串扫描为 0；真实外壳各轮完整扫描待后续 |
| 17 | 纯状态机覆盖全部允许/禁止迁移，库层退出独立事件已验证；最终外壳完整迁移日志待后续 |
| 18 | resources 忽略规则已加入；资源映射、dev/release 实测未验证 |
| 19 | Python lock 原样保留、本次 Cargo.lock 入库；package-lock 未生成；整体 Git 仍有负责人原有 VM 改动 |
| 20 | 最终两个 EXE manifest 尚未提取；系统策略及 >260 字符实机测试未验证 |

## 遇到的问题

- 首轮 clippy 报 4 处可合并 if 和 1 处大 enum 变体；修改控制流并将事件 Snapshot 装箱，没有禁用 lint。新增清理错误用例随后暴露一次测试返回类型转换遗漏，已显式 map_err 修复。原始失败保留在 clippy-attempt-01.txt / clippy-attempt-02.txt；首轮 17 项通过输出保留在 tests-attempt-01.txt，不改为 18。最终依据为本报告嵌入的 checks-final-output.txt。
- VM 只读现状：Hyper-V=Enabled、vmms=Running，pristine ID 匹配；但 vCPU=10、动态内存 512MB–1TB、TPM=False，与负责人描述不同。完整原文见 ../preflight/environment-current-output.txt；未改 VM，未重做 Copy-VMFile，不把负责人提供的双侧 SHA 当作本次独立验证。
- 当前 PATH Node/npm 为 20.18.0/10.8.2，另有应用自带 Node 24.19.0。本检查点尚未选择或安装前端工具链，后续会先明确兼容版本与安装清单。
- 负责人已有四项未提交 VM 文件变更保留原样，不混入本次 src-tauri 提交。因此不能宣称整个工作区干净；本检查点不作第 3 步最终关闭验收。

## 下一步打算

停在检查点 1 等负责人确认；确认后接真实冻结 onedir 引擎及其失败场景，随后再按顺序进入 Tauri/React，新增依赖另列清单确认。