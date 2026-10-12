# PMRS 4.2.2 源码清单与审阅覆盖

**固定提交：** `e4de0210f9985224e030ac4cfd2f7e2904005b37`
**性质：** 静态目录盘点、定向源码审阅覆盖及建议去向；不是完整调用图、执行覆盖率或环境 SBOM。

[审计报告](01-Architecture-Audit.zh-CN.md) · [实施计划](02-Implementation-Plan.zh-CN.md) · [机器可读清单](source-inventory.json)。

## 1. 统计口径

69 个顶层 Python 模块 + 5 个 workflows 模块，共 74 个。Git tree 提供的源码大小合计 1,560,557 字节。每个文件仅计一次；不把目录、JSON schema、前端、测试及构建脚本计入这 74 个。完整目录的证据来自固定树，不来自对文件名的推测。[R-tree] [R-workflow-tree]

| 级别 | 含义 | 模块数 |
|---|---|---|
| E | 本阶段直接读取关键源码范围；并非每行都检查 | 20 |
| H | 本对话前段对同一固定提交的定向源码读取，可复用 | 6 |
| D | 根据目录、架构文档或已读调用点定位；内部仍需逐函数核对 | 39 |
| T | 仅核对目录元数据；职责分类为待验证建议 | 9 |

E/H 的“已读”限于本次取回的范围。D/T 的职责与迁移去向是规划标签，不能引用为该文件内部算法已被独立审计。后续 PR-01 应取得隔离源码 checkout，解析所有源文件的 AST，生成直接/传递 import 图及强连通分量；不通过执行 import 收集依赖。

## 2. 逐模块清单

表中“建议去向”是拆分目标，不表示现有结构已满足该分层。链接固定提交。

| 编号 | 文件 | 字节 | 审阅 | 当前职责/定位 | 建议去向 |
|---|---|---:|:---:|---|---|
| M01 | [`__init__.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/__init__.py) | 95 | T | 包入口 | `package` |
| M02 | [`__main__.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/__main__.py) | 47 | T | 命令入口 | `interfaces/cli` |
| M03 | [`activity.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/activity.py) | 10,694 | D | 状态展示投影 | `observability/projections` |
| M04 | [`admission.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/admission.py) | 413 | T | 接纳入口 | `application/admission` |
| M05 | [`archive.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/archive.py) | 3,983 | T | 归档 | `adapters/storage` |
| M06 | [`assistant.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/assistant.py) | 47,417 | H | 已停用助手及历史兼容 | `legacy/assistant` |
| M07 | [`assurance.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/assurance.py) | 41,195 | E | 数学资格与独立审查 | `domain/qualification` |
| M08 | [`changes.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/changes.py) | 64,560 | E | 科学变更校验与接纳 | `domain/validation + application/admission` |
| M09 | [`autoflow.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/autoflow.py) | 20,760 | D | 应用推进与历史入口 | `application + orchestration/legacy` |
| M10 | [`cli.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/cli.py) | 17,839 | H | CLI 与装配 | `interfaces/cli + bootstrap` |
| M11 | [`codex_client.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/codex_client.py) | 19,355 | E | Codex 登录、能力探测及输入测量 | `adapters/codex` |
| M12 | [`communication.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/communication.py) | 32,050 | D | 消息、暴露、独立性和输送 | `application/communication + domain/exposure` |
| M13 | [`context.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/context.py) | 23,554 | D | 任务前提闭包与上下文过滤 | `domain/input_policy + application/context` |
| M14 | [`contracts.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/contracts.py) | 49,386 | D | 记录与调用契约混合 | `domain/contracts + ports/dtos` |
| M15 | [`corrections.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/corrections.py) | 8,878 | D | 修订请求 | `application/corrections` |
| M16 | [`demo.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/demo.py) | 14,380 | D | 教学与合成输送 | `tests/support` |
| M17 | [`desktop.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/desktop.py) | 3,641 | D | 桌面启动 | `retire/interfaces/desktop` |
| M18 | [`engine.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/engine.py) | 26,684 | E | 共享应用门面 | `application/research` |
| M19 | [`execution.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/execution.py) | 67,575 | E | 调用生命周期、接纳和恢复 | `application/execution + domain/events` |
| M20 | [`handoff.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/handoff.py) | 7,302 | D | 范围化研究交接 | `domain/handoff + application/handoff` |
| M21 | [`harness_methods.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/harness_methods.py) | 30,337 | D | 科研方法与实际输入装配 | `domain/protocols + application/context` |
| M22 | [`harness_runtime.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/harness_runtime.py) | 8,791 | E | MAIN 事件准入与唤醒 | `application/main_control + orchestration` |
| M23 | [`host_pool.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/host_pool.py) | 8,747 | E | 全局槽位及公平分配 | `application/resources + adapters/local_runtime` |
| M24 | [`incidents.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/incidents.py) | 13,938 | D | 事故分类与受控恢复 | `application/recovery + observability` |
| M25 | [`input_delivery.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/input_delivery.py) | 17,933 | D | 实际输入送达与封窗 | `application/input_delivery` |
| M26 | [`input_plans.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/input_plans.py) | 21,059 | D | 输入选择及材料计划 | `domain/input_policy + application/context` |
| M27 | [`knowledge.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/knowledge.py) | 22,335 | H | 六类科学记录与精确引用 | `domain/evidence` |
| M28 | [`knowledge_access.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/knowledge_access.py) | 12,699 | E | 授权知识导航、检索及展开 | `application/queries + adapters/index` |
| M29 | [`language.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/language.py) | 6,174 | D | 科研输出语言规则 | `domain/presentation_policy` |
| M30 | [`localization.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/localization.py) | 2,481 | T | 界面地区配置 | `interfaces/localization` |
| M31 | [`main_history.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/main_history.py) | 4,434 | D | MAIN 历史导航 | `application/context` |
| M32 | [`main_input_tables.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/main_input_tables.py) | 8,893 | D | MAIN 输入元数据编码 | `application/context` |
| M33 | [`main_materials.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/main_materials.py) | 3,242 | D | MAIN 材料引用装配 | `application/context` |
| M34 | [`main_recovery.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/main_recovery.py) | 12,599 | D | 原生 MAIN 特定故障恢复 | `adapters/codex/recovery + application/recovery` |
| M35 | [`main_session.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/main_session.py) | 5,696 | D | MAIN 状态及会话入口 | `application/main_control + observability` |
| M36 | [`model_policy.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/model_policy.py) | 12,493 | E | 角色配置与 Codex 参数编码混合 | `domain/role_requirements + application/model_selection + adapters/codex` |
| M37 | [`native_main.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/native_main.py) | 43,000 | E | 持久 Codex MAIN、原生 Goal、根轮次门控 | `adapters/codex/native_runner` |
| M38 | [`obligations.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/obligations.py) | 22,590 | D | 科研职责、依赖和资格阈值 | `domain/obligations` |
| M39 | [`operations.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/operations.py) | 465 | T | 操作兼容入口 | `application/commands` |
| M40 | [`pdf_filter.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/pdf_filter.py) | 2,468 | D | PDF 编译隔离 | `adapters/reporting` |
| M41 | [`portability.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/portability.py) | 4,407 | D | 项目导入导出 | `adapters/storage/portability` |
| M42 | [`relations.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/relations.py) | 8,353 | E | 数学依赖关系 | `domain/relations` |
| M43 | [`render.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/render.py) | 12,274 | E | 受限 TeX 编译、PDF 检查与工具 | `adapters/reporting` |
| M44 | [`report_catalog.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/report_catalog.py) | 13,974 | D | 报告目录及当前性 | `application/reports + observability` |
| M45 | [`report_revisions.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/report_revisions.py) | 10,321 | D | 报告修订、版本和授权 | `domain/report_contract + application/reports` |
| M46 | [`reports.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/reports.py) | 94,644 | H | 报告编排、接纳、修订、输出 | `application/reports + domain/report_contract + adapters/reporting` |
| M47 | [`research_audit.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/research_audit.py) | 28,894 | H | 研究时钟、检查点和指导 | `domain/research_memory + application/audit` |
| M48 | [`research_plans.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/research_plans.py) | 16,383 | D | 多分支工作计划与历史控制 | `application/plans` |
| M49 | [`research_prompts.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/research_prompts.py) | 16,038 | D | 科研职责提示词 | `domain/protocols` |
| M50 | [`resources.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/resources.py) | 13,438 | D | 磁盘、内存与准备资源 | `application/resources + adapters/local_runtime` |
| M51 | [`restricted_tex.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/restricted_tex.py) | 9,773 | D | 受限 TeX 与语义身份 | `domain/report_contract + adapters/reporting` |
| M52 | [`rounds.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/rounds.py) | 11,176 | D | 轮次结果与交付 | `domain/delivery + application/reports` |
| M53 | [`runner.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/runner.py) | 40,151 | E | 进程、沙箱、输入、执行、协调器 | `adapters/codex + application/supervisor + testing` |
| M54 | [`scheduler.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/scheduler.py) | 21,784 | E | 职责准入、资源公平与预算 | `application/admission + orchestration` |
| M55 | [`setup.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/setup.py) | 16,986 | D | 环境探测及配置 | `bootstrap + adapters/local_runtime` |
| M56 | [`stages.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/stages.py) | 6,368 | T | 阶段入口 | `domain/protocols + application` |
| M57 | [`store.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/store.py) | 30,651 | E | 权威 journal/blob、事务、回放和索引 | `adapters/storage/journal + application/unit_of_work` |
| M58 | [`strategy.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/strategy.py) | 64,011 | H | MAIN 路线、提案、派工与状态 | `domain/strategy + application/main_control` |
| M59 | [`survey.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/survey.py) | 74,955 | D | 综述领域与线性编排 | `domain/survey + application/survey` |
| M60 | [`survey_retrieval.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/survey_retrieval.py) | 13,942 | D | 来源检索与获取 | `adapters/sources` |
| M61 | [`task_tools.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/task_tools.py) | 24,035 | E | 请求级 MCP、权限、消息和读记录 | `interfaces/mcp + application/tool_gateway` |
| M62 | [`tasks.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/tasks.py) | 42,661 | D | 冻结任务、材料、请求、模型配置 | `application/tasks + ports/dtos` |
| M63 | [`ui.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/ui.py) | 26,924 | E | HTTP 路由和网页接入 | `retire/interfaces/web` |
| M64 | [`usage_ledger.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/usage_ledger.py) | 33,087 | E | 计量规则、Codex 事件解析、投影 | `application/usage + adapters/codex/usage + observability` |
| M65 | [`util.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/util.py) | 5,574 | D | 散列、路径、原子文件等共享工具 | `domain/value_helpers + adapters/filesystem` |
| M66 | [`version.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/version.py) | 536 | T | 版本元数据 | `package` |
| M67 | [`views.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/views.py) | 29,430 | D | 科研和运行投影 | `observability/queries` |
| M68 | [`workflow_instances.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/workflow_instances.py) | 42,400 | D | TRH/FDH 生命周期、授权和控制 | `domain/lifecycle + application/control` |
| M69 | [`workspace.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/workspace.py) | 52,139 | E | 工作区、动作、后台线程和展示 | `application/supervisor + application/commands + retire/web_state` |
| M70 | [`workflows/__init__.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/workflows/__init__.py) | 79 | T | 科研协议包 | `domain/protocols` |
| M71 | [`workflows/fdh.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/workflows/fdh.py) | 18,980 | D | D0–D5 职责契约 | `domain/protocols` |
| M72 | [`workflows/registry.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/workflows/registry.py) | 9,996 | E | 统一职责注册、独立性角色、禁止自动阶段转移 | `domain/protocols` |
| M73 | [`workflows/survey.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/workflows/survey.py) | 3,794 | D | 综述职责契约 | `domain/protocols` |
| M74 | [`workflows/trh.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/workflows/trh.py) | 42,217 | D | P0–P14 职责契约 | `domain/protocols` |

## 3. 非 Python 产品资源与外部依赖

| 资源/边界 | 本阶段已确认的定位 | 重构处置 | 审阅限制 |
|---|---|---|---|
| `pyproject.toml` | Python >=3.11，Python runtime dependency 列表为空，打包/CLI/desktop 入口 | 拆为纯内核、CLI、各适配器可选依赖 | 空 dependencies 不意味着系统运行无外部依赖 |
| `research_studio/static/`、`locales/` | 自建网页和显示资源；含数学渲染资源 | PR-14 删除 UI 专属资产；保留 CLI 需要的语义标签 | 未逐个审查所有前端资源和第三方许可证 |
| `research_studio/native/` 与 `docs/native-*` | app-server、sidecar、manifest、来源和补丁边界 | 留在 Codex adapter 的版本化 provenance 中 | 仓库不分发 compiled pair；未构建/执行 |
| 科研/调用 schema 与 registry | 记录、任务、协议、权限等不同语义混合 | 拆领域 schema 和执行 DTO，保持身份兼容 | 尚未对全部生成 schema 做一致性执行检查 |
| `README*`、`ARCHITECTURE*`、`docs/*METHOD*` | 产品说明与 MAIN 方法源 | 文档、实际 packet、测试三者一致更新 | 磁盘存在不证明真实送达 |
| `.github/workflows/final-candidate.yml` | 指定自托管 Ubuntu 与浏览器证据门 | 改为离线核心门 + 明确可选平台/原生门 | 未调用任何 workflow 或下载私人运行产物 |
| Codex CLI、patched app-server、sidecar | 模型/Agent 执行与认证 | Runner/能力/事件/usage 适配器 | 具体用户机器兼容性未确认 |
| fcntl、/proc、文件锁、Unix socket、进程组 | 现行 Linux 运行控制依赖 | 本地 runtime adapter；平台支持须明确 | 未声明 Windows 原生运行等价 |
| Tectonic、Poppler、fontconfig、bubblewrap、prlimit、seccomp | 可选报告生成的外部工具/隔离 | 报告 renderer 可选安装 | 不因移除 UI 删除报告能力；未调用这些工具 |
| Rust/C/C++、OpenSSL、curl/tar/patch 等 | 原生构建链 | 文档和特定适配器构建环境 | 上游源码/二进制传递依赖 SBOM 尚未生成 |

依赖事实见 [R-pyproject] [R-native-doc] [R-runner] [R-render] [R-ci]。本阶段没有安装 LangGraph、Deep Agents 或模型 SDK，也没有把它们加入 PMRS。

## 4. 脚本清单

下面 10 项来自固定 Git tree。除已核对调用点、架构和原生构建说明外，不声称完整阅读过每个脚本。[R-scripts]

| 脚本 | Git tree 字节 | 迁移职责建议 |
|---|---:|---|
| [`browser_evidence.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/scripts/browser_evidence.py) | 6,046 | 退役 UI 证据；保留需要替代的产品验收职责 |
| [`build-native-main.sh`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/scripts/build-native-main.sh) | 3,536 | Codex native adapter 构建与来源核验 |
| [`build-release.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/scripts/build-release.py) | 13,591 | 无 UI 分包、可重现性、manifest |
| [`coverage_registry.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/scripts/coverage_registry.py) | 6,275 | 测试职责映射，不能将历史 PASS 迁为当前 PASS |
| [`install-gui.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/scripts/install-gui.py) | 6,283 | 退役图形安装入口 |
| [`install-local.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/scripts/install-local.py) | 13,354 | 保留/简化 CLI 与可选适配器安装 |
| [`prepare-release.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/scripts/prepare-release.py) | 1,261 | 包完整性与准备 |
| [`test-runner.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/scripts/test-runner.py) | 8,390 | 离线测试入口及隔离安全检查 |
| [`validate-groups.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/scripts/validate-groups.py) | 3,414 | 拆分核心/适配器/平台验收 |
| [`verify-pdf.py`](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/scripts/verify-pdf.py) | 3,952 | 可选报告验收，不是 UI 依赖 |

## 5. 测试资源覆盖的解释

固定树包含 kernel/storage/security/workflow/model-policy/communication/recovery/report/survey/packaging/UI 等测试族，以及 `tests/coverage/*.json`、fixture builders、旧助手 legacy 测试和 workbench JavaScript 测试。存在性已经核对，实际断言需要后续阅读/选择，全部当前执行状态为 **NOT_EXECUTED**。[R-tests]

实施计划第 15 节给出可复用文件族和新测试映射。没有调用 `pytest`、仓库测试 runner、CI、`doctor`、native executable 或真实模型；不能将本清单作运行验收凭据。

## 6. 需要下一阶段补足的依赖成果

源码层：生成完整静态 import 图、动态 import/插件/子进程调用清单、强连通分量与跨层例外，人工确认不可达 legacy 分支。函数级调用图存在动态语言限制，必须标覆盖边界。

环境层：在确定支持的平台和后端版本后，记录 Python 包锁、Node/Rust/原生 binary provenance、系统工具版本与许可证，形成实际安装环境的 SBOM。仅凭 `dependencies=[]` 或目录树无法获得完整传递依赖。

数据层：经后续授权只读分析所选项目的 schema、journal 版本和引用完整性。公开源码与单次历史实验摘要不能替代用户实际数据版本核对。

| 来源 ID | 来源及核对用途 |
|---|---|
| R-ci | [指定 self-hosted 验收入口](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/.github/workflows/final-candidate.yml) |
| R-native-doc | [原生 pair 来源、构建与已报告限制](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/docs/NATIVE-RUNTIME.md) |
| R-pyproject | [Python 包、入口与依赖声明](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/pyproject.toml) |
| R-render | [离线报告编译工具与隔离](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/render.py) |
| R-runner | [CodexExecutor、沙箱、协调器与 doctor](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/runner.py) |
| R-scripts | [安装、构建和测试脚本清单](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/tree/e4de0210f9985224e030ac4cfd2f7e2904005b37/scripts) |
| R-tests | [测试源文件清单；不表示执行通过](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/tree/e4de0210f9985224e030ac4cfd2f7e2904005b37/tests) |
| R-tree | [74 模块目录盘点的主目录](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/tree/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio) |
| R-workflow-tree | [5 个科研协议模块](https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/tree/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/workflows) |

外部文档仅支持对应框架能力描述，不支持本报告提出的 PMRS 实现已经存在或经过运行验证。

[R-ci]: https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/.github/workflows/final-candidate.yml "指定 self-hosted 验收入口"
[R-native-doc]: https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/docs/NATIVE-RUNTIME.md "原生 pair 来源、构建与已报告限制"
[R-pyproject]: https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/pyproject.toml "Python 包、入口与依赖声明"
[R-render]: https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/render.py "离线报告编译工具与隔离"
[R-runner]: https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/blob/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/runner.py "CodexExecutor、沙箱、协调器与 doctor"
[R-scripts]: https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/tree/e4de0210f9985224e030ac4cfd2f7e2904005b37/scripts "安装、构建和测试脚本清单"
[R-tests]: https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/tree/e4de0210f9985224e030ac4cfd2f7e2904005b37/tests "测试源文件清单；不表示执行通过"
[R-tree]: https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/tree/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio "74 模块目录盘点的主目录"
[R-workflow-tree]: https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio/tree/e4de0210f9985224e030ac4cfd2f7e2904005b37/research_studio/workflows "5 个科研协议模块"

