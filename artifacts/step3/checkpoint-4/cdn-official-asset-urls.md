# 官方 GitHub 发布资产 CDN 直取地址（Ephemeral，用后即焚）

背景：github.com 宿主当前被网络阻断（直连 TCP 443 丢弃、经本地代理 TLS 失败），
但 GitHub 官方资产 CDN（release-assets.githubusercontent.com）直连可达。
以下 URL 是官方 github.com 发布地址的签名跳转目标，由负责人实测捕获，
此刻实测仍返回 200 且字节数精确吻合。签名可能随时失效——**先下载再校验，不要拖延**。

纪律：不改写 URL 任何字符；不关证书/吊销校验；不用非官方镜像；
下载后必须按下方锚点校验，任何不符即停并报告。

## 1) nsis-3.13.zip

- 官方发布地址：https://github.com/tauri-apps/binary-releases/releases/download/nsis-3.13/nsis-3.13.zip
- 期望字节数：2,363,925
- 期望 SHA1（CLI 2.12.3 内嵌自校验锚点）：DB14F8AF2EA346B786C6AE19343F61AAF5E09B8E
- CDN URL（单行，勿改字符）：

https://release-assets.githubusercontent.com/github-production-release-asset/357697736/1a8ffa99-cbe2-4391-b822-d89b36916ce2?sp=r&sv=2018-11-09&sr=b&spr=https&se=2026-10-18T16%3A29%3A38Z&rscd=attachment%3B+filename%3Dnsis-3.13.zip&rsct=application%2Foctet-stream&skoid=96c2d410-5711-43a1-aedd-ab1947aa7ab0&sktid=398a6654-997b-47e9-b12b-9515b896b4de&skt=2026-10-18T15%3A29%3A01Z&ske=2026-10-18T16%3A29%3A38Z&sks=b&skv=2018-11-09&sig=mI9Sjh8oWj9txUXasIVwOjZKQh%2FYmJavXOX1aMWdNRc%3D&response-content-disposition=attachment%3Bfilename%3Dnsis-3.13.zip&response-content-type=application%2Foctet-stream

## 2) nsis_tauri_utils.dll

- 官方发布地址：https://github.com/tauri-apps/nsis-tauri-utils/releases/download/nsis_tauri_utils-v0.5.3/nsis_tauri_utils.dll
- 期望字节数：34,304
- 期望 SHA1（CLI 2.12.3 内嵌自校验锚点）：75197FEE3C6A814FE035788D1C34EAD39349B860
- CDN URL（单行，勿改字符）：

https://release-assets.githubusercontent.com/github-production-release-asset/580520344/bbd0c219-8e7e-4362-a1af-4459926e1887?sp=r&sv=2018-11-09&sr=b&spr=https&se=2026-10-18T16%3A24%3A16Z&rscd=attachment%3B+filename%3Dnsis_tauri_utils.dll&rsct=application%2Foctet-stream&skoid=96c2d410-5711-43a1-aedd-ab1947aa7ab0&sktid=398a6654-997b-47e9-b12b-9515b896b4de&skt=2026-10-18T15%3A23%3A30Z&ske=2026-10-18T16%3A24%3A16Z&sks=b&skv=2018-11-09&sig=r%2BdH2bY42GRNhz679HY2l%2FgkC3%2BY%2FVxNiVjLseOkP8%3D&response-content-disposition=attachment%3Bfilename%3Dnsis_tauri_utils.dll&response-content-type=application%2Foctet-stream

## 3) WebView2 x64 离线安装器（微软官方，双通道可达，无需签名 URL）

- 官方 fwlink：https://go.microsoft.com/fwlink/?linkid=2124701
- 期望字节数：214,156,024
- 校验：Authenticode 签名必须 Valid 且签名者为 Microsoft；归档 SHA256。
- 优先交给 CLI 自己下载（msedge CDN 可达）；失败才手动下载。

## 下载命令模板（PowerShell，直连）

New-Item -ItemType Directory -Force -Path E:\AI_Agent\src-tauri\target\tauri | Out-Null
curl.exe --noproxy * -L --max-time 300 -o E:\AI_Agent\src-tauri\target\tauri\nsis-3.13.zip "<第 1 节 URL>"
curl.exe --noproxy * -L --max-time 300 -o E:\AI_Agent\src-tauri\target\tauri\nsis_tauri_utils.dll "<第 2 节 URL>"
curl.exe --noproxy * -L --max-time 900 -o E:\AI_Agent\src-tauri\target\tauri\MicrosoftEdgeWebView2RuntimeInstallerX64.exe "https://go.microsoft.com/fwlink/?linkid=2124701"
Get-FileHash E:\AI_Agent\src-tauri\target\tauri\nsis-3.13.zip,E:\AI_Agent\src-tauri\target\tauri\nsis_tauri_utils.dll -Algorithm SHA1
Get-AuthenticodeSignature E:\AI_Agent\src-tauri\target\tauri\MicrosoftEdgeWebView2RuntimeInstallerX64.exe

## 落盘后的后续

1. 按 CLI 自身期望的 tools 缓存布局放置两文件（由 CLI 文件检查逻辑反推，缺失清单以 CLI 报的为准）。
2. 校验证据（URL、字节数、SHA1/SHA256、签名、下载通道、时间戳）归档到 checkpoint-4。
3. 工具就位后按已批准条件继续：--features custom-protocol 重编译、新外壳 exe SHA/RT_MANIFEST 重绑、
   发布态资源加载实测、30 轮矩阵在最终二进制复跑。
4. 签名 URL 失效（403/超时）→ 回退 Fix B（负责人在代理侧处理），不得改用非官方镜像。
