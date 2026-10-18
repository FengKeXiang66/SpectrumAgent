## 完成到哪一步

批准的 Node/npm 工具链复制、10 个 npm 直接包与 4 个 Tauri crate 安装完成。
package-lock.json 与更新后的 Cargo.lock 同笔提交；Python lock 不变。
本报告只确认工具链/依赖，不声明 Tauri 宿主、UI 或 /smoke 已联调。

## 命令与原始输出

Node 24.19.0、npm 10.8.2 使用 E 盘副本。1898 个文件复制前后逐字节 SHA256
一致，源文件复查未变；完整明细见 toolchain-copy-20261018-165421-172398.json。
只改子进程 PATH，npm 两轮 execution JSON 均核实 User/System PATH 未变，strict_ssl=true。
未关闭证书验证；npm 安装两条命令 exit=0，未遇吊销校验错误，未执行升级提示。
E 盘路径与锁指纹见 installation-receipt.json。

实际命令包括 install_frontend_deps.ps1 中两条完整 npm install；
frontend.ps1 run tauri -- add single-instance；cargo fetch --locked（全平台后中止）；
cargo fetch --locked --target x86_64-pc-windows-msvc（exit=0）；以及下列依赖树。

### 复制原文

```text
{
  "mode": "copy",
  "target": "E:\\AI_Agent\\.toolchains\\node24.19.0-npm10.8.2",
  "node_version": "v24.19.0",
  "npm_version": "10.8.2",
  "node_sha256_before": "3602f2bb1a10f2cbab4c36886218a33c1ab3db87290e73b033c46c77147d0237",
  "node_sha256_after": "3602f2bb1a10f2cbab4c36886218a33c1ab3db87290e73b033c46c77147d0237",
  "all_files_equal": true,
  "files": 1898,
  "user_system_PATH_modified": false
}
receipt=E:\AI_Agent\artifacts\step3\checkpoint-3\toolchain-copy-20261018-165421-172398.json

```

### npm runtime install

```text

added 28 packages in 57s
npm notice
npm notice New major version of npm available! 10.8.2 -> 12.2.0
npm notice Changelog: https://github.com/npm/cli/releases/tag/v12.2.0
npm notice To update run: npm install -g npm@12.2.0
npm notice

```

### npm dev install

```text

up to date in 1s

```

### CLI add（包含真实失败，未删节）

```text

> spectrum-agent@0.1.0 tauri
> tauri add single-instance

        Info Installing Cargo dependency "tauri-plugin-single-instance"...
    Updating crates.io index
      Adding tauri-plugin-single-instance v2 to dependencies for target `cfg(not(any(target_os = "android", target_os = "ios")))`
             Features as of v2.0.0:
             - deep-link
             - semver
    Updating crates.io index
     Locking 341 packages to highest Rust 1.99.1 compatible versions
      Adding adler2 v2.0.1
      Adding aho-corasick v1.1.5
      Adding alloc-no-stdlib v3.0.0
      Adding alloc-stdlib v0.3.0
      Adding anyhow v1.0.104
      Adding async-broadcast v0.7.2
      Adding async-channel v2.5.0
      Adding async-executor v1.14.0
      Adding async-io v2.6.0
      Adding async-lock v3.4.2
      Adding async-process v2.5.0
      Adding async-recursion v1.2.0
      Adding async-signal v0.2.14
      Adding async-task v4.7.1
      Adding async-trait v0.1.92
      Adding atk v0.18.2
      Adding atk-sys v0.18.2
      Adding base64 v0.21.7
      Adding base64 v0.22.1
      Adding bit-set v0.8.0
      Adding bit-vec v0.8.0
      Adding bitflags v1.3.2
      Adding block-buffer v0.10.4
      Adding block2 v0.6.2
      Adding blocking v1.7.0
      Adding brotli v9.0.0
      Adding brotli-decompressor v6.0.1 (available: v6.1.0)
      Adding bs58 v0.5.1
      Adding bytemuck v1.25.2
      Adding byteorder v1.5.0
      Adding cairo-rs v0.18.5
      Adding cairo-sys-rs v0.18.2
      Adding camino v1.2.6
      Adding cargo-platform v0.1.9
      Adding cargo_metadata v0.19.2
      Adding cargo_toml v1.0.1
      Adding cesu8 v1.1.0
      Adding cfb v0.14.0
      Adding cfg-expr v0.15.8
      Adding combine v4.6.9
      Adding concurrent-queue v2.5.0
      Adding cookie v0.18.2
      Adding core-foundation v0.10.1
      Adding core-graphics v0.25.0
      Adding core-graphics-types v0.2.0
      Adding cpufeatures v0.2.17
      Adding crc32fast v1.5.2
      Adding crossbeam-channel v0.5.17
      Adding crossbeam-utils v0.8.23
      Adding crypto-common v0.1.7
      Adding cssparser v0.37.0
      Adding cssparser-macros v0.7.1
      Adding ctor v1.0.13
      Adding darling v0.24.1
      Adding darling_core v0.24.1
      Adding darling_macro v0.24.1
      Adding defmt v1.2.0
      Adding defmt-macros v1.2.0
      Adding defmt-parser v1.1.0
      Adding deranged v0.5.9
      Adding derive_more v2.1.1
      Adding derive_more-impl v2.1.1
      Adding digest v0.10.7
      Adding dirs v7.0.0
      Adding dirs-sys v0.5.0
      Adding dispatch2 v0.3.1
      Adding dlopen2 v0.8.2
      Adding dlopen2_derive v0.4.3
      Adding dom_query v0.28.0
      Adding dpi v0.1.2
      Adding dtoa v1.0.11
      Adding dtoa-short v0.3.5
      Adding dunce v1.0.5
      Adding dyn-clone v1.0.20
      Adding embed-resource v3.0.12
      Adding embed_plist v1.2.2
      Adding endi v1.1.1
      Adding enumflags2 v0.7.12
      Adding enumflags2_derive v0.7.12
      Adding equivalent v1.0.3
      Adding erased-serde v0.4.10
      Adding errno v0.3.14
      Adding event-listener v5.4.2
      Adding event-listener-strategy v0.5.4
      Adding fastrand v2.5.0
      Adding fdeflate v0.3.7
      Adding field-offset v0.3.6
      Adding flate2 v1.1.10
      Adding fnv v1.0.7
      Adding foldhash v0.2.0
      Adding foreign-types v0.5.0
      Adding foreign-types-macros v0.2.4
      Adding foreign-types-shared v0.3.1
      Adding futures-executor v0.3.34
      Adding futures-lite v2.6.1
      Adding futures-macro v0.3.34
      Adding gdk v0.18.2
      Adding gdk-pixbuf v0.18.5
      Adding gdk-pixbuf-sys v0.18.0
      Adding gdk-sys v0.18.2
      Adding gdkwayland-sys v0.18.2
      Adding generic-array v0.14.7 (available: v0.14.9)
      Adding getrandom v0.3.4
      Adding getrandom v0.4.3
      Adding gio v0.18.4
      Adding gio-sys v0.18.1
      Adding glib v0.18.5
      Adding glib-macros v0.18.5
      Adding glib-sys v0.18.1
      Adding glob v0.3.4
      Adding gobject-sys v0.18.0
      Adding gtk v0.18.2
      Adding gtk-sys v0.18.2
      Adding gtk3-macros v0.18.2
      Adding hashbrown v0.12.3
      Adding hashbrown v0.17.1
      Adding heck v0.4.1
      Adding heck v0.5.0
      Adding hermit-abi v0.5.3
      Adding hex v0.4.3
      Adding html5ever v0.39.0
      Adding ico v0.5.0
      Adding ident_case v1.0.1
      Adding indexmap v1.9.3
      Adding indexmap v2.14.2
      Adding infer v0.22.0
      Adding is-docker v0.2.0
      Adding is-wsl v0.4.0
      Adding javascriptcore-rs v1.1.2
      Adding javascriptcore-rs-sys v1.1.1
      Adding jiff v0.2.38
      Adding jiff-core v0.1.1
      Adding jiff-static v0.2.38
      Adding jiff-tzdb v0.1.9
      Adding jiff-tzdb-platform v0.1.3
      Adding jni v0.21.1
      Adding jni-sys v0.3.1
      Adding jni-sys v0.4.1
      Adding jni-sys-macros v0.4.1
      Adding json-patch v4.2.0
      Adding jsonptr v0.7.1
      Adding keyboard-types v0.8.3
      Adding libappindicator v0.9.0
      Adding libappindicator-sys v0.9.0
      Adding libloading v0.7.4
      Adding libredox v0.1.25
      Adding linux-raw-sys v0.12.1
      Adding lock_api v0.4.14
      Adding markup5ever v0.39.0
      Adding memoffset v0.9.1
      Adding mime v0.3.17
      Adding miniz_oxide v0.8.9
      Adding miniz_oxide v0.9.1
      Adding muda v0.20.0
      Adding ndk v0.9.0
      Adding ndk-context v0.1.1
      Adding ndk-sys v0.6.0+11769913
      Adding new_debug_unreachable v1.0.6
      Adding num-conv v0.2.2
      Adding num_enum v0.7.6
      Adding num_enum_derive v0.7.6
      Adding objc2 v0.6.5
      Adding objc2-app-kit v0.3.2
      Adding objc2-cloud-kit v0.3.2
      Adding objc2-core-data v0.3.2
      Adding objc2-core-foundation v0.3.2
      Adding objc2-core-graphics v0.3.2
      Adding objc2-core-image v0.3.2
      Adding objc2-core-location v0.3.2
      Adding objc2-core-text v0.3.2
      Adding objc2-encode v4.1.0
      Adding objc2-exception-helper v0.1.1
      Adding objc2-foundation v0.3.2
      Adding objc2-io-surface v0.3.2
      Adding objc2-quartz-core v0.3.2
      Adding objc2-ui-kit v0.3.2
      Adding objc2-user-notifications v0.3.2
      Adding objc2-web-kit v0.3.2
      Adding open v5.4.4
      Adding option-ext v0.2.0
      Adding ordered-stream v0.2.0
      Adding pango v0.18.3
      Adding pango-sys v0.18.0
      Adding parking v2.2.1
      Adding parking_lot v0.12.5
      Adding parking_lot_core v0.9.12
      Adding phf v0.13.1
      Adding phf_codegen v0.13.1
      Adding phf_generator v0.13.1
      Adding phf_macros v0.13.1
      Adding phf_shared v0.13.1
      Adding piper v0.2.5
      Adding pkg-config v0.3.34
      Adding plist v1.10.1
      Adding png v0.17.16
      Adding png v0.18.1
      Adding polling v3.11.0
      Adding portable-atomic v1.15.0
      Adding portable-atomic-util v0.2.8
      Adding powerfmt v0.2.1
      Adding precomputed-hash v0.1.1
      Adding proc-macro-crate v1.3.1
      Adding proc-macro-crate v2.0.2
      Adding proc-macro-crate v3.5.0
      Adding proc-macro-error v1.0.4
      Adding proc-macro-error-attr v1.0.4
      Adding quick-xml v0.42.0
      Adding r-efi v5.3.0
      Adding r-efi v6.0.0
      Adding raw-window-handle v0.6.2
      Adding redox_syscall v0.5.18
      Adding redox_users v0.5.3
      Adding ref-cast v1.0.27
      Adding ref-cast-impl v1.0.27
      Adding regex v1.13.1
      Adding regex-automata v0.4.18
      Adding regex-syntax v0.8.11
      Adding rustc-hash v2.1.3
      Adding rustc_version v0.4.1
      Adding rustix v1.1.5
      Adding same-file v1.0.6
      Adding schemars v0.8.22
      Adding schemars v0.9.0
      Adding schemars v1.2.3
      Adding schemars_derive v0.8.22
      Adding scopeguard v1.2.0
      Adding selectors v0.38.0
      Adding semver v1.0.28
      Adding serde-untagged v0.1.9
      Adding serde_derive_internals v0.29.1
      Adding serde_repr v0.1.21
      Adding serde_spanned v0.6.9
      Adding serde_spanned v1.1.2
      Adding serde_with v3.24.0
      Adding serde_with_macros v3.24.0
      Adding serialize-to-javascript v0.1.2
      Adding serialize-to-javascript-impl v0.1.2
      Adding servo_arc v0.4.3
      Adding sha2 v0.10.9
      Adding signal-hook-registry v1.4.8
      Adding simd-adler32 v0.3.10
      Adding siphasher v1.0.4
      Adding softbuffer v0.4.8
      Adding soup3 v0.5.0
      Adding soup3-sys v0.5.0
      Adding static_vcruntime v3.0.0
      Adding string_cache v0.9.0
      Adding string_cache_codegen v0.6.1
      Adding strsim v0.11.1
      Adding swift-rs v1.0.9
      Adding syn v1.0.109
      Adding system-deps v6.2.2
      Adding tao v0.37.1
      Adding tao-macros v0.1.4
      Adding target-lexicon v0.12.16
      Adding tauri v2.12.4
      Adding tauri-build v2.7.3
      Adding tauri-codegen v2.7.3
      Adding tauri-macros v2.7.3
      Adding tauri-plugin v2.7.2
      Adding tauri-plugin-opener v2.7.2
      Adding tauri-plugin-single-instance v2.5.4
      Adding tauri-runtime v2.12.2
      Adding tauri-runtime-wry v2.12.2
      Adding tauri-utils v2.10.2
      Adding tauri-winres v0.3.6
      Adding tempfile v3.27.0
      Adding tendril v0.5.1
      Adding thiserror v1.0.69
      Adding thiserror v2.0.21
      Adding thiserror-impl v1.0.69
      Adding thiserror-impl v2.0.21
      Adding time v0.3.55
      Adding time-core v0.1.9
      Adding time-macros v0.2.32
      Adding tinyvec v1.13.3
      Adding tokio-util v0.7.20
      Adding toml v0.8.2 (available: v0.8.23)
      Adding toml v1.1.8+spec-1.1.0
      Adding toml_datetime v0.6.3 (available: v0.6.11)
      Adding toml_datetime v1.1.2+spec-1.1.0
      Adding toml_edit v0.19.15
      Adding toml_edit v0.20.2 (available: v0.20.7)
      Adding toml_edit v0.25.17+spec-1.1.0
      Adding toml_parser v1.1.5+spec-1.1.0
      Adding toml_writer v1.1.3+spec-1.1.0
      Adding tracing-attributes v0.1.31
      Adding tray-icon v0.25.1
      Adding typeid v1.0.3
      Adding typenum v1.20.1
      Adding uds_windows v1.2.1
      Adding unicode-segmentation v1.13.3
      Adding urlpattern v0.6.0
      Adding uuid v1.28.0
      Adding version-compare v0.2.1
      Adding version_check v0.9.5
      Adding vswhom v0.1.0
      Adding vswhom-sys v0.1.3
      Adding walkdir v2.5.0
      Adding wasip2 v1.0.4+wasi-0.2.12
      Adding wasm-streams v0.5.0
      Adding web-time v1.1.0
      Adding web_atoms v0.2.6
      Adding webkit2gtk v2.0.2
      Adding webkit2gtk-sys v2.0.2
      Adding webview2-com v0.39.1
      Adding webview2-com-macros v0.8.1
      Adding webview2-com-sys v0.39.1
      Adding winapi v0.3.9
      Adding winapi-i686-pc-windows-gnu v0.4.0
      Adding winapi-util v0.1.11
      Adding winapi-x86_64-pc-windows-gnu v0.4.0
      Adding window-vibrancy v0.8.1
      Adding windows v0.62.2
      Adding windows-collections v0.3.2
      Adding windows-future v0.3.2
      Adding windows-numerics v0.3.1
      Adding windows-sys v0.45.0
      Adding windows-targets v0.42.2
      Adding windows-threading v0.2.1
      Adding windows-version v0.1.7
      Adding windows_aarch64_gnullvm v0.42.2
      Adding windows_aarch64_msvc v0.42.2
      Adding windows_i686_gnu v0.42.2
      Adding windows_i686_msvc v0.42.2
      Adding windows_x86_64_gnu v0.42.2
      Adding windows_x86_64_gnullvm v0.42.2
      Adding windows_x86_64_msvc v0.42.2
      Adding winnow v0.5.40
      Adding winnow v1.0.4
      Adding winreg v0.56.0
      Adding wit-bindgen v0.57.1
      Adding wry v0.57.0
      Adding zbus v5.19.0
      Adding zbus_macros v5.19.0
      Adding zbus_names v4.3.5
      Adding zcheapstr v1.1.0
      Adding zlib-rs v0.6.8
      Adding zvariant v5.15.1
      Adding zvariant_derive v5.15.1
      Adding zvariant_utils v4.2.0
failed to read Rust entry point E:\AI_Agent\src-tauri\src/main.rs: 系统找不到指定的文件。 (os error 2)
       Error failed to read Rust entry point E:\AI_Agent\src-tauri\src/main.rs: 系统找不到指定的文件。 (os error 2)

```

### 实际解析版本

```text
Cargo.lock tauri-plugin-single-instance=['2.5.4']

```

### Windows fetch

```text
 Downloading crates ...
  Downloaded webview2-com-sys v0.39.1
  Downloaded windows v0.62.2

```

### npm ls --all（exit=0）

```text
spectrum-agent@0.1.0 E:\AI_Agent
├── @tauri-apps/api@2.12.4
├─┬ @tauri-apps/cli@2.12.3
│ ├── UNMET OPTIONAL DEPENDENCY @tauri-apps/cli-darwin-arm64@2.12.3
│ ├── UNMET OPTIONAL DEPENDENCY @tauri-apps/cli-darwin-x64@2.12.3
│ ├── UNMET OPTIONAL DEPENDENCY @tauri-apps/cli-linux-arm-gnueabihf@2.12.3
│ ├── UNMET OPTIONAL DEPENDENCY @tauri-apps/cli-linux-arm64-gnu@2.12.3
│ ├── UNMET OPTIONAL DEPENDENCY @tauri-apps/cli-linux-arm64-musl@2.12.3
│ ├── UNMET OPTIONAL DEPENDENCY @tauri-apps/cli-linux-riscv64-gnu@2.12.3
│ ├── UNMET OPTIONAL DEPENDENCY @tauri-apps/cli-linux-x64-gnu@2.12.3
│ ├── UNMET OPTIONAL DEPENDENCY @tauri-apps/cli-linux-x64-musl@2.12.3
│ ├── UNMET OPTIONAL DEPENDENCY @tauri-apps/cli-win32-arm64-msvc@2.12.3
│ ├── UNMET OPTIONAL DEPENDENCY @tauri-apps/cli-win32-ia32-msvc@2.12.3
│ └── @tauri-apps/cli-win32-x64-msvc@2.12.3
├─┬ @types/node@24.10.1
│ └── undici-types@7.16.0
├─┬ @types/react-dom@19.3.0
│ └── @types/react@19.3.0 deduped
├─┬ @types/react@19.3.0
│ └── csstype@3.2.3
├─┬ @vitejs/plugin-react@6.1.2
│ ├── UNMET OPTIONAL DEPENDENCY @rolldown/plugin-babel@^0.1.7 || ^0.2.0
│ ├── @rolldown/pluginutils@1.0.1
│ ├── UNMET OPTIONAL DEPENDENCY babel-plugin-react-compiler@^1.0.0
│ ├── UNMET OPTIONAL DEPENDENCY oxc-transform-react@^0.152.0
│ └── vite@8.3.4 deduped
├─┬ react-dom@19.3.1
│ ├── react@19.3.1 deduped
│ └── scheduler@0.28.0
├── react@19.3.1
├── typescript@5.9.3
└─┬ vite@8.3.4
  ├── @types/node@24.10.1 deduped
  ├── UNMET OPTIONAL DEPENDENCY @vitejs/devtools@^0.7.1
  ├── UNMET OPTIONAL DEPENDENCY esbuild@^0.27.0 || ^0.28.0
  ├── UNMET OPTIONAL DEPENDENCY fsevents@~2.3.3
  ├── UNMET OPTIONAL DEPENDENCY jiti@>=1.21.0
  ├── UNMET OPTIONAL DEPENDENCY less@^4.0.0
  ├─┬ lightningcss@1.33.0
  │ ├── detect-libc@2.1.2
  │ ├── UNMET OPTIONAL DEPENDENCY lightningcss-android-arm64@1.33.0
  │ ├── UNMET OPTIONAL DEPENDENCY lightningcss-darwin-arm64@1.33.0
  │ ├── UNMET OPTIONAL DEPENDENCY lightningcss-darwin-x64@1.33.0
  │ ├── UNMET OPTIONAL DEPENDENCY lightningcss-freebsd-x64@1.33.0
  │ ├── UNMET OPTIONAL DEPENDENCY lightningcss-linux-arm-gnueabihf@1.33.0
  │ ├── UNMET OPTIONAL DEPENDENCY lightningcss-linux-arm64-gnu@1.33.0
  │ ├── UNMET OPTIONAL DEPENDENCY lightningcss-linux-arm64-musl@1.33.0
  │ ├── UNMET OPTIONAL DEPENDENCY lightningcss-linux-x64-gnu@1.33.0
  │ ├── UNMET OPTIONAL DEPENDENCY lightningcss-linux-x64-musl@1.33.0
  │ ├── UNMET OPTIONAL DEPENDENCY lightningcss-win32-arm64-msvc@1.33.0
  │ └── lightningcss-win32-x64-msvc@1.33.0
  ├── picomatch@4.0.7
  ├─┬ postcss@8.5.30
  │ ├── nanoid@3.3.20
  │ ├── picocolors@1.1.1
  │ └── source-map-js@1.2.2
  ├─┬ rolldown@1.2.14
  │ ├── @oxc-project/types@0.154.0
  │ ├── UNMET OPTIONAL DEPENDENCY @rolldown/binding-android-arm-eabi@1.2.14
  │ ├── UNMET OPTIONAL DEPENDENCY @rolldown/binding-android-arm64@1.2.14
  │ ├── UNMET OPTIONAL DEPENDENCY @rolldown/binding-darwin-arm64@1.2.14
  │ ├── UNMET OPTIONAL DEPENDENCY @rolldown/binding-darwin-x64@1.2.14
  │ ├── UNMET OPTIONAL DEPENDENCY @rolldown/binding-freebsd-x64@1.2.14
  │ ├── UNMET OPTIONAL DEPENDENCY @rolldown/binding-linux-arm-gnueabihf@1.2.14
  │ ├── UNMET OPTIONAL DEPENDENCY @rolldown/binding-linux-arm64-gnu@1.2.14
  │ ├── UNMET OPTIONAL DEPENDENCY @rolldown/binding-linux-arm64-musl@1.2.14
  │ ├── UNMET OPTIONAL DEPENDENCY @rolldown/binding-linux-ppc64-gnu@1.2.14
  │ ├── UNMET OPTIONAL DEPENDENCY @rolldown/binding-linux-s390x-gnu@1.2.14
  │ ├── UNMET OPTIONAL DEPENDENCY @rolldown/binding-linux-x64-gnu@1.2.14
  │ ├── UNMET OPTIONAL DEPENDENCY @rolldown/binding-linux-x64-musl@1.2.14
  │ ├── UNMET OPTIONAL DEPENDENCY @rolldown/binding-openharmony-arm64@1.2.14
  │ ├── UNMET OPTIONAL DEPENDENCY @rolldown/binding-win32-arm64-msvc@1.2.14
  │ ├── @rolldown/binding-win32-x64-msvc@1.2.14
  │ └── @rolldown/pluginutils@1.0.1 deduped
  ├── UNMET OPTIONAL DEPENDENCY sass-embedded@^1.70.0
  ├── UNMET OPTIONAL DEPENDENCY sass@^1.70.0
  ├── UNMET OPTIONAL DEPENDENCY stylus@>=0.54.8
  ├── UNMET OPTIONAL DEPENDENCY sugarss@^5.0.0
  ├── UNMET OPTIONAL DEPENDENCY terser@^5.16.0
  ├─┬ tinyglobby@0.2.17
  │ ├─┬ fdir@6.5.0
  │ │ └── picomatch@4.0.7 deduped
  │ └── picomatch@4.0.7 deduped
  ├── UNMET OPTIONAL DEPENDENCY tsx@^4.8.1
  └── UNMET OPTIONAL DEPENDENCY yaml@^2.4.2


```

### cargo tree --locked --offline --target x86_64-pc-windows-msvc（exit=0）

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
│   │   │   ├── bytes v1.12.1
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
│   │       ├── tracing-attributes v0.1.31 (proc-macro)
│   │       │   ├── proc-macro2 v1.0.107
│   │       │   │   └── unicode-ident v1.0.27
│   │       │   ├── quote v1.0.47
│   │       │   │   └── proc-macro2 v1.0.107 (*)
│   │       │   └── syn v2.0.119
│   │       │       ├── proc-macro2 v1.0.107 (*)
│   │       │       ├── quote v1.0.47 (*)
│   │       │       └── unicode-ident v1.0.27
│   │       └── tracing-core v0.1.36
│   │           └── once_cell v1.21.4
│   ├── log v0.4.34
│   ├── percent-encoding v2.3.2
│   ├── pin-project-lite v0.2.17
│   ├── serde v1.0.229
│   │   ├── serde_core v1.0.229
│   │   └── serde_derive v1.0.229 (proc-macro)
│   │       ├── proc-macro2 v1.0.107 (*)
│   │       ├── quote v1.0.47 (*)
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
│   │   │   └── serde_core v1.0.229
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
│   │       ├── percent-encoding v2.3.2
│   │       ├── serde v1.0.229 (*)
│   │       └── serde_derive v1.0.229 (proc-macro) (*)
│   ├── tower-service v0.3.3
│   └── url v2.5.8 (*)
├── serde v1.0.229 (*)
├── serde_json v1.0.154 (*)
├── tauri v2.12.4
│   ├── anyhow v1.0.104
│   ├── cookie v0.18.2
│   │   └── time v0.3.55
│   │       ├── deranged v0.5.9
│   │       ├── num-conv v0.2.2
│   │       ├── powerfmt v0.2.1
│   │       ├── time-core v0.1.9
│   │       └── time-macros v0.2.32 (proc-macro)
│   │           ├── num-conv v0.2.2
│   │           └── time-core v0.1.9
│   │   [build-dependencies]
│   │   └── version_check v0.9.5
│   ├── dirs v7.0.0
│   │   └── dirs-sys v0.5.0
│   │       ├── option-ext v0.2.0
│   │       └── windows-sys v0.61.2 (*)
│   ├── dunce v1.0.5
│   ├── getrandom v0.3.4
│   │   └── cfg-if v1.0.5
│   ├── glob v0.3.4
│   ├── heck v0.5.0
│   ├── http v1.5.0 (*)
│   ├── log v0.4.34
│   ├── mime v0.3.17
│   ├── muda v0.20.0
│   │   ├── crossbeam-channel v0.5.17
│   │   │   └── crossbeam-utils v0.8.23
│   │   ├── dpi v0.1.2
│   │   │   └── serde v1.0.229 (*)
│   │   ├── keyboard-types v0.8.3
│   │   │   ├── bitflags v2.13.2 (*)
│   │   │   └── serde v1.0.229 (*)
│   │   ├── once_cell v1.21.4
│   │   ├── serde v1.0.229 (*)
│   │   ├── thiserror v2.0.21
│   │   │   └── thiserror-impl v2.0.21 (proc-macro)
│   │   │       ├── proc-macro2 v1.0.107 (*)
│   │   │       ├── quote v1.0.47 (*)
│   │   │       └── syn v3.0.9 (*)
│   │   └── windows-sys v0.61.2 (*)
│   ├── percent-encoding v2.3.2
│   ├── raw-window-handle v0.6.2
│   ├── serde v1.0.229 (*)
│   ├── serde_json v1.0.154 (*)
│   ├── serde_repr v0.1.21 (proc-macro)
│   │   ├── proc-macro2 v1.0.107 (*)
│   │   ├── quote v1.0.47 (*)
│   │   └── syn v3.0.9 (*)
│   ├── serialize-to-javascript v0.1.2
│   │   ├── serde v1.0.229 (*)
│   │   ├── serde_json v1.0.154 (*)
│   │   └── serialize-to-javascript-impl v0.1.2 (proc-macro)
│   │       ├── proc-macro2 v1.0.107 (*)
│   │       ├── quote v1.0.47 (*)
│   │       └── syn v2.0.119 (*)
│   ├── tauri-macros v2.7.3 (proc-macro)
│   │   ├── heck v0.5.0
│   │   ├── proc-macro2 v1.0.107 (*)
│   │   ├── quote v1.0.47 (*)
│   │   ├── syn v2.0.119 (*)
│   │   ├── tauri-codegen v2.7.3
│   │   │   ├── base64 v0.23.1
│   │   │   ├── brotli v9.0.0
│   │   │   │   ├── alloc-no-stdlib v3.0.0
│   │   │   │   ├── alloc-stdlib v0.3.0
│   │   │   │   │   └── alloc-no-stdlib v3.0.0
│   │   │   │   └── brotli-decompressor v6.0.1
│   │   │   │       ├── alloc-no-stdlib v3.0.0
│   │   │   │       └── alloc-stdlib v0.3.0 (*)
│   │   │   ├── ico v0.5.0
│   │   │   │   ├── byteorder v1.5.0
│   │   │   │   └── png v0.17.16
│   │   │   │       ├── bitflags v1.3.2
│   │   │   │       ├── crc32fast v1.5.2
│   │   │   │       │   └── cfg-if v1.0.5
│   │   │   │       ├── fdeflate v0.3.7
│   │   │   │       │   └── simd-adler32 v0.3.10
│   │   │   │       ├── flate2 v1.1.10
│   │   │   │       │   ├── crc32fast v1.5.2 (*)
│   │   │   │       │   └── miniz_oxide v0.9.1
│   │   │   │       │       ├── adler2 v2.0.1
│   │   │   │       │       └── simd-adler32 v0.3.10
│   │   │   │       └── miniz_oxide v0.8.9
│   │   │   │           ├── adler2 v2.0.1
│   │   │   │           └── simd-adler32 v0.3.10
│   │   │   ├── json-patch v4.2.0
│   │   │   │   ├── jsonptr v0.7.1
│   │   │   │   │   ├── serde v1.0.229
│   │   │   │   │   │   ├── serde_core v1.0.229
│   │   │   │   │   │   └── serde_derive v1.0.229 (proc-macro) (*)
│   │   │   │   │   └── serde_json v1.0.154
│   │   │   │   │       ├── itoa v1.0.18
│   │   │   │   │       ├── memchr v2.8.3
│   │   │   │   │       ├── serde_core v1.0.229
│   │   │   │   │       └── zmij v1.0.23
│   │   │   │   ├── serde v1.0.229 (*)
│   │   │   │   ├── serde_json v1.0.154 (*)
│   │   │   │   └── thiserror v2.0.21
│   │   │   │       └── thiserror-impl v2.0.21 (proc-macro) (*)
│   │   │   ├── png v0.18.1
│   │   │   │   ├── bitflags v2.13.2
│   │   │   │   ├── crc32fast v1.5.2 (*)
│   │   │   │   ├── fdeflate v0.3.7 (*)
│   │   │   │   ├── flate2 v1.1.10 (*)
│   │   │   │   └── miniz_oxide v0.8.9 (*)
│   │   │   ├── proc-macro2 v1.0.107 (*)
│   │   │   ├── quote v1.0.47 (*)
│   │   │   ├── semver v1.0.28
│   │   │   │   └── serde_core v1.0.229
│   │   │   ├── serde v1.0.229 (*)
│   │   │   ├── serde_json v1.0.154 (*)
│   │   │   ├── sha2 v0.10.9
│   │   │   │   ├── cfg-if v1.0.5
│   │   │   │   ├── cpufeatures v0.2.17
│   │   │   │   └── digest v0.10.7
│   │   │   │       ├── block-buffer v0.10.4
│   │   │   │       │   └── generic-array v0.14.7
│   │   │   │       │       └── typenum v1.20.1
│   │   │   │       │       [build-dependencies]
│   │   │   │       │       └── version_check v0.9.5
│   │   │   │       └── crypto-common v0.1.7
│   │   │   │           ├── generic-array v0.14.7 (*)
│   │   │   │           └── typenum v1.20.1
│   │   │   ├── syn v2.0.119 (*)
│   │   │   ├── tauri-utils v2.10.2
│   │   │   │   ├── anyhow v1.0.104
│   │   │   │   ├── brotli v9.0.0 (*)
│   │   │   │   ├── cargo_metadata v0.19.2
│   │   │   │   │   ├── camino v1.2.6
│   │   │   │   │   │   └── serde_core v1.0.229
│   │   │   │   │   ├── cargo-platform v0.1.9
│   │   │   │   │   │   └── serde v1.0.229 (*)
│   │   │   │   │   ├── semver v1.0.28 (*)
│   │   │   │   │   ├── serde v1.0.229 (*)
│   │   │   │   │   ├── serde_json v1.0.154 (*)
│   │   │   │   │   └── thiserror v2.0.21 (*)
│   │   │   │   ├── ctor v1.0.13
│   │   │   │   ├── dom_query v0.28.0
│   │   │   │   │   ├── bit-set v0.8.0
│   │   │   │   │   │   └── bit-vec v0.8.0
│   │   │   │   │   ├── cssparser v0.37.0
│   │   │   │   │   │   ├── cssparser-macros v0.7.1 (proc-macro)
│   │   │   │   │   │   │   ├── quote v1.0.47 (*)
│   │   │   │   │   │   │   └── syn v3.0.9 (*)
│   │   │   │   │   │   ├── dtoa-short v0.3.5
│   │   │   │   │   │   │   └── dtoa v1.0.11
│   │   │   │   │   │   ├── itoa v1.0.18
│   │   │   │   │   │   ├── phf v0.13.1
│   │   │   │   │   │   │   ├── phf_macros v0.13.1 (proc-macro)
│   │   │   │   │   │   │   │   ├── phf_generator v0.13.1
│   │   │   │   │   │   │   │   │   ├── fastrand v2.5.0
│   │   │   │   │   │   │   │   │   └── phf_shared v0.13.1
│   │   │   │   │   │   │   │   │       └── siphasher v1.0.4
│   │   │   │   │   │   │   │   ├── phf_shared v0.13.1 (*)
│   │   │   │   │   │   │   │   ├── proc-macro2 v1.0.107 (*)
│   │   │   │   │   │   │   │   ├── quote v1.0.47 (*)
│   │   │   │   │   │   │   │   └── syn v2.0.119 (*)
│   │   │   │   │   │   │   └── phf_shared v0.13.1 (*)
│   │   │   │   │   │   └── smallvec v1.16.3
│   │   │   │   │   ├── foldhash v0.2.0
│   │   │   │   │   ├── html5ever v0.39.0
│   │   │   │   │   │   ├── log v0.4.34
│   │   │   │   │   │   └── markup5ever v0.39.0
│   │   │   │   │   │       ├── log v0.4.34
│   │   │   │   │   │       ├── tendril v0.5.1
│   │   │   │   │   │       │   └── new_debug_unreachable v1.0.6
│   │   │   │   │   │       └── web_atoms v0.2.6
│   │   │   │   │   │           ├── phf v0.13.1 (*)
│   │   │   │   │   │           └── string_cache v0.9.0
│   │   │   │   │   │               ├── new_debug_unreachable v1.0.6
│   │   │   │   │   │               ├── parking_lot v0.12.5
│   │   │   │   │   │               │   ├── lock_api v0.4.14
│   │   │   │   │   │               │   │   └── scopeguard v1.2.0
│   │   │   │   │   │               │   └── parking_lot_core v0.9.12
│   │   │   │   │   │               │       ├── cfg-if v1.0.5
│   │   │   │   │   │               │       ├── smallvec v1.16.3
│   │   │   │   │   │               │       └── windows-link v0.2.1
│   │   │   │   │   │               ├── phf_shared v0.13.1 (*)
│   │   │   │   │   │               └── precomputed-hash v0.1.1
│   │   │   │   │   │           [build-dependencies]
│   │   │   │   │   │           ├── phf_codegen v0.13.1
│   │   │   │   │   │           │   ├── phf_generator v0.13.1 (*)
│   │   │   │   │   │           │   └── phf_shared v0.13.1 (*)
│   │   │   │   │   │           └── string_cache_codegen v0.6.1
│   │   │   │   │   │               ├── phf_generator v0.13.1 (*)
│   │   │   │   │   │               ├── phf_shared v0.13.1 (*)
│   │   │   │   │   │               ├── proc-macro2 v1.0.107 (*)
│   │   │   │   │   │               └── quote v1.0.47 (*)
│   │   │   │   │   ├── precomputed-hash v0.1.1
│   │   │   │   │   ├── selectors v0.38.0
│   │   │   │   │   │   ├── bitflags v2.13.2
│   │   │   │   │   │   ├── cssparser v0.37.0 (*)
│   │   │   │   │   │   ├── derive_more v2.1.1
│   │   │   │   │   │   │   └── derive_more-impl v2.1.1 (proc-macro)
│   │   │   │   │   │   │       ├── proc-macro2 v1.0.107 (*)
│   │   │   │   │   │   │       ├── quote v1.0.47 (*)
│   │   │   │   │   │   │       └── syn v2.0.119 (*)
│   │   │   │   │   │   │       [build-dependencies]
│   │   │   │   │   │   │       └── rustc_version v0.4.1
│   │   │   │   │   │   │           └── semver v1.0.28 (*)
│   │   │   │   │   │   ├── log v0.4.34
│   │   │   │   │   │   ├── new_debug_unreachable v1.0.6
│   │   │   │   │   │   ├── phf v0.13.1 (*)
│   │   │   │   │   │   ├── precomputed-hash v0.1.1
│   │   │   │   │   │   ├── rustc-hash v2.1.3
│   │   │   │   │   │   ├── servo_arc v0.4.3
│   │   │   │   │   │   │   └── stable_deref_trait v1.2.1
│   │   │   │   │   │   └── smallvec v1.16.3
│   │   │   │   │   │   [build-dependencies]
│   │   │   │   │   │   └── phf_codegen v0.13.1 (*)
│   │   │   │   │   └── tendril v0.5.1 (*)
│   │   │   │   ├── dunce v1.0.5
│   │   │   │   ├── glob v0.3.4
│   │   │   │   ├── http v1.5.0
│   │   │   │   │   ├── bytes v1.12.1
│   │   │   │   │   └── itoa v1.0.18
│   │   │   │   ├── infer v0.22.0
│   │   │   │   │   └── cfb v0.14.0
│   │   │   │   │       ├── fnv v1.0.7
│   │   │   │   │       ├── uuid v1.28.0
│   │   │   │   │       │   ├── getrandom v0.4.3
│   │   │   │   │       │   │   └── cfg-if v1.0.5
│   │   │   │   │       │   └── serde_core v1.0.229
│   │   │   │   │       └── web-time v1.1.0
│   │   │   │   ├── json-patch v4.2.0 (*)
│   │   │   │   ├── log v0.4.34
│   │   │   │   ├── memchr v2.8.3
│   │   │   │   ├── phf v0.13.1 (*)
│   │   │   │   ├── plist v1.10.1
│   │   │   │   │   ├── base64 v0.23.1
│   │   │   │   │   ├── indexmap v2.14.2
│   │   │   │   │   │   ├── equivalent v1.0.3
│   │   │   │   │   │   └── hashbrown v0.17.1
│   │   │   │   │   ├── quick-xml v0.42.0
│   │   │   │   │   │   └── memchr v2.8.3
│   │   │   │   │   ├── serde v1.0.229 (*)
│   │   │   │   │   └── time v0.3.55
│   │   │   │   │       ├── deranged v0.5.9
│   │   │   │   │       ├── num-conv v0.2.2
│   │   │   │   │       ├── powerfmt v0.2.1
│   │   │   │   │       └── time-core v0.1.9
│   │   │   │   ├── proc-macro2 v1.0.107 (*)
│   │   │   │   ├── quote v1.0.47 (*)
│   │   │   │   ├── regex v1.13.1
│   │   │   │   │   ├── aho-corasick v1.1.5
│   │   │   │   │   │   └── memchr v2.8.3
│   │   │   │   │   ├── memchr v2.8.3
│   │   │   │   │   ├── regex-automata v0.4.18
│   │   │   │   │   │   ├── aho-corasick v1.1.5 (*)
│   │   │   │   │   │   ├── memchr v2.8.3
│   │   │   │   │   │   └── regex-syntax v0.8.11
│   │   │   │   │   └── regex-syntax v0.8.11
│   │   │   │   ├── schemars v0.8.22
│   │   │   │   │   ├── dyn-clone v1.0.20
│   │   │   │   │   ├── indexmap v1.9.3
│   │   │   │   │   │   ├── hashbrown v0.12.3
│   │   │   │   │   │   └── serde v1.0.229 (*)
│   │   │   │   │   │   [build-dependencies]
│   │   │   │   │   │   └── autocfg v1.5.1
│   │   │   │   │   ├── schemars_derive v0.8.22 (proc-macro)
│   │   │   │   │   │   ├── proc-macro2 v1.0.107 (*)
│   │   │   │   │   │   ├── quote v1.0.47 (*)
│   │   │   │   │   │   ├── serde_derive_internals v0.29.1
│   │   │   │   │   │   │   ├── proc-macro2 v1.0.107 (*)
│   │   │   │   │   │   │   ├── quote v1.0.47 (*)
│   │   │   │   │   │   │   └── syn v2.0.119 (*)
│   │   │   │   │   │   └── syn v2.0.119 (*)
│   │   │   │   │   ├── serde v1.0.229 (*)
│   │   │   │   │   ├── serde_json v1.0.154 (*)
│   │   │   │   │   ├── url v2.5.8
│   │   │   │   │   │   ├── form_urlencoded v1.2.2
│   │   │   │   │   │   │   └── percent-encoding v2.3.2
│   │   │   │   │   │   ├── idna v1.1.0
│   │   │   │   │   │   │   ├── idna_adapter v1.2.2
│   │   │   │   │   │   │   │   ├── icu_normalizer v2.3.0
│   │   │   │   │   │   │   │   │   ├── icu_collections v2.3.0
│   │   │   │   │   │   │   │   │   │   ├── displaydoc v0.2.7 (proc-macro) (*)
│   │   │   │   │   │   │   │   │   │   ├── potential_utf v0.1.6
│   │   │   │   │   │   │   │   │   │   │   └── zerovec v0.11.8
│   │   │   │   │   │   │   │   │   │   │       ├── yoke v0.8.3
│   │   │   │   │   │   │   │   │   │   │       │   ├── stable_deref_trait v1.2.1
│   │   │   │   │   │   │   │   │   │   │       │   ├── yoke-derive v0.8.4 (proc-macro) (*)
│   │   │   │   │   │   │   │   │   │   │       │   └── zerofrom v0.1.8
│   │   │   │   │   │   │   │   │   │   │       │       └── zerofrom-derive v0.1.8 (proc-macro) (*)
│   │   │   │   │   │   │   │   │   │   │       ├── zerofrom v0.1.8 (*)
│   │   │   │   │   │   │   │   │   │   │       └── zerovec-derive v0.11.6 (proc-macro) (*)
│   │   │   │   │   │   │   │   │   │   ├── utf8_iter v1.0.4
│   │   │   │   │   │   │   │   │   │   ├── yoke v0.8.3 (*)
│   │   │   │   │   │   │   │   │   │   ├── zerofrom v0.1.8 (*)
│   │   │   │   │   │   │   │   │   │   └── zerovec v0.11.8 (*)
│   │   │   │   │   │   │   │   │   ├── icu_normalizer_data v2.3.0
│   │   │   │   │   │   │   │   │   ├── icu_provider v2.3.1
│   │   │   │   │   │   │   │   │   │   ├── displaydoc v0.2.7 (proc-macro) (*)
│   │   │   │   │   │   │   │   │   │   ├── icu_locale_core v2.3.0
│   │   │   │   │   │   │   │   │   │   │   ├── displaydoc v0.2.7 (proc-macro) (*)
│   │   │   │   │   │   │   │   │   │   │   ├── litemap v0.8.3
│   │   │   │   │   │   │   │   │   │   │   ├── tinystr v0.8.4
│   │   │   │   │   │   │   │   │   │   │   │   ├── displaydoc v0.2.7 (proc-macro) (*)
│   │   │   │   │   │   │   │   │   │   │   │   └── zerovec v0.11.8 (*)
│   │   │   │   │   │   │   │   │   │   │   ├── writeable v0.6.4
│   │   │   │   │   │   │   │   │   │   │   └── zerovec v0.11.8 (*)
│   │   │   │   │   │   │   │   │   │   ├── writeable v0.6.4
│   │   │   │   │   │   │   │   │   │   ├── yoke v0.8.3 (*)
│   │   │   │   │   │   │   │   │   │   ├── zerofrom v0.1.8 (*)
│   │   │   │   │   │   │   │   │   │   ├── zerotrie v0.2.5
│   │   │   │   │   │   │   │   │   │   │   ├── displaydoc v0.2.7 (proc-macro) (*)
│   │   │   │   │   │   │   │   │   │   │   ├── yoke v0.8.3 (*)
│   │   │   │   │   │   │   │   │   │   │   └── zerofrom v0.1.8 (*)
│   │   │   │   │   │   │   │   │   │   └── zerovec v0.11.8 (*)
│   │   │   │   │   │   │   │   │   ├── smallvec v1.16.3
│   │   │   │   │   │   │   │   │   └── zerovec v0.11.8 (*)
│   │   │   │   │   │   │   │   └── icu_properties v2.3.0
│   │   │   │   │   │   │   │       ├── displaydoc v0.2.7 (proc-macro) (*)
│   │   │   │   │   │   │   │       ├── icu_collections v2.3.0 (*)
│   │   │   │   │   │   │   │       ├── icu_locale_core v2.3.0 (*)
│   │   │   │   │   │   │   │       ├── icu_properties_data v2.3.0
│   │   │   │   │   │   │   │       ├── icu_provider v2.3.1 (*)
│   │   │   │   │   │   │   │       ├── zerotrie v0.2.5 (*)
│   │   │   │   │   │   │   │       └── zerovec v0.11.8 (*)
│   │   │   │   │   │   │   ├── smallvec v1.16.3
│   │   │   │   │   │   │   └── utf8_iter v1.0.4
│   │   │   │   │   │   ├── percent-encoding v2.3.2
│   │   │   │   │   │   ├── serde v1.0.229 (*)
│   │   │   │   │   │   └── serde_derive v1.0.229 (proc-macro) (*)
│   │   │   │   │   └── uuid v1.28.0 (*)
│   │   │   │   ├── semver v1.0.28 (*)
│   │   │   │   ├── serde v1.0.229 (*)
│   │   │   │   ├── serde-untagged v0.1.9
│   │   │   │   │   ├── erased-serde v0.4.10
│   │   │   │   │   │   ├── serde_core v1.0.229
│   │   │   │   │   │   └── typeid v1.0.3
│   │   │   │   │   ├── serde_core v1.0.229
│   │   │   │   │   └── typeid v1.0.3
│   │   │   │   ├── serde_json v1.0.154 (*)
│   │   │   │   ├── serde_with v3.24.0
│   │   │   │   │   ├── serde_core v1.0.229
│   │   │   │   │   └── serde_with_macros v3.24.0 (proc-macro)
│   │   │   │   │       ├── darling v0.24.1
│   │   │   │   │       │   ├── darling_core v0.24.1
│   │   │   │   │       │   │   ├── ident_case v1.0.1
│   │   │   │   │       │   │   ├── proc-macro2 v1.0.107 (*)
│   │   │   │   │       │   │   ├── quote v1.0.47 (*)
│   │   │   │   │       │   │   ├── strsim v0.11.1
│   │   │   │   │       │   │   └── syn v3.0.9 (*)
│   │   │   │   │       │   └── darling_macro v0.24.1 (proc-macro)
│   │   │   │   │       │       ├── darling_core v0.24.1 (*)
│   │   │   │   │       │       ├── quote v1.0.47 (*)
│   │   │   │   │       │       └── syn v3.0.9 (*)
│   │   │   │   │       ├── proc-macro2 v1.0.107 (*)
│   │   │   │   │       ├── quote v1.0.47 (*)
│   │   │   │   │       └── syn v3.0.9 (*)
│   │   │   │   ├── thiserror v2.0.21 (*)
│   │   │   │   ├── toml v1.1.8+spec-1.1.0
│   │   │   │   │   ├── serde_core v1.0.229
│   │   │   │   │   ├── serde_spanned v1.1.2
│   │   │   │   │   │   └── serde_core v1.0.229
│   │   │   │   │   ├── toml_datetime v1.1.2+spec-1.1.0
│   │   │   │   │   │   └── serde_core v1.0.229
│   │   │   │   │   ├── toml_parser v1.1.5+spec-1.1.0
│   │   │   │   │   │   └── winnow v1.0.4
│   │   │   │   │   ├── toml_writer v1.1.3+spec-1.1.0
│   │   │   │   │   └── winnow v1.0.4
│   │   │   │   ├── url v2.5.8 (*)
│   │   │   │   ├── urlpattern v0.6.0
│   │   │   │   │   ├── icu_properties v2.3.0 (*)
│   │   │   │   │   ├── regex v1.13.1 (*)
│   │   │   │   │   ├── serde v1.0.229 (*)
│   │   │   │   │   └── url v2.5.8 (*)
│   │   │   │   ├── uuid v1.28.0 (*)
│   │   │   │   └── walkdir v2.5.0
│   │   │   │       ├── same-file v1.0.6
│   │   │   │       │   └── winapi-util v0.1.11
│   │   │   │       │       └── windows-sys v0.61.2
│   │   │   │       │           └── windows-link v0.2.1
│   │   │   │       └── winapi-util v0.1.11 (*)
│   │   │   ├── thiserror v2.0.21 (*)
│   │   │   ├── url v2.5.8 (*)
│   │   │   ├── uuid v1.28.0 (*)
│   │   │   └── walkdir v2.5.0 (*)
│   │   └── tauri-utils v2.10.2 (*)
│   ├── tauri-runtime v2.12.2
│   │   ├── cookie v0.18.2 (*)
│   │   ├── dpi v0.1.2 (*)
│   │   ├── http v1.5.0 (*)
│   │   ├── raw-window-handle v0.6.2
│   │   ├── serde v1.0.229 (*)
│   │   ├── serde_json v1.0.154 (*)
│   │   ├── tauri-utils v2.10.2
│   │   │   ├── anyhow v1.0.104
│   │   │   ├── brotli v9.0.0
│   │   │   │   ├── alloc-no-stdlib v3.0.0
│   │   │   │   ├── alloc-stdlib v0.3.0
│   │   │   │   │   └── alloc-no-stdlib v3.0.0
│   │   │   │   └── brotli-decompressor v6.0.1
│   │   │   │       ├── alloc-no-stdlib v3.0.0
│   │   │   │       └── alloc-stdlib v0.3.0 (*)
│   │   │   ├── ctor v1.0.13
│   │   │   ├── dunce v1.0.5
│   │   │   ├── glob v0.3.4
│   │   │   ├── http v1.5.0 (*)
│   │   │   ├── infer v0.22.0
│   │   │   │   └── cfb v0.14.0
│   │   │   │       ├── fnv v1.0.7
│   │   │   │       ├── uuid v1.28.0
│   │   │   │       │   └── serde_core v1.0.229
│   │   │   │       └── web-time v1.1.0
│   │   │   ├── json-patch v4.2.0
│   │   │   │   ├── jsonptr v0.7.1
│   │   │   │   │   ├── serde v1.0.229 (*)
│   │   │   │   │   └── serde_json v1.0.154 (*)
│   │   │   │   ├── serde v1.0.229 (*)
│   │   │   │   ├── serde_json v1.0.154 (*)
│   │   │   │   └── thiserror v2.0.21 (*)
│   │   │   ├── log v0.4.34
│   │   │   ├── memchr v2.8.3
│   │   │   ├── phf v0.13.1
│   │   │   │   ├── phf_macros v0.13.1 (proc-macro) (*)
│   │   │   │   └── phf_shared v0.13.1
│   │   │   │       └── siphasher v1.0.4
│   │   │   ├── plist v1.10.1
│   │   │   │   ├── base64 v0.23.1
│   │   │   │   ├── indexmap v2.14.2
│   │   │   │   │   ├── equivalent v1.0.3
│   │   │   │   │   └── hashbrown v0.17.1
│   │   │   │   ├── quick-xml v0.42.0
│   │   │   │   │   └── memchr v2.8.3
│   │   │   │   ├── serde v1.0.229 (*)
│   │   │   │   └── time v0.3.55 (*)
│   │   │   ├── regex v1.13.1
│   │   │   │   ├── aho-corasick v1.1.5
│   │   │   │   │   └── memchr v2.8.3
│   │   │   │   ├── memchr v2.8.3
│   │   │   │   ├── regex-automata v0.4.18
│   │   │   │   │   ├── aho-corasick v1.1.5 (*)
│   │   │   │   │   ├── memchr v2.8.3
│   │   │   │   │   └── regex-syntax v0.8.11
│   │   │   │   └── regex-syntax v0.8.11
│   │   │   ├── semver v1.0.28
│   │   │   ├── serde v1.0.229 (*)
│   │   │   ├── serde-untagged v0.1.9
│   │   │   │   ├── erased-serde v0.4.10
│   │   │   │   │   ├── serde_core v1.0.229
│   │   │   │   │   └── typeid v1.0.3
│   │   │   │   ├── serde_core v1.0.229
│   │   │   │   └── typeid v1.0.3
│   │   │   ├── serde_json v1.0.154 (*)
│   │   │   ├── serde_with v3.24.0
│   │   │   │   ├── serde_core v1.0.229
│   │   │   │   └── serde_with_macros v3.24.0 (proc-macro) (*)
│   │   │   ├── thiserror v2.0.21 (*)
│   │   │   ├── toml v1.1.8+spec-1.1.0
│   │   │   │   ├── serde_core v1.0.229
│   │   │   │   ├── serde_spanned v1.1.2
│   │   │   │   │   └── serde_core v1.0.229
│   │   │   │   ├── toml_datetime v1.1.2+spec-1.1.0
│   │   │   │   │   └── serde_core v1.0.229
│   │   │   │   ├── toml_parser v1.1.5+spec-1.1.0
│   │   │   │   │   └── winnow v1.0.4
│   │   │   │   ├── toml_writer v1.1.3+spec-1.1.0
│   │   │   │   └── winnow v1.0.4
│   │   │   ├── url v2.5.8 (*)
│   │   │   ├── urlpattern v0.6.0
│   │   │   │   ├── icu_properties v2.3.0 (*)
│   │   │   │   ├── regex v1.13.1 (*)
│   │   │   │   ├── serde v1.0.229 (*)
│   │   │   │   └── url v2.5.8 (*)
│   │   │   ├── uuid v1.28.0 (*)
│   │   │   └── walkdir v2.5.0
│   │   │       ├── same-file v1.0.6
│   │   │       │   └── winapi-util v0.1.11
│   │   │       │       └── windows-sys v0.61.2 (*)
│   │   │       └── winapi-util v0.1.11 (*)
│   │   ├── thiserror v2.0.21 (*)
│   │   ├── url v2.5.8 (*)
│   │   ├── webview2-com v0.39.1
│   │   │   ├── webview2-com-macros v0.8.1 (proc-macro)
│   │   │   │   ├── proc-macro2 v1.0.107 (*)
│   │   │   │   ├── quote v1.0.47 (*)
│   │   │   │   └── syn v2.0.119 (*)
│   │   │   ├── webview2-com-sys v0.39.1
│   │   │   │   ├── windows v0.62.2
│   │   │   │   │   ├── windows-collections v0.3.2
│   │   │   │   │   │   └── windows-core v0.62.2
│   │   │   │   │   │       ├── windows-implement v0.60.2 (proc-macro)
│   │   │   │   │   │       │   ├── proc-macro2 v1.0.107 (*)
│   │   │   │   │   │       │   ├── quote v1.0.47 (*)
│   │   │   │   │   │       │   └── syn v2.0.119 (*)
│   │   │   │   │   │       ├── windows-interface v0.59.3 (proc-macro)
│   │   │   │   │   │       │   ├── proc-macro2 v1.0.107 (*)
│   │   │   │   │   │       │   ├── quote v1.0.47 (*)
│   │   │   │   │   │       │   └── syn v2.0.119 (*)
│   │   │   │   │   │       ├── windows-link v0.2.1
│   │   │   │   │   │       ├── windows-result v0.4.1
│   │   │   │   │   │       │   └── windows-link v0.2.1
│   │   │   │   │   │       └── windows-strings v0.5.1
│   │   │   │   │   │           └── windows-link v0.2.1
│   │   │   │   │   ├── windows-core v0.62.2 (*)
│   │   │   │   │   ├── windows-future v0.3.2
│   │   │   │   │   │   ├── windows-core v0.62.2 (*)
│   │   │   │   │   │   ├── windows-link v0.2.1
│   │   │   │   │   │   └── windows-threading v0.2.1
│   │   │   │   │   │       └── windows-link v0.2.1
│   │   │   │   │   └── windows-numerics v0.3.1
│   │   │   │   │       ├── windows-core v0.62.2 (*)
│   │   │   │   │       └── windows-link v0.2.1
│   │   │   │   └── windows-core v0.62.2 (*)
│   │   │   │   [build-dependencies]
│   │   │   │   └── thiserror v2.0.21 (*)
│   │   │   ├── windows v0.62.2 (*)
│   │   │   └── windows-core v0.62.2 (*)
│   │   └── windows v0.62.2 (*)
│   ├── tauri-runtime-wry v2.12.2
│   │   ├── http v1.5.0 (*)
│   │   ├── log v0.4.34
│   │   ├── once_cell v1.21.4
│   │   ├── raw-window-handle v0.6.2
│   │   ├── softbuffer v0.4.8
│   │   │   ├── raw-window-handle v0.6.2
│   │   │   ├── tracing v0.1.44 (*)
│   │   │   └── windows-sys v0.61.2 (*)
│   │   ├── tao v0.37.1
│   │   │   ├── bitflags v2.13.2 (*)
│   │   │   ├── crossbeam-channel v0.5.17 (*)
│   │   │   ├── dpi v0.1.2 (*)
│   │   │   ├── libc v0.2.191
│   │   │   ├── log v0.4.34
│   │   │   ├── parking_lot v0.12.5
│   │   │   │   ├── lock_api v0.4.14
│   │   │   │   │   └── scopeguard v1.2.0
│   │   │   │   └── parking_lot_core v0.9.12
│   │   │   │       ├── cfg-if v1.0.5
│   │   │   │       ├── smallvec v1.16.3
│   │   │   │       └── windows-link v0.2.1
│   │   │   ├── raw-window-handle v0.6.2
│   │   │   ├── unicode-segmentation v1.13.3
│   │   │   ├── url v2.5.8 (*)
│   │   │   ├── windows v0.62.2 (*)
│   │   │   ├── windows-core v0.62.2 (*)
│   │   │   └── windows-version v0.1.7
│   │   │       └── windows-link v0.2.1
│   │   ├── tauri-runtime v2.12.2 (*)
│   │   ├── tauri-utils v2.10.2 (*)
│   │   ├── url v2.5.8 (*)
│   │   ├── webview2-com v0.39.1 (*)
│   │   ├── windows v0.62.2 (*)
│   │   └── wry v0.57.0
│   │       ├── cookie v0.18.2 (*)
│   │       ├── dpi v0.1.2 (*)
│   │       ├── dunce v1.0.5
│   │       ├── http v1.5.0 (*)
│   │       ├── once_cell v1.21.4
│   │       ├── raw-window-handle v0.6.2
│   │       ├── thiserror v2.0.21 (*)
│   │       ├── webview2-com v0.39.1 (*)
│   │       ├── windows v0.62.2 (*)
│   │       ├── windows-core v0.62.2 (*)
│   │       └── windows-version v0.1.7 (*)
│   ├── tauri-utils v2.10.2 (*)
│   ├── thiserror v2.0.21 (*)
│   ├── tokio v1.53.3 (*)
│   ├── url v2.5.8 (*)
│   ├── webview2-com v0.39.1 (*)
│   ├── window-vibrancy v0.8.1
│   │   ├── raw-window-handle v0.6.2
│   │   ├── windows-sys v0.61.2 (*)
│   │   └── windows-version v0.1.7 (*)
│   └── windows v0.62.2 (*)
│   [build-dependencies]
│   ├── glob v0.3.4
│   ├── heck v0.5.0
│   ├── tauri-build v2.7.3
│   │   ├── anyhow v1.0.104
│   │   ├── cargo_toml v1.0.1
│   │   │   ├── semver v1.0.28 (*)
│   │   │   ├── serde v1.0.229 (*)
│   │   │   └── toml v1.1.8+spec-1.1.0 (*)
│   │   ├── dirs v7.0.0
│   │   │   └── dirs-sys v0.5.0
│   │   │       ├── option-ext v0.2.0
│   │   │       └── windows-sys v0.61.2 (*)
│   │   ├── glob v0.3.4
│   │   ├── heck v0.5.0
│   │   ├── json-patch v4.2.0 (*)
│   │   ├── schemars v0.8.22 (*)
│   │   ├── semver v1.0.28 (*)
│   │   ├── serde v1.0.229 (*)
│   │   ├── serde_json v1.0.154 (*)
│   │   ├── static_vcruntime v3.0.0
│   │   ├── strsim v0.11.1
│   │   ├── tauri-utils v2.10.2 (*)
│   │   ├── tauri-winres v0.3.6
│   │   │   ├── dunce v1.0.5
│   │   │   ├── embed-resource v3.0.12
│   │   │   │   ├── cc v1.8.0
│   │   │   │   │   ├── find-msvc-tools v0.1.14
│   │   │   │   │   └── shlex v2.0.1
│   │   │   │   ├── rustc_version v0.4.1 (*)
│   │   │   │   ├── toml v1.1.8+spec-1.1.0 (*)
│   │   │   │   ├── vswhom v0.1.0
│   │   │   │   │   ├── libc v0.2.191
│   │   │   │   │   └── vswhom-sys v0.1.3
│   │   │   │   │       └── libc v0.2.191
│   │   │   │   │       [build-dependencies]
│   │   │   │   │       └── cc v1.8.0 (*)
│   │   │   │   └── winreg v0.56.0
│   │   │   │       ├── cfg-if v1.0.5
│   │   │   │       └── windows-sys v0.61.2 (*)
│   │   │   └── toml v1.1.8+spec-1.1.0 (*)
│   │   └── walkdir v2.5.0 (*)
│   └── tauri-utils v2.10.2 (*)
├── tauri-plugin-opener v2.7.2
│   ├── dunce v1.0.5
│   ├── glob v0.3.4
│   ├── open v5.4.4
│   │   └── dunce v1.0.5
│   ├── serde v1.0.229 (*)
│   ├── serde_json v1.0.154 (*)
│   ├── tauri v2.12.4 (*)
│   ├── thiserror v2.0.21 (*)
│   └── windows v0.62.2 (*)
│   [build-dependencies]
│   ├── schemars v0.8.22 (*)
│   ├── serde v1.0.229 (*)
│   └── tauri-plugin v2.7.2
│       ├── anyhow v1.0.104
│       ├── glob v0.3.4
│       ├── schemars v0.8.22 (*)
│       ├── serde v1.0.229 (*)
│       ├── serde_json v1.0.154 (*)
│       ├── tauri-utils v2.10.2 (*)
│       └── walkdir v2.5.0 (*)
├── tauri-plugin-single-instance v2.5.4
│   ├── serde v1.0.229 (*)
│   ├── serde_json v1.0.154 (*)
│   ├── tauri v2.12.4 (*)
│   ├── thiserror v2.0.21 (*)
│   ├── tokio v1.53.3 (*)
│   ├── tracing v0.1.44 (*)
│   └── windows-sys v0.61.2 (*)
└── windows-sys v0.61.2 (*)
[build-dependencies]
└── tauri-build v2.7.3 (*)

```

### reqwest feature 树（exit=0）

```text
reqwest v0.13.5
├── reqwest feature "blocking"
│   └── spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri)
│       └── spectrum-agent feature "default" (command-line)
└── reqwest feature "json"
    └── spectrum-agent v0.1.0 (E:\AI_Agent\src-tauri) (*)

```

## 遇到的问题

CLI 已解析 single-instance 2.5.4，自动注册阶段因当时还没有 src/main.rs 失败。
锁中实际版本确为 2.5.4 后，manifest 将同一版本约束钉为 =2.5.4；未解析其他版本、
未升级/降级凑数。插件注册将由真实宿主实现且必须首个注册，安装结果不冒充宿主通过。
完整初次 add 输出保留。

全平台 cargo fetch 后段包含未使用平台的大包，控制器核对 Cargo 进程身份后停止该轮，
改为同一 Cargo.lock 的 Windows x64 fetch，成功。不变更任何锁定版本或 TLS 配置。
中途 offline cargo tree 曾因尚缺 webview2-com-sys 失败，原文保留在
cargo-tree-locked-installed-output.txt；成功树使用新文件名，未覆盖首轮失败。

npm ls 的 UNMET OPTIONAL DEPENDENCY 为未选择的跨平台或可选功能，exit=0；
实际 Windows x64 组件已安装。reqwest 的当前目标 feature 仅 blocking/json，无 TLS。

## 下一步打算

编译并验证固定 /health + /smoke 客户端、真实 Tauri 四态窗口与对话条；所有联调须引用
新引擎批次 manifest。第 2 步 VM 仍待实机验证，旧 exit code=70 内部原因未验证。
