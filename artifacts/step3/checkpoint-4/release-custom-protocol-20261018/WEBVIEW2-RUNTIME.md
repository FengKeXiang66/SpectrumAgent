# 已打包 WebView2 的版本依据

微软fwlink与CLI自行下载得到同一214,156,024字节文件，SHA256=0625fb5c1e75be58a164e14f95aa58a3e5badb859b3d17c952385f3e4a9ff3e8；Authenticode=Valid，签署者Microsoft Corporation。CLI缓存实际位置为target/.tauri/x64/35871e19-d11b-432d-9d1e-7be0ff286540/MicrosoftEdgeWebView2RuntimeInstallerX64.exe。

外层安装器FileVersion/ProductVersion实测均为 **1.3.287.9**。它不能当作WebView2 Runtime的pv。只读解析已验签安装器的PE资源B/102，用Python标准库LZMA解码，读取其Omaha response XML：appid={F3017226-FE2A-4295-8BDF-00C3A9A7E4C5} 的manifest version为 **155.0.4283.62**；包名MicrosoftEdgeWebview_X64_155.0.4283.62.exe，大小207,695,224，内层SHA256=daf767004075269b786200fdacadb1991ed5b936e6bb636b6d8fb5009e7c6fca。XML原文及解析输出见webview2-runtime-manifest-output.txt。这是已签名离线包元数据证据，不冒充VM已安装版本。

VM实际安装时先记录上述appid对应EdgeUpdate Clients注册表pv，再执行断网安装后读取pv并与 **155.0.4283.62** 核对。若干净底座已经有Runtime且NSIS跳过该段，必须如实记录预存pv/跳过事实，不能声称本离线包已经安装；该情形下首次缺Runtime的安装验证另行安排。安装/版本核对目前仍待VM实机。
