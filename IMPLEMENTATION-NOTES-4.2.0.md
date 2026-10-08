# PMRS 4.2.0 implementation notes / 实现说明

## English

Version **4.2.0** includes two completed development scopes: repairs to scientific responsibilities, bounded workflow continuation and execution resources; and the new project assistant with exact report revision. These notes describe the implementation and retained development evidence. The published **v4.1.0 tag and release assets remain unchanged**. Actual 4.2.0 build and publication identities are recorded separately; this document does not assert completed remote publication.

The new Project assistant adds one persistent conversation panel with project, task-issue and exact-report entry points. It uses gpt-6-astra/xhigh, an initially zero assistant allowance, and at most one assistant call per sent turn. Explicit report revision uses separate finite author/reviewer authorization, preserves report versions and accumulated user requirements, and does not resume paused research. Reading history and evidence is model-free; UNKNOWN and lost receipts retain the original operation. These implemented capabilities are not a claim of paid-model validation or mathematical correctness. Bilingual instructions are in the README and in-app Guide.

The repaired implementation gives all existing 29 TRW, TFDW and SURVEY stages explicit scientific input, role and result duties. Bounded work plans select actual tasks and dependencies without requiring every stage to run. P7 supports N framework-learning branches plus M independent direct-analysis branches; synthesis must account for every selected branch, including failures and explicitly deferred optional work. P8 can perform a first research attempt, and P11 examines the global mathematical gap. Survey reading, topic organization and coverage review can share one finite mission. Renaming a branch or opening another mission does not reset the same duty's accumulated attempt allowance.

The ordinary **Start research round** entry now advances necessary work from actual results under the original authorization. TRW checks and reuses applicable P1–P3 background, reverse-analysis and route-exploration results, schedules missing prerequisites, and follows concrete gaps and dependencies. It does not always start at P4 or require stage-by-stage approval. TFDW presents its candidate frontier for human choice; Survey advances selected reading, organization and readiness work, with a visible wait for missing inputs and no implicit online retrieval. The explicit finite-plan interface remains available for deliberate branches and dependencies.

A deterministic host account provides P13-style delivery: actual results, failures, unfinished and unperformed duties, and open gaps. Dependency waits, resource waits, exhausted authorization, faults and readiness for a human decision remain distinct. This account makes no model call, does not certify the mathematics, and does not request a formal report or open another round. The researcher retains the P14 decision.

**Request a correction** records a concrete affected responsibility and success criterion in the original mission and pauses new dispatch. Continuation recovers eligible original captures and executes the correction within the remaining allowance. **Authorize more calls in this round** explicitly adds a finite allowance with a reason; saving it does not start execution or reset the scope, concurrency, request identities or cumulative responsibility-attempt limits. Starting a new round does not send the previous mission's unsent prepared requests. Original sent requests and captures remain preserved for their original recovery path, and UNKNOWN is never automatically resent.

Execution supports an explicitly authorized project concurrency of up to **8**, under a shared host pool of **10**. Existing lower project limits remain effective. A live queue refills available slots when a task settles; short input preparation has a separate two-slot limit. Resource admission accounts for physical memory and temporary disk across projects, using these per-phase estimates:

| Phase | Estimated memory |
| --- | ---: |
| Prepare | 256 MiB |
| Client | 96 MiB |
| Capture | 256 MiB |
| Admission | 512 MiB |
| Render | 1,024 MiB |

New tasks reference immutable material hashes and copy only their selected input closure. They avoid embedding a second full source body in the packet. Existing frozen packets keep their original identities and bytes. Resource waiting, capture recovery and report-render continuation preserve the original request; UNKNOWN is never automatically resent.

The retained workflow/resource development measurements covered eight 1 MiB tasks, a separate 8 MiB task, and overlap with a real one-page render: sampled process-tree RSS peaked at **379.4 MiB**, with **144.2 MiB** during preparation. A separate 30 MiB single-task case peaked at **95.8 MiB**. These runs used a controlled local transport with zero paid model calls and zero network requests. RSS was sampled every 20 ms; shared pages can be counted more than once and brief peaks can be missed. Enlarged synthetic token allowances supported measurement only. These observations neither establish real-model context capacity nor prove a bound for arbitrary TeX, input corpora or workloads. Phase estimates are application admission accounting, not added operating-system memory or swap limits.

The supported native checkpoint state serialization remains **48 MiB**. A checkpoint-producing commit that exceeds this boundary cannot advance HEAD; an existing capture remains available for recovery after the blocking condition is resolved. This is a state-publication boundary, not an unlimited-history guarantee or a 48 MiB source-library limit.

Portable evidence and implementation references (test paths below belong to the matching source ZIP; they are not files in the installer ZIP):

- Assistant panel, pinned context, original-turn recovery and report versions — `tests/repair-workbench.test.js` in the source ZIP, bilingual Guide and raw-text isolation — `tests/locale-workbench.test.js` in the source ZIP.
- Assistant native transport, finite allowances and mixed queue — `tests/test_assistant_kernel.py` in the source ZIP, exact manuscript revisions and captured-result recovery — `tests/test_assistant_reports.py` in the source ZIP, real HTTP multi-turn diagnosis and report delivery — `tests/test_assistant_surface.py` in the source ZIP. These tests use controlled responses; they do not establish live model availability or mathematical correctness. Local edits select existing top-level numbered sections; arbitrary sentence ranges are not supported. Unselected source bytes are preserved, but changed content can reflow later pages; unchanged page pixels are not promised.
- Scientific duties and bounded plans — `tests/test_research_plans.py` in the source ZIP, [29-stage prompt definitions](research_studio/research_prompts.py).
- Ordinary-start automatic continuation and prerequisite reuse — `tests/test_autoflow.py` in the source ZIP, round delivery, corrections and explicit finite authorization — `tests/test_round_intervention.py` in the source ZIP, pause and original-request preservation — `tests/test_runner_pause.py` in the source ZIP.
- Shared host pool and original-request recovery — `tests/test_model_pool.py` in the source ZIP, physical-resource admission — `tests/test_resource_admission.py` in the source ZIP.
- Exact inputs, reference packets, report continuation and checkpoint recovery — `tests/test_intervention_inputs.py` in the source ZIP, input resource regressions — `tests/test_resource_inputs.py` in the source ZIP.
- [Architecture and supported boundaries](ARCHITECTURE-4.2.0.md). The [4.2.0 validation record](TEST-REPORT-4.2.0.md) separates original development executions, their scoped reuse, release-specific checks and the historical published baseline. Earlier batches are not summed into a newly executed full suite. Local measurement logs and native recovery receipts are retained separately and are not bundled with source or installers.

## 中文

版本 **4.2.0** 包含两项已完成的开发范围：科学职责、有限自动承接及资源执行的补齐与修复；项目助手及精确报告修订的新功能。本说明记录实现与保留的开发证据。已发布 **v4.1.0 的 tag 和附件保持不变**；4.2.0 构建与发布身份另行记录，此文不提前宣称远端发布已完成。

新增“项目助手”提供统一持久会话面板，项目、任务问题及精确报告均可进入。助手使用 gpt-6-astra/xhigh，初始额度为零，每次发送最多一次助手调用；明确的报告修订使用独立有限作者/审查授权，保留版本及累计用户要求，不恢复已暂停科研。读历史与证据不调用模型；UNKNOWN 与丢失回执均保留原操作。这些已实现能力不等于付费模型验收或数学正确性证明。README 和程序内 Guide 均提供完整双语说明。

上方助手原生传输、报告修订及真实 HTTP 测试覆盖有限额度、共用队列、多轮要求和原结果恢复；全部使用受控响应，不证明实时模型可用性或数学正确性。局部改稿选择既有顶层编号章节，暂不支持任意句子区间。未选部分保留原稿字节，但修改可能引起后续页面重排，不承诺未选页面像素不变。

本版补齐三种流程既有 29 个阶段的科学职责，各阶段均有明确的科学输入、角色职责和结果承接。有限工作计划按实际需要选择任务及依赖，不强制依次执行全部阶段。P7 支持 N 条框架学习分支和 M 条独立直接分析分支，综合必须交代全部选定分支，包括失败及明确延期的可选工作；P8 支持首次实际研究，P11 检查全局数学缺口。Survey 的多来源阅读、主题整理及覆盖审查可共用一个有限授权。更换分支名称或新建 mission 不会重置同一职责的累计尝试额度。

普通“开始本轮研究”现按实际结果在原授权内承接必要工作。TRW 检查并复用适用的 P1–P3 背景、目标逆推与路线探索成果，安排缺失前置，再按具体缺口及依赖推进，不再固定从 P4 开始或要求逐阶段批准。TFDW 呈现候选前沿后等待人类选择；Survey 承接所选材料的阅读、组织与就绪审查，缺少输入时明确等待，不隐含联网获取。高级有限计划入口仍可显式指定分支与依赖。

宿主通过确定性盘点提供 P13 式交付，保留实际成果、失败、未完成和未执行职责及开放缺口，区分依赖等待、资源等待、预算耗尽、故障与可交给人类决定的状态。该盘点不调用模型、不认证数学结论、不请求正式报告，也不自动开启下一轮；P14 决定仍由研究者作出。

“提出纠正要求”把具体受影响职责和完成标准记入原 mission，并暂停新派发。继续时先恢复符合条件的原捕获，再在余额内执行纠正。“为本轮追加有限调用授权”要求人类明确有限数额与原因；保存不启动，也不重置范围、并发、请求身份或同一职责累计尝试限制。开始新轮不会发送旧 mission 尚未发出的 prepared 请求；原已发送请求和捕获仍保留，按原恢复路径处理，UNKNOWN 不自动重发。

显式授权后的单项目并发最高 **8**，共享宿主调用池为 **10**；既有较低项目限制继续生效。任务结算后动态补充可运行任务，短时输入准备另有两个槽位。跨项目物理内存与临时磁盘记账采用上表的阶段估算：准备 256、客户端 96、捕获 256、接纳 512、渲染 1,024 MiB。这些数值用于应用层准入，不新增操作系统内存或 swap 硬限制。

新任务通过不可变内容哈希引用精确选材闭包，不在任务包中重复嵌入整份原文；旧冻结任务包保持原身份与字节。资源等待、捕获恢复及报告渲染续办均保留原请求，UNKNOWN 不自动重发。

保留的职责/资源阶段模拟测量包含 8 个各约 1 MiB 的任务、另一个 8 MiB 任务，以及与实际单页渲染的重叠：进程树采样 RSS 峰值 **379.4 MiB**，准备阶段峰值 **144.2 MiB**；单独 30 MiB 任务峰值 **95.8 MiB**。全部使用受控本地传输，付费模型调用和网络请求均为零。20 ms 采样可能遗漏短峰值，共享页面可能重复计数；测量用放大 token 容量不代表真实模型支持该容量。上述结果不构成对任意 TeX、材料集或负载的内存上界证明。

原生检查点状态序列化的支持边界仍是 **48 MiB**。生成检查点的提交超过此边界时不能推进 HEAD；已有捕获保留，解除阻断后按原请求恢复。这不是无限历史保证，也不是来源库总大小限制。

上方测试路径属于同版源码 ZIP，安装包不包含测试源码；当前说明链接指向安装包内实际提供的文件。它们提供可移植的职责、调度、输入与恢复依据。[4.2.0 验收记录](TEST-REPORT-4.2.0.md)区分原开发执行、限定复用、本版发布检查和历史发布基线，不把旧批次数量相加为本轮新执行的全套验收；本地测量原始日志与原生恢复回执独立保存，不随源码或安装包分发。
