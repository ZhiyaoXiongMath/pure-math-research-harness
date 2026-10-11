# PMRS 4.2.2 installation and evidence guide

The supported native package is Linux x86_64 with Python 3.11+. Follow the complete [English](README.md#requirements-and-installation) or [Chinese](README.zh-CN.md#环境和安装) source-build and isolated-install instructions. This code branch intentionally excludes prebuilt native executables; see [native provenance and prerequisites](docs/NATIVE-RUNTIME.md).

Use a new installation prefix, launcher directory and workspace. Verify artifact SHA-256 and the installer manifest. Do not point a preview at an older production project or overwrite its installation. Configure the official Codex CLI and optional PDF dependencies through Settings; keep credentials and workspace contents outside Git.

Candidate22's existing installation and limited real-run evidence are described in [the validation report](TEST-REPORT-4.2.2.md). The original experiment is paused and must not be resumed merely to verify this publication. No simulated scenario, browser matrix, stress run, FDH/SURVEY paid acceptance or extra model probe is part of this source push. Existing native desktop/file-picker paths are not declared passed unless actually observed.

## 中文

请按 README 准备核验后的原生程序对，再构建到外部目录并隔离安装。使用新的前缀、启动器目录和工作区，勿覆盖旧安装或旧项目。认证和科研工作区不进入 Git。

candidate22 的有限实测见验证报告。原实验已暂停，不为源码推送恢复；此次没有模拟、浏览器矩阵、压力、FDH/SURVEY 付费验收或额外模型探测。构建核对不等于完整验收。
