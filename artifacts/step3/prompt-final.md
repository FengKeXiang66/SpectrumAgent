第 3 步：Tauri 外壳（进程监督器 → 四态 UI → 常驻对话条）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
零、先关账第 2 步（未完成不得开始第 3 步）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
仓库当前状态：artifacts/step2/STATUS.md 写"第 2 步未关闭"、
artifacts/step2/REPORT.md 写"等待负责人复核"、TASK-01 契约修订未提交、
有未跟踪文件。按顺序做完、git status 干净后，第 2 步才算正式关闭。

1. 在 HEAD（d218262）上跑唯一一条正式 pytest 命令（命令以 REPORT.md
   记录的那条为准），输出存 artifacts/step2/revision-01/
   pytest-head-output.txt。注意 --basetemp 的父目录不会自动创建，
   先 mkdir 再跑。
2. （**本项是最后关账动作，实体见第 8 项**：第 3～7 项全部完成
   且 git status 干净后才更新 STATUS / REPORT，不得提前写关闭。）
3. revision-01/ 下已存在的 pytest 原始输出**一份都不许修改**，在
   revision-01/history/README.md 注明它们是开发期中间输出：
   08:42=25 passed、08:50=26、08:53=26、08:59=27（前三份为中间态，
   圆点数递增源于开发期逐加用例；08:59 那份是提交前最后一次全量），
   HEAD 新跑出的准数才是最终依据（预期 27 passed，不符就如实记录
   差异再上报）。**不许回头改旧输出凑数。**
4. TASK-01-地基演示.md 的契约修订（§2 第 2 步、新增 §2b、§6）单独提交
   一笔，message 说明改了什么。
5. 历史探针去重，按确定流程做（**不要用通配符，不要造第三份副本**）：
   a. 先计算并记录 7 个根目录探针的 SHA256（存进
      revision-01/history/manual-probes-manifest.txt：文件名、来源、
      SHA256）。
   b. 已确认 verify_step2.py / verify_step2b.py / verify_signal.py /
      verify_signal2.py / verify_frozen_vs_dev.py 这 5 份，根目录副本与
      revision-01/history/ 下已跟踪副本 **SHA256 逐字节一致**（已核）。
      对这 5 份：
        1) git mv 把已跟踪的 history 副本移入
           revision-01/history/manual-probes/；
        2) 删除根目录中逐字节一致的未跟踪冗余副本（内容仍由 Git 完整
           保留，不算丢证据）。
   c. verify_final.py、verify_recover.py 直接移入 manual-probes/，
      **移入后 git add**（二者当前未跟踪，revision-01/ 不在忽略区，
      不 add 不会进版本控制）。
   d. **不得移动 artifacts/step2/verify_frozen_sources.py**——它已受版本
      控制，被 REPORT 当作正式验证步骤引用。
   e. 今后同名但内容不同：**绝不覆盖旧文件**，以时间戳或短 SHA 追加到
      文件名，并在 manifest 记录来源和哈希。
   f. manual-probes/README 写："历史人工复现脚本，会删除本机
      %LOCALAPPDATA% 握手、taskkill /F、注入控制台信号、把 token 放在
      curl 命令行；非规范验收入口，禁止在 CI 或正式回归中直接运行。"
   g. 正式回归入口只有受版本控制的 lifecycle_regression.py 与
      selfcheck_step2.ps1。
6. VM 三件（VM-BUILD-Win11Clean.md、build-vm.ps1、vm-ops.ps1）单独
   一笔提交，不与第 3 步代码混。build-vm.ps1 缺
   Set-VMKeyProtector，两个脚本都没
   Enable-VMIntegrationService "Guest Service Interface"（默认关闭，
   不启用则 Copy-VMFile 必失败），先补。VM 状态分两态记录，不许
   一笔带过：
   - 脚本首次提交时：文档状态写"待实机验证"；
   - 实机跑通后更新为"实机验证通过"，并引用原始输出（VM 能创建并
     启动、TPM 与 Secure Boot 状态正确、Copy-VMFile 成功、
     pristine 检查点创建与恢复成功）；
   - **关账时若仍为"待实机验证"，第 2 步不得关闭**（见第 8 项）。
7. 生成**产物树全量清单** artifacts/step2/product-manifest.json：
   对象为第 2 步冻结的 dist/app/ 整棵树，逐文件记录"相对 dist/app/
   的路径 + 字节数 + SHA256"。它是第 3 步三.13 暂存 Canonical /
   FaultFixture 两种模式比对的**唯一参照物**——现存
   artifacts/step2/source-manifest.json 覆盖不到产物树（键只有
   source_sha256：13 个 backend 源码哈希；exe_sha256：单个 exe
   哈希；没有任何 _internal 条目），不能用来比对产物树。
   a. 生成前必须与既有第 2 步证据交叉核验，**任一项不符即不得为
      当前目录生成新的权威 manifest，必须如实上报**（防止给已被
      意外改坏的目录颁发"权威认证"）：
      - app.exe 存在，字节数 16,771,126；
      - app.exe SHA256 等于 source-manifest.json 的 exe_sha256 字段；
      - _internal 恰好 543 个文件、合计 238,793,334 字节；
      - _internal/python312.dll 存在；
      - rasterio.libs 恰好 36 个 DLL；
      - rasterio 下恰好 15 个 pyd；
      - 不存在 *.test-backup、临时 manifest、故障夹具标记或其他
        实验残留；
        b. manifest 自身格式（顶层字段名固定，不得自造）：
           schema_version / artifact_source_commit / manifest_generated_at /
           manifest_generator_commit / artifact_root / files；
      - artifact_source_commit = 产生该冻结产物的代码提交，固定
        "d218262"（产物在该提交上冻结；后续文档 / VM / 本清单自身
        的提交都不改变产物来源）；
      - manifest_generator_commit = 执行清单生成时的 HEAD 提交；
      - **两者不得混为一个 "source_commit"**——混用会错误暗示
        二进制由生成清单时的新提交构建；
      - manifest_generated_at 用 UTC ISO8601；
      - artifact_root 固定 "artifacts/step2/dist/app"；
      - files 内相对路径统一用 `/` 分隔、按路径排序，每条含字节数
        与 SHA256；
      - 文件本身仍放在产物树外（当前路径即满足）；
   c. .gitignore 是白名单模式（artifacts/* 全忽略、逐条 ! 放行），
      必须补一行 `!artifacts/step2/product-manifest.json`，否则
      git add 会被拒绝；
   d. git add 并单独一笔提交，message 说明它是暂存比对参照物。
8. 最后关账：第 1、3～7 项全部完成并提交后，先确认除待更新的
   STATUS.md / REPORT.md 外不存在其他未提交改动；随后更新两份文档，
   写入负责人验收日期、HEAD pytest 输出、VM 实机证据和
   product-manifest 提交，明确“第 2 步正式关闭”；将两份文档作为
   最后一笔关账提交提交，然后再次确认 git status 完全干净。
   最终 git status 不干净，仍不得开始第 3 步。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
一、契约已修订落盘，按新版执行（TASK-01 接口契约）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 引擎独占握手生命周期：互斥、所有权判断、陈旧清扫、原子发布、本代关闭
  清理；
- 外壳只读、校验，**绝不由外壳自动删除或改写握手**；启动前读旧握手**仅作
  诊断快照**，不据此认定就绪、也不据此自行中止——真正结果以本次子进程和
  新握手为准；
- 就绪判据：握手 pid == 本次 spawn 的子进程 pid，且 process_created_at
  与该子进程实际创建时间一致；然后 /health 200 且 boot_id 一致；
- **第 3 步不实现任何自动修复**：失败页只显示握手路径、日志路径和"打开
  数据目录"，不动握手文件；
- **启动流程按 TASK-01 §2 六步顺序执行，不许调换**：取应用级单实例锁 →
  只读旧握手（诊断快照）→ 以 CREATE_SUSPENDED 挂起创建子进程 → 创建 Job
  并设 KILL_ON_JOB_CLOSE、把子进程加入（加入失败即终止引擎并报启动
  失败）→ 恢复主线程 → 同时等 /health 与子进程退出，30 秒超时。
- **开发手册《运行约束》的"引擎侧 SQLite 排他锁双保险"本步显式延期
  留痕**（防止关闭验收时悬空）：该条随数据库里程碑实现——DB 建立时
  引擎以排他锁占用数据库，第二实例获取锁失败即退出；本步不实现也
  不假装（任务卡本轮 SQLite 仅连接占位，无库可锁）。本步的多实例
  防护 = 外壳单实例插件 + 引擎握手 owner-alive 拒绝启动，足够覆盖
  地基演示期。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
二、实施顺序（不要先写 React）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Rust 侧 EngineSupervisor + Win32 抽象层与测试替身，UI 全不上；
2. 跑通 stub、注入式 Win32 测试；
3. 接真实冻结引擎——通过**本步新增**的外壳侧环境变量
   SPECTRUM_ENGINE_EXE 指定冻结 onedir 的 app.exe（语义见三.13，
   仓库中目前不存在这个变量，由本步定义）；
4. 再做四态 UI、失败页、底部常驻对话条；
5. 最后跑单实例、关窗/强杀矩阵、release --no-bundle 验收。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
三、实现要求
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. 骨架与依赖
   - src-tauri/（Rust）+ src/ + index.html + package.json + vite.config.ts
     + tsconfig.json（strict: true）；React 19 + TypeScript；
   - **运行时 dependencies 只允许** react、react-dom、@tauri-apps/api 与
     实际用到的 @tauri-apps/plugin-*；
   - **构建与类型检查依赖放 devDependencies**：vite、typescript、
     @vitejs/plugin-react、@types/react、@types/react-dom、
     @tauri-apps/cli 等；
   - **本轮不引入**状态管理库、UI 组件库、HTTP 封装库（四态 UI 用 React
     自身状态即可）；确需引入先停下来问；
   - 定稿选型表已封版 TanStack Query / Zustand / TanStack Table
     三件套（前端行），后续里程碑按定稿引入：**不许自研替代、不许
     换型**，也不要把本轮"不引入"写成"永远禁引"；
   - 提交 package-lock.json 与 src-tauri/Cargo.lock；capabilities 最小化；
   - **.gitignore 必须排除 src-tauri/resources/**（onedir 约 240MB 二进制，
     不许入库）。

2. 四态状态机：定义与迁移
   - 状态仅有四个：Starting / Ready / Failed / Stopping；
   - 允许迁移：
       Starting → Ready / Failed / Stopping
       Ready    → Failed / Stopping
       Failed   → Starting（重试）/ Stopping
   - **Ready 后子进程意外退出必须进入 Failed**，不得仍显示 Ready；
   - **Stopping 是进程内最后一个状态**：清理完成后记录独立的 app_exit
     事件，随后外壳进程退出。app_exit **不是第五个状态，也不记作状态
     迁移**，否则"只允许四态"与日志模型自相矛盾；
   - 每次状态迁移记录 from / to / reason，不得出现未定义迁移。

3. 代次保护（generation_id）
   - 每次启动生成新的 generation_id；**格式用递增整数或带连字符的
     UUID**——不得用裸 32 位 hex，否则与 token 的日志扫描规则混淆、
     真假难辨；
   - 子进程退出监听、握手轮询、health 请求、超时任务、以及**阻塞式 Win32
     等待的回传结果**，全部携带该 generation_id；
   - 回调只有在该 generation_id 仍等于当前代时才能修改状态，否则丢弃；
   - 进入 Stopping 后，**预期的**子进程退出不得转为 Failed /
     EngineExitedAfterReady；
   - 重试必须先等上一代清理与进程退出完成，才创建下一代；
   - 目的：防止 A 的迟到退出回调把 B 的 Starting/Ready 误改成 Failed。

4. 失败原因分类（外壳内部与失败页共用一套枚举，至少包括）
   - SpawnFailed：exe 不存在或 CreateProcessW 失败；
   - JobSetupFailed：CreateJobObjectW / SetInformationJobObject /
     AssignProcessToJobObject 失败；
   - **ResumeFailed：子进程已创建并加入 Job，但 ResumeThread 失败**（保存
     Win32 错误码，用 TerminateJobObject 清理）；
   - ExitedBeforeReady：就绪前退出；
   - HandshakeInvalid：非法或缺字段握手；
   - StartupTimeout：30 秒未就绪；
   - HealthIdentityMismatch：health boot_id 不一致；
   - EngineExitedAfterReady：Ready 后引擎意外退出。
   失败页至少显示用户可读原因、退出码或 Win32 错误码、日志路径、数据
   目录入口和重试按钮；禁止倾倒 traceback。
   SPECTRUM_ENGINE_EXE 指向不存在文件时必须立即进入 SpawnFailed
   （该变量仅 dev/test 构建读取，见三.13 与验收 3 / 18），
   **不得等 30 秒，不得归类为超时**。
   **失败分类规则（因果优先于优先级）**：
   - 启动前诊断读到预置握手非法（JSON / 字段 / 元数据）只记诊断字段
     preexisting_handshake_invalid（含原因细分），**不作为分类
     依据**；
   - 归为 HandshakeInvalid 必须有**逐行可归属的因果证据**，四条
     全部满足才成立：① 启动子进程前记录引擎日志文件与 EOF 偏移
     （引擎日志按日切分，跨午夜时同时跟踪启动日与退出日两个
     文件），只扫描本次启动后新增的完整 JSON 行；② 其中
     event=handshake_error、logger=engine.handshake 的行**自带
     pid / boot_id**（engine.py:43 的 bind_contextvars +
     logging_config 的 merge_contextvars；当前实现里握手校验在
     engine.py:22 的 HandshakeServer.startup() 内、由 uvicorn 事件
     循环线程执行（workers=1，不另起工作线程；asyncio Task 复制
     context，因此该行确实自带 pid）——**但验收不依赖该实现
     细节**：handshake_error 必须自带 pid 且等于本次 CreateProcessW
     返回的子进程 PID；pid 缺失、类型非法或不匹配时一律视为没有
     可归属的因果证据，**不得**用 engine_boot、时间接近或 boot_id
     进行回退推定；engine_boot 只能作辅助证据，不能替代
     handshake_error 自身的 PID。若未来引擎把握手判断移入工作
     线程，必须显式传播 contextvars，不许用降低验收标准的方式解决；
     注意 engine_boot 因在绑定前发出，反而只带调用处显式的 pid），
     要求该行 pid == 本次 CreateProcessW 返回的子进程 PID——这是
     **直接判据**；新增行里的 engine_boot（pid 相同）作为辅助锚定；
     ③ 该行时间戳落在子进程实际创建时间至观察到退出的区间内
     （统一 UTC 归一化后比较，同三.9）；④ error 属启动期校验族
     （HANDSHAKE_READ_FAILED / HANDSHAKE_INVALID_JSON /
     HANDSHAKE_INVALID_FIELDS / HANDSHAKE_INVALID_METADATA /
     HANDSHAKE_OWNER_UNVERIFIABLE）。boot_id 仅作辅助记录——非法
     旧握手路径下本代握手尚未发布，不能要求外壳事先知道。只满足
     "时间窗内有错误"但 pid 对不上，属别的实例的事件，**不得**
     作为本次因果证据；外壳对引擎日志只读、且只在本数据根内读；
   - 无因果证据时，主因让位给更直接的进程证据：SpawnFailed /
     JobSetupFailed / ResumeFailed / ExitedBeforeReady，同时失败
     对象**必须同时携带** exit_reason 与 preexisting_handshake_
     invalid 两个字段，一个都不许丢；
   - 禁止用优先级覆盖更直接的证据：例如缺 DLL 时 Python 尚未运行，
     即使旁有非法预置握手，也只能是 ExitedBeforeReady + 诊断。

5. Win32 抽象层：必须可注入，范围要覆盖被断言的全部调用
   抽象至少覆盖：
     CreateJobObjectW、SetInformationJobObject、CreateProcessW、
     AssignProcessToJobObject、ResumeThread、TerminateProcess、
     TerminateJobObject、WaitForSingleObject、GetExitCodeProcess、
     GetProcessTimes、CloseHandle。
   测试替身必须能记录调用顺序、参数、以及每个句柄的关闭次数；生产实现
   使用真实 Win32 API。
   失败 → 清理路径的对应关系（按创建顺序：挂起创建 → 建 Job → 加入 →
   恢复；测试按下表逐条断言，**只断言实际创建成功的句柄**）：
     - CreateProcessW 失败          → SpawnFailed；此时没有任何子进程
       句柄：**不调** TerminateProcess / WaitForSingleObject，**不关
       闭**不存在的 hProcess / hThread；
     - CreateJobObjectW 失败        → JobSetupFailed；子进程已挂起创建：
       TerminateProcess → WaitForSingleObject → 关 hThread、hProcess；
     - SetInformationJobObject 失败 → JobSetupFailed；子进程未入 Job：
       TerminateProcess → Wait → 关 hThread、hProcess，并关 Job；
     - AssignProcessToJobObject 失败 → JobSetupFailed；子进程未入 Job：
       同上；
     - ResumeThread 失败            → ResumeFailed；子进程已入 Job：
       TerminateJobObject → Wait → 关 hThread、hProcess、Job。
       实际创建成功的每个句柄必须恰好关闭一次；不存在的句柄不得假称关闭。

6. 阻塞式调用不得冻结界面
   - WaitForSingleObject 等阻塞式 Win32 调用必须放在专用线程或
     spawn_blocking 中；**不得阻塞 Tauri 主事件循环或异步执行器工作
     线程**（否则窗口、单实例回调、invoke 命令全部冻结）；
   - 等待结果通过 channel 回传，并携带 generation_id；迟到的阻塞任务
     结果同样要过代次过滤。

7. CreateProcessW 参数细节
   - bInheritHandles **显式传 FALSE**（不依赖默认值）；
   - lpApplicationName 用解析后的完整 exe 路径；
   - lpCurrentDirectory 用 exe 所在目录；
   - 如使用 lpCommandLine，必须是可写 UTF-16 缓冲区（CreateProcessW 可能
     原地修改它）；
   - 加 CREATE_NO_WINDOW，避免闪 Python 控制台窗口；
   - **Win32 调用失败后立即保存 GetLastError()，再做其他清理**，否则错误
     码会被后续 API 覆盖；
   - Rust 标准库 Command 拿不到"挂起创建再恢复主线程"，必须用
     CreateProcessW(CREATE_SUSPENDED ...)。

8. Job Object 与句柄生命周期（红线，写错就是孤儿进程）
   - CreateJobObjectW 的 lpJobAttributes 传 **NULL**，返回的 Job 句柄
     默认不可继承；不要传自定义 SECURITY_ATTRIBUTES 改继承性；
   - **引擎绝不能继承 Job 句柄**：KILL_ON_JOB_CLOSE 只在 Job 的最后一个
     句柄关闭时才触发，若外壳被强杀而引擎仍持有继承来的 Job 句柄，Job 不会
     关闭，孤儿引擎进程就留下了；
   - 若以后确需重定向子进程标准流，只能用 STARTUPINFOEX +
     PROC_THREAD_ATTRIBUTE_HANDLE_LIST 精确白名单继承，且绝不许把 Job
     句柄放进白名单；
   - 句柄生命周期：hThread 只在 ResumeThread 前需要，ResumeThread
     成功后**立即关闭 hThread**；hProcess 保留用于退出监听与取退出码；
     Job 句柄保留至外壳退出或本代 supervisor 清理；
   - 清理顺序：终止（TerminateJobObject）→ 等 hProcess 确认退出 → 关闭
     hProcess 与 Job；尚未成功入 Job 时只能用 TerminateProcess(hProcess)；
   - 五条终态路径（正常关窗、启动失败、超时、health 不匹配、重试前）都
     走同一套清理；
   - 用 Rust RAII 包住所有句柄，保证任何错误分支都只关闭一次、不泄漏。

9. 握手与 health
   - 握手只读；就绪判据见「一」；
   - 等握手用轮询 + 超时，不做文件系统监听；
   - /health 客户端**显式禁用代理**（reqwest .no_proxy()，它同时禁用系统
     代理；不要写 trust_env=false，那是 httpx 的说法），设连接与总超时；
   - **process_created_at 统一归一化后比较**：握手里的 ISO8601
     （YYYY-MM-DDTHH:MM:SS.mmmZ）解析为 UTC 毫秒整数，与 GetProcessTimes
     取得的子进程创建时间同样归一化后做整数比较；禁止字符串直接 ==。

10. Rust ↔ 前端桥：固定命令，禁止通用代理
    - 只暴露固定命令（engine_status、run_smoke 等）；签名里**不许**出现
      任意 URL、端口、HTTP 路径、Authorization 参数；
    - Bearer token 只存 Rust 侧状态；前端代码、DOM、localStorage 一律
      不得出现 token 明文；
    - 客户端只访问握手确认过的 127.0.0.1。

11. 常驻对话条：必须定义实际行为
    - 依据：需求文档 v2.4 变更说明"每个界面都保留常驻的 Agent 输入框，
      按钮与表单是对话的可视化与确认面，而不是与对话并列的另一条路"，
      UI 文档（ui-v2.3）2.1 信息架构同此（"底部对话条在所有业务屏常驻"）；
      对应需求 FR-D13（需求 3.4 域）；
    - **FR-D13 本步只落地子集**：常驻输入框 + 快捷键 + 占位行为；
      "输入框自动继承上下文并在发送前明示""写操作可定位可撤销"
      "空态/错误态等价入口"要等有上下文对象的数据接入/标注里程碑，
      本步不实现、不预留假接口；
    - Starting：窗口隐藏，本态下对话条不渲染（不可达，无需"禁用"文案）；
    - Ready：可输入"运行冒烟测试"或点击发送，调用固定的 run_smoke；
    - Failed：对话条保留但禁用，显示失败原因与诊断入口；
    - Stopping：禁用，显示"正在关闭"；
    - Windows 下至少支持 Ctrl+K 聚焦、Ctrl+Enter 发送；
    - 不识别的输入明确提示"当前地基演示仅支持冒烟测试"，**不得假装调用
      LLM**。

12. 单实例与激活
    - `npm run tauri add single-instance`，插件**第一个注册**（官方要求），
      回调签名 init(|app, args, cwd|)；
    - 不要再手写命名互斥体做单实例；
    - Ready / Failed：回调立即 show + unminimize + set_focus；
    - Starting：**窗口一律保持隐藏**（任务卡契约：就绪才显示窗口），
      只记 pending_activation=true，等进入 Ready 或 Failed 后才
      show + focus；不提供"启动中界面"备选方案；
    - 回调里窗口可能尚未创建，取窗口必须容错，不许 expect()/unwrap() 崩掉。

13. 资源路径与引擎 exe 解析：只允许仓库相对路径
    - **暂存必须走受版本控制的脚本**（如仓库根 stage-backend.ps1），
      不许手工复制；脚本有且仅有两个显式模式，**默认只能是
      Canonical**：
      - **Canonical 模式（默认）**：来源默认
        artifacts/step2/dist/app/（第 2 步正式产物），必须与第 2 步
        正式产物清单 product-manifest.json 全量一致（该清单是
        dist/app 全量逐文件"相对路径+字节数+SHA256"，由关账第 7 项
        生成并入库，是两种模式比对的唯一参照物；现有
        source-manifest.json 覆盖不到产物树（source_sha256：13 个
        源码哈希 + exe_sha256：单个 exe 哈希，无 _internal 条目），
        不能用来比对产物树）；用于一切普通 dev / release
        构建和**最终交付构建**；来源不完整（缺 app.exe / _internal /
        与 manifest 不符）立即失败并说缺什么；
      - **FaultFixture 模式**：必须显式指定，**不得由文件差异自动
        推断**；来源与 product-manifest.json 相比必须**恰好只缺少
        预定的 _internal/python312.dll**（与第 2 步 missing-dll
        记录一致），
        其余相对路径、字节数、SHA256 全部一致；只允许用于缺 DLL
        验收；**fault_fixture=true 标记不得写进 resources/backend/**
        （写进去目标目录就无法与来源精确镜像），放在外部 staging
        report、shell 构建日志或专用构建输出目录名，三者之一或
        同时即可；
        **禁止作为最终交付构建来源**；
      - 两种模式下目标目录都与**所选来源**精确镜像（不是覆盖
        复制）：先安全清空目标（目标只允许是解析后确认位于仓库内
        的 src-tauri/resources/backend/），再复制来源 onedir 的
        **目录内容**——最终布局必须是 resources/backend/app.exe，
        不得出现 resources/backend/app/app.exe 这类嵌套；目标
        manifest 与所选来源 manifest 全量一致，不许多文件、不许
        少文件、不许有旧文件残留；
      - **manifest 与比对报告必须存放在来源与目标目录之外**
        （artifacts/step3/staging-reports/ 下）——否则 manifest
        文件自身会污染被比较的目录；且**必须入库**（它们是验收
        4b / 4c 的夹具边界与最终交付边界证据）。报告为**追加式**：
        每次暂存生成独立 run_id，报告文件名包含 UTC 时间、模式和
        短 SHA；Canonical、FaultFixture、最终 Canonical 三轮的
        报告分别保存，**已有报告一律不得覆盖**（否则最终 Canonical
        会覆盖 FaultFixture 的边界证据）。注意白名单模式：
        artifacts/step3/ 整目录被忽略，需先补四行
        `!artifacts/step3/`、`artifacts/step3/*`、
        `!artifacts/step3/staging-reports/`、
        `!artifacts/step3/staging-reports/*`，否则 git add 被拒；
      - **绝不修改来源产物**；最终 release 必须重新以 Canonical
        模式暂存、构建并全量复核；
      - src-tauri/resources/ 在 .gitignore 内，新检出无法直接构建，
        tauri build 前必须先跑该脚本；
    - release 模式：app.path().resolve("resources/backend/app.exe",
      tauri::path::BaseDirectory::Resource)；
    - **引擎 exe 三个来源，优先级从高到低**：
      ① **测试注入**：EngineSupervisor 通过构造参数 / 测试配置接收
         exe 路径，stub 测试走这条，**不借用** SPECTRUM_ENGINE_EXE；
      ② **dev 联调**：SPECTRUM_ENGINE_EXE 是本步新增的外壳侧机制
         （仓库中目前不存在，不是引擎提供的），**仅 dev 构建读取**；
         设置时它必须是冻结 onedir app.exe 的绝对路径；
      ③ **release**：**不读 SPECTRUM_ENGINE_EXE**（编译期隔离，如
         debug_assertions），只用 resolve(Resource) 的
         resources/backend/app.exe；
    - dev 联调指向的必须是冻结 onedir（artifacts/step2/dist/app/
      app.exe）；**禁止 spawn python.exe / python -m backend**——用
      解释器启动会改变进程模型，第 2 步实测的单 exe / 控制台信号 /
      强杀结论全部失效，验收作废。**代价提示**：引擎侧任何改动都
      必须重新冻结 onedir 才能联调，不存在"改完 Python 直接热启"
      的捷径，排期时把这步冻结成本算进去；
    - tauri.conf.json：
        "bundle": { "resources": { "resources/backend/": "resources/backend/" } }
    - **禁止在 tauri.conf.json 里写绝对路径**（如 E:/...）——换机器就无法
      构建；
    - 禁止手工 resource_dir() + join；
    - 最终映射以实际 `tauri build --no-bundle` 产物为准，不许凭记忆断言。

14. 安装配置字段（第 4 步才打包，现在先写对）
    - bundle.windows.webviewInstallMode.type = "offlineInstaller"
    - bundle.windows.nsis.installMode = "currentUser"
    - **产品名与安装目录名用 ASCII**（如 SpectrumAgent），显示名与快捷
      方式可用中文——规避 GDAL / PROJ 在中文路径下的编码问题（需求 8.1
      原条）；
    - **长路径支持（需求 8.1）分三层，本步只做第一层**：
      ① longPathAware **不是** tauri.conf.json 的合法键（已核对
         Tauri 2 配置参考，schema 中没有），不得写入配置；
      ② 本步为 Tauri 外壳提供自定义 Windows application manifest，
         经 tauri-build 的 WindowsAttributes::app_manifest 嵌入；
         **自定义 manifest 整体替换默认 manifest**，因此必须以默认
         manifest 为底稿，保留 Microsoft.Windows.Common-Controls
         6.0.0.0 依赖，再加带正确 WindowsSettings 命名空间的
         longPathAware=true——不许交一份只含 longPathAware 的残缺
         manifest（tauri-build 官方文档对此有明确警告）；
      ③ 冻结引擎侧**只记录并验证、不修改**：第 2 步产物 app.exe
         已内嵌 longPathAware / asInvoker / Common-Controls v6
         （已只读扫描实测），引擎 spec 已验收封版，本步不许动；
         最终构建须提取并检查外壳 exe 与 backend/app.exe **两个**
         manifest；
      - longPathAware **按进程生效**（外壳与引擎是两个独立进程，
        都要有）；且 manifest 只是应用侧 opt-in——真正解除 Win32
        API 的 MAX_PATH 限制还需系统 LongPathsEnabled=1，
        currentUser 安装不得静默修改 HKLM（需管理员权限）；
      - **本步不得声称长路径需求已完整通过**；第 4/5 步须在记录了
        系统策略状态的干净 VM 上，用超过 260 字符的真实路径分别
        验证外壳与引擎的文件访问；
    - 关键键名以本地生成的 src-tauri/gen/schemas/desktop-schema.json 为准，
      schema 里不存在的键名一律不许写；
    - "卸载前结束引擎进程、卸载不删用户数据"（8.1 卸载条）属第 4 步 NSIS
      脚本，本轮只记录、不提前实现。

15. 外壳日志
    - %LOCALAPPDATA%\SpectrumAgent\logs\shell-YYYYMMDD.log，从第一行启用；
    - 不得记 token，不得记完整握手内容（可记 boot_id/pid/port）；
    - 留痕内容：尝试启动、子进程 pid、Job 加入结果、握手读取结果、health
      结果、窗口显示、激活请求、generation_id、每次状态迁移 from/to/
      reason、清理结果、app_exit。

16. 代码质量
    - cargo clippy 无 warning；tsc --noEmit 无错误；strict；
    - 可失败路径不许 unwrap()/expect()/panic!；不为跑通禁用 lint。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
四、验收关卡（逐条贴原始输出）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. 静态检查与构建全绿，逐条贴原始输出：cargo fmt --check；
   cargo clippy --all-targets --all-features -- -D warnings；
   cargo test 全部通过（贴完整输出）；npm run build（含
   tsc --noEmit）；一次 npm run tauri build -- --no-bundle 成功。

2. Supervisor 测试分三组，不许混：
   2a 子进程 stub（确定性）：
       - 成功：stub 发布握手 + health 回匹配 boot_id → Ready；
       - ExitedBeforeReady：启动即退 → 立即 Failed，贴退出码；
       - StartupTimeout：stub 存活超过 30 秒但不发布握手、不监听端口 →
         约 30 秒后 Failed；
       - HealthIdentityMismatch：构造能通过本次子进程 pid /
         process_created_at 校验、但端口指向假服务、且返回不同 boot_id
         的握手 → 失败必须发生在 boot_id 检查而非 pid 检查，证据要能
         区分是哪一层拦下的；
       - EngineExitedAfterReady：**专用 stub**——先发布合法握手、health
         成功进入 Ready，随后主动退出 → 恰好一次
         Ready → Failed(EngineExitedAfterReady)。
   2b 注入式 Win32 测试（Job 失败路径只能这样测）：
       - 分别注入 CreateProcessW、CreateJobObjectW、
         SetInformationJobObject、AssignProcessToJobObject、
         ResumeThread 失败；
       - 每种按三.5 映射表逐条断言：失败分类正确（SpawnFailed /
         JobSetupFailed / ResumeFailed）、终止用 TerminateProcess
         还是 TerminateJobObject 正确、该等的等了、**实际创建成功的
         句柄恰好关闭一次**；CreateProcessW 失败时进一步断言**没有**
         对不存在的 hProcess / hThread 做 Wait 或 Close；
       - 贴测试替身记录的调用顺序与参数。
   2c 真实 release 集成：正常启动到 Ready、真实 /health、真实 /smoke、
       缺 DLL（专用 release 故障夹具，见第 4 条）、陈旧握手恢复、
       关窗与强杀回收。
       **缺 DLL 轮次记录从 spawn 到进入 Failed 的耗时**，对照任务卡
       验收 8③ 的"约 2 秒内"口径；超出如实报告，不许改口径迁就实现。
       **HandshakeInvalid（只能用真实冻结引擎）**：分别预置非法
       JSON 与缺字段握手后启动——外壳只作诊断读取、不删不改；本次
       子进程仍被拉起；引擎 fail-closed 退出；外壳凭引擎结构化日志
       中的 handshake_error 事件归类为 HandshakeInvalid（因果证据
       规则见三.4），不得仅凭"预置握手非法 + 子进程退出"断定；
       预置握手字节前后不变；失败页显示握手路径、日志路径与"打开
       数据目录"。反向对照：缺 DLL 轮次没有引擎日志证据，**不得**
       被归为 HandshakeInvalid。（合法所有者占用分支已在第 2 步
       引擎侧验收，本步不复测，只要求同样进失败页、不永久转圈。）
   2d 外壳侧握手解析单元测试（不起子进程，纯函数级）：**Rust 解析
       规则逐项镜像当前引擎契约**（backend/handshake.py 的 FIELDS
       exact-set 与逐字段校验），至少覆盖：
       - 非法 JSON；顶层不是对象（数组 / 字符串 / 数字）；缺任一
         必需字段；多出未知字段——一律拒绝；
       - boot_id：非字符串、非 8 位小写 hex（7/9 位、含大写）；
       - pid：非整数（含 JSON true/false 布尔，对应 Python
         "type is int" 语义）、≤ 0、≥ 2^32；
       - port：非整数、≤ 0、≥ 65536；
       - protocol：非整数或不等于 1（字符串 "1" 也不行）；
       - version：不等于精确字符串 "0.1.0"（如 "0.1.1"、尾部
         空格）；
       - token：非字符串、空、非 32 位小写 hex（31/33 位、大写）；
       - process_created_at / started_at：非字符串、非
         YYYY-MM-DDTHH:MM:SS.mmmZ 三位毫秒格式、以及格式对但
         日期不存在（如 2026-02-30T…）；
       - 合法握手完整解析成功，各字段值正确；
       - 所有错误路径与日志都不得输出 token 明文。
   **超时与 boot_id 假服务继续由专用 stub 验证，不假称由真实引擎制造。**

3. SpawnFailed（**仅 dev/test 构建**）：在 dev/test 构建中把
   SPECTRUM_ENGINE_EXE 设为不存在的路径 → 立即失败，不得等
   30 秒、不得归类为超时；贴启动到进入失败态的耗时。正式 release
   忽略该变量（恶意环境变量不影响 bundled engine）由验收 18 的
   反向用例单独验证——两条各管一头，互不否定。
4. 缺 DLL 验收分两级，两级都不许碰第 2 步正式产物：
   a. **dev/test 快速级**：完整 onedir 复制到临时目录，副本里移走
      DLL，dev/test 构建经测试注入指向该副本——只证明"启动即退出 →
      立即 Failed"的行为，**不算 release 证据**；
   b. **专用 release 故障夹具（release 级证据）**：暂存必须走
      FaultFixture 显式模式（fault_fixture=true 标记按三.13 放在
      sources 外），构建一个专用 release（--no-bundle 即可）并运行：
      断言约 2 秒内进入失败界面、显示退出码与日志路径、
      **实际启动的是夹具内的 app.exe**（贴解析路径）；
   c. 夹具验收完成后：重新以 Canonical 模式暂存完整正式 onedir，
      重建
      最终 release，核对最终 resources 与第 2 步产物**完整 manifest
      全量一致**（逐文件相对路径 + 字节数 + SHA256——仅抽样不算
      通过，这一步是交付边界，必须证明无 DLL 残留）；
      **故障夹具不得作为最终交付物**。
5. ResumeThread 失败的清理必须是 TerminateJobObject（子进程已入 Job），
   不是 TerminateProcess；贴注入测试对调用顺序的记录。
6. 代次竞态：构造"A 失败/清理中 → 用户立即重试 → A 的退出回调稍后到达"
   场景，证明 B 的 Starting/Ready 不被旧回调改写；再验证进入 Stopping 后
   的子进程退出不产生 EngineExitedAfterReady。
7. 界面不冻结（Starting 窗口隐藏，改为可自动验证的证据）：在 30 秒
   超时 stub 运行期间，Tauri 主事件循环周期性写带时间戳的 heartbeat，
   期间再触发一次第二实例激活和一个内部 invoke 命令；断言 heartbeat
   无异常长中断、单实例回调被处理且 pending_activation 被置位、
   invoke 正常返回、窗口始终保持隐藏。heartbeat 写入器是**测试
   探针**（测试构建或测试期启用），正式版本不持续定时写日志。
   禁止要求"移动 / 点击一个隐藏窗口"。
8. 窗口可见性：Starting 隐藏；Ready 显示主界面；Failed 显示失败界面
   （不得隐藏卡死）；第二实例回调在 Starting 下不提前显示。
9. 单实例：第一例运行中再启动一次，不起第二个引擎、激活已有窗口；并在
   第一例处于 Starting 时再试一次。**计数规则**：外壳实例按外壳
   完整可执行路径统计（app.exe 是通用名，机器上可能有无关同名
   进程，一律不按进程名数）；引擎实例按 supervisor 记录的子进程
   PID 统计，并核对其 ExecutablePath 等于本轮解析出的
   resources/backend/app.exe；tasklist 仅作辅助展示。
10. /smoke 通过前端 invoke() 调通并显示真实返回；对话条行为逐态贴
    截图或日志（Starting 态窗口隐藏，以日志为证，无截图属预期）；
    Ctrl+K 聚焦、Ctrl+Enter 发送各贴一次操作证据；不识别的输入有
    明确提示且不假装调用 LLM。
11. 三段计时：引擎就绪 / 启动到界面可交互 / 首次 /smoke；dev 与 release
    分别记，标注是否冷启动（dev 无"双击"，按 tauri dev 启动到界面
    可交互计时）。**不预设 ≤3 秒通过线**。本轮 dev/release 数据是
    中间数据：定稿验收标准 1 要求的干净 Win10/11 冷启动三段计时在
    第 5 步干净 VM 上执行，**未经 VM 不得声称该条已通过**。
12. 关窗：引擎进程与端口都没了；10 轮，每轮贴 PID 与端口核验。
13. 任务管理器强杀外壳：**直接运行构建出的 release 外壳 exe**，不经
    tauri dev、npm、测试运行器或 IDE（否则父级 Job 可能顺带回收引擎，
    掩盖外壳自己的 Job 实现错误）；强杀后核验引擎 PID 与端口；10 轮。
    引擎存废按本轮记录的子进程 PID + ExecutablePath 完整路径判定，
    不按进程名 app.exe 模糊匹配。这一组必须能证明 Job 句柄没被
    引擎继承。
14. 启动过程中（握手出现前）强杀外壳：无孤儿引擎进程；10 轮
    （启动窗口极短，用"拉起后立即 taskkill /F"的循环凑满）。孤儿
    判定按 ExecutablePath 完整路径 == 本轮解析的 backend/app.exe，
    app.exe 为通用名，不按进程名匹配；每轮贴 PID 与端口。
15. 陈旧握手不得被误判为就绪：预置含已死 PID 的 handshake.json，再启动，
    必须等自己的子进程真正发布新握手才 Ready；贴新旧 boot_id 与 pid。
16. token 泄漏检查（按证据强度排序）：① 取每轮测试实际读到的握手
    token 原串，精确扫描外壳日志，0 命中；② 扫描
    "Authorization: Bearer"，0 命中；③ 扫描完整握手 JSON，0 命中。
    通用 32 位 hex 扫描仅作辅助，不作为唯一依据（避免误伤未来的
    合法 ID）。
17. 状态机：迁移日志覆盖全部允许迁移、无未定义迁移、app_exit 只作为
    独立事件出现且不记为第五态；贴一遍完整迁移序列。
18. 资源路径：确认 tauri.conf.json 无绝对路径；src-tauri/resources/ 在
    .gitignore 内且未入库；贴 git status 与一次 --no-bundle 产物布局实测；
    dev 轮次贴 SPECTRUM_ENGINE_EXE 指定 artifacts/step2/dist/app/
    app.exe 启动成功的证据；**release 轮次记录最终解析出的 exe 路径，
    证明实际使用的是 resources/backend/app.exe**；再把
    SPECTRUM_ENGINE_EXE 故意设成无效路径跑一次 release，确认启动
    不受影响（证明 release 真的不读该变量）。
19. 三套 lock 归档，git status 干净。
20. Windows manifest（本步只验 manifest 落盘，不冒充长路径功能已
    通过）：
    - 从**最终 release 外壳 exe** 提取 RT_MANIFEST（Win SDK 自带
      mt.exe；**PowerShell 里未入变量的分号会被当作命令分隔符**，
      必须按下面形式写，贴命令时照此）：
      ```powershell
      $inputArg = "-inputresource:$exePath;#1"
      $outputArg = "-out:$manifestPath"
      & $mtPath $inputArg $outputArg
      Get-Content -LiteralPath $manifestPath -Raw
      ```
      提取的 XML 写入 artifacts/step3/staging-reports/，**不写入
      资源树**；证明外壳 exe 的 manifest 包含
      Microsoft.Windows.Common-Controls 6.0.0.0 与命名空间正确的
      longPathAware=true
      （http://schemas.microsoft.com/SMI/2016/WindowsSettings）；
    - 从 resources/backend/app.exe 提取 RT_MANIFEST，证明包含
      longPathAware=true、requestedExecutionLevel=asInvoker 与
      Common-Controls v6（引擎侧只验不改）；
    - 贴提取命令与 mt.exe 输出，并**完整保存、展示提取出的 XML**——
      mt.exe 成功时可能没有实质控制台输出，**不得只贴空输出**；
    - 分别记录外壳 exe 与引擎 app.exe 的 SHA256，证明提取对象就是
      本轮最终验收产物；
    - RT_MANIFEST 不存在或提取失败，本项直接判失败，不许用构建
      源文件里的 manifest XML 替代；
    - 读取并记录当前机器 LongPathsEnabled 的实际值；
    - **本步仅验 manifest 落盘**；"超过 260 字符路径可用"仍留给
      第 4/5 步干净 VM（需系统 LongPathsEnabled=1 配合），不得在
      本步声称该功能已通过。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
五、收尾
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 按里程碑提交；不得提交 dist/、target/、node_modules/、
  src-tauri/resources/；
- 任何一条不过就如实写没过；
- 要改接口契约先停下来问；
- 动手前先把第四节验收标准逐条复述一遍再写代码；
- 四条纪律不变：先跑只读探针再下断言；不确定写"未验证"；贴出来的原始
  数据要往下解释一层；探针的价值在于跑炸不在于跑通。
