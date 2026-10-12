# PMRS-Next 第一阶段：架构审计与重构规划

**日期：2026-10-11；固定提交：`e4de0210f9985224e030ac4cfd2f7e2904005b37`。**

本包交付静态审计、目标接口与实施计划。已通过连接的 GitHub 读取固定版本源码及目录；没有提交产品修改、创建真实 PR、运行 PMRS/仓库测试、调用研究模型、访问正式科研项目或改变 MAIN/Goal。

## 阅读顺序

| 文件 | 内容 |
|---|---|
| [01 架构审计报告](01-Architecture-Audit.zh-CN.md) | 15 项发现、依赖分析、当前与目标架构、LangGraph/Deep Agents/DSH 中立比较、已证据化事实与限制 |
| [02 实施计划与接口设计](02-Implementation-Plan.zh-CN.md) | Runner/Provider/编排/领域/控制接口、事件与四轴状态、恢复/预算、安全讨论、快慢数学、18 个规划 PR、58 项新增软件验收条目、原指南 46 项继承映射 |
| [03 源码清单与审阅覆盖](03-Source-Inventory.zh-CN.md) | 74 个 Python 模块及建议归属，脚本/系统依赖/测试族、E/H/D/T 审阅深度 |
| [source-inventory.json](source-inventory.json) | 机器可读的固定版本路径、元数据和审阅级别 |
| [00 原开发指南](00-Reference-Development-Guide.zh-CN.md) | 用户提供的需求基线，原字节保留；旧助手可直接复用的判断已在 01 中更正 |
| [audit-manifest.json](audit-manifest.json) | 范围、禁止动作执行情况、文档质量检查与交付计数 |
| [SHA256SUMS.txt](SHA256SUMS.txt) | 上述交付文件的 SHA-256 校验值 |

## 核心结论

先建立纯查询与稳定端口，保留现有科学接纳和保守恢复语义，再抽取独立内核、Codex Runner 与 headless supervisor。快数学必须成为有精确慢层支撑的第一类模块/连接，而不是摘要缓存。

LangGraph 可评估为执行编排；Deep Agents 可评估为受约束 runner；它们都不能自动替代 PMRS 的数学资格、原目标/D0、用户授权及 UNKNOWN 处理。不预先确定必须采用某一框架。

**覆盖边界：** 完整列出 69 个顶层 Python 模块及 5 个 workflows 模块；20 个有本阶段定向源码读取、6 个复用同对话同提交读取、39 个为目录/调用点/文档定位、9 个仅元数据。不是全仓逐行审计、完整 AST 图或真实环境 SBOM。

**下一授权建议：** 仅 PR-01–03：安全离线开发入口、统一接口、纯查询拆分。本包不授权任何后续开发或科研执行。

## 图与文件使用

所有内容为 UTF-8 Markdown/JSON；图使用 Mermaid，不能渲染 Mermaid 的阅读器仍可查看图的源码与相邻文字。解压后相对链接保持可用。没有 PDF、可执行程序、模型日志、私人科研原件或凭据。

文档检查只检查文件可读、链接/引用、代码围栏、计数、JSON 与压缩包完整性。所有 PMRS 产品测试与新的科研验收均为 **NOT_EXECUTED**，不能将文档检查理解成程序通过测试。
