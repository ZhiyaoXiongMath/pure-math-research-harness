# PMRS 4.2.2 candidate22 preview changes

This code preview contains the latest candidate22 implementation and publication-only documentation/cleanup. It is not a fully accepted release. See [validation status](TEST-REPORT-4.2.2.md).

- TRH and FDH each use an independent Astra Ultra MAIN with the full dynamic method, persistent native thread and Goal. SURVEY stays serial and host-controlled.
- MAIN owns research assignments, routes, dependencies, concurrency, communications, waits and delivery. Stage CLI tasks use 8 per-instance / 20 global resource admission; native internal delegation stays open and outside those slots.
- Automatic P14, next-P14 stopping and manual P14 preserve original scope, cumulative allowance and actual native control state. FDH formal D5 provides explicit researcher choices and a paused independent TRH handoff.
- Event-driven guidance, configurable light checks, effective-research audit timing and immutable MAIN checkpoints support long-running research without treating routine waiting as paid analysis.
- Actual input/output, original material, repairs, admission, communication and usage are readable and downloadable in the workbench. Round reports are distinct from requested manuscripts/PDFs.
- Software fixes preserve original evidence: live dispatch validation, observed receipt scope, reference normalization, lossless metadata transport, exact on-demand historical material access, native launcher recovery and stale/collapsed UI state.
- The single real HSC TRH experiment remains OPEN and was later paused at the user's request. FDH/SURVEY and unexercised paths are not claimed as passed. Public docs contain only sanitized status; private scientific evidence is excluded.

## 中文

- TRH/FDH 各自独立 Astra Ultra MAIN、完整动态方法、持久原生线程与 Goal；SURVEY 仍由宿主线性运行。
- MAIN 决定科研派工、路线、依赖、并发、通信、等待和交付；阶段任务采用每实例 8、全局 20 准入，原生内部委派不受其限制。
- 自动/人工 P14、下次 P14 停止、FDH D5 人工选择及暂停 TRH 交接，保留原范围、额度与真实 Goal 状态。
- 事件驱动指导、可配置轻量检查、有效研究审计和不可改写检查点支撑长期研究，不把正常等待变成付费分析。
- 网页查看/下载真实输入输出和证据；轮次报告不自动触发整套稿件/PDF 写作。
- 保留证据的软件修复覆盖实时派工校验、回执观察范围、引用归一化、无损元数据传输、历史原件按需读取、启动器恢复及界面阅读状态。
- 唯一 HSC 实验仍为 OPEN，后续按用户要求暂停；FDH/SURVEY 和未覆盖行为不标为实测通过。本次只推代码，不创建 tag 或 GitHub Release。
