# Native runtime for the 4.2.2 code preview

The Git branch contains source and provenance, not prebuilt executables or private build logs. Before running MAIN, supply both Linux x86_64 executables under `research_studio/native/` or use `PMRS_NATIVE_MAIN_BINARY` to point to a verified external app-server directory containing its `manifest.json` and `codex-code-mode-host`. The external override is for running; the packaging script requires the verified files under `research_studio/native/`.

## Provenance and build

- The patched app-server uses OpenAI Codex commit `2351d9e1b608e6f9d9a3699b71d7eb39ee41cfa4`. Exact archive and patch hashes are in [source metadata](native-goal-source.json). The [patch](native-goal-client.patch) adds root MAIN admission before sampling and isolates product configuration. Native internal delegates bypass the PMRS root gate. This is a modified build, not an unmodified official executable.
- The companion used by candidate22 came from the official Codex 0.160.0 distribution. Its separate SHA-256 and protocol provenance are in [companion metadata](native-code-mode-source.json). It was not built from the same source commit as the patched app-server. The attempted matching-source build could not obtain the upstream `rusty_v8` 150.4.0 sandbox archive (HTTP 404). No sandbox weakening was used.
- [build-native-main.sh](../scripts/build-native-main.sh) builds the pinned app-server in an isolated directory using the exact separately supplied companion. It checks the source archive and companion hashes, applies the patch and writes the native manifest. It requires Linux x86_64, Python 3, a C/C++ toolchain, pkg-config, OpenSSL headers, curl, tar, patch, network access and build storage. Build parallelism in that script is a compiler setting, not a research-agent limit.
- The upstream [Apache license](native-goal-APACHE-LICENSE) and [native license](../research_studio/native/LICENSE) remain included.

An operator who already has the verified candidate22 binaries may place them in `research_studio/native/` with the matching manifest and executable modes. Never substitute another binary under the old hash or describe a different companion as the same-source build. `scripts/build-release.py` and MAIN admission verify the pair. Missing or mismatched executables block research; there is no CLI fallback for MAIN.

Only the sanitized build facts are public. Original build logs, machine paths, authentication and runtime sessions remain private. This source-only publication did not repeat the native Rust/V8 build or a paid compatibility probe. Its packaging verification reuses the already verified candidate22 pair locally and excludes both executables from the Git commit.

## 中文

Git 分支保留源码、补丁、版本和哈希，不上传两个已编译程序或私人构建日志。运行 MAIN 前，需要配套的 Linux x86_64 app-server、code-mode-host 和匹配 `manifest.json`；也可通过 `PMRS_NATIVE_MAIN_BINARY` 指向包含这三项的外部目录。打包时仍须将核验后的程序放到 `research_studio/native/`。

app-server 使用固定上游源码及 PMRS 根轮次准入补丁，内部委派不受该根轮次准入限制。candidate22 的配套程序来自官方 Codex 0.160.0，来源与 app-server 不同。同源码构建配套程序曾因上游 V8 归档 HTTP 404 受阻；未削弱沙箱。请按各自清单核对，不能任意替换或冒称同源码构建。

构建脚本需要 Linux x86_64、Python 3、C/C++ 工具链、pkg-config、OpenSSL 头文件、curl、tar、patch、网络与空间。源码推送只复用已核验程序做本地打包核对，不重跑原生构建或付费探测。原程序、日志及运行记录仍留在私人本地备份/验证目录，Git 提交不含二进制。
