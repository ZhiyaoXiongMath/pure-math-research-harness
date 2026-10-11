# PMRS 4.2.2 architecture

TRH and FDH are independent MAIN-driven research harnesses. SURVEY is a host-controlled sequential workflow. They share one native Store, executor, source library, usage ledger and report services.

## Decision boundary

For each TRH/FDH instance, the first model request belongs to its own `gpt-6-astra` Ultra MAIN. A complete versioned method handbook enters the actual frozen request: P0–P13 and P14 for TRH; D1–D5 and D0 scope for FDH. Recovery supplies the method, original target, current problem graph and prior decision evidence again. A document stored on disk alone is not evidence of delivery.

MAIN chooses research responsibilities, stage CLI tasks, priorities, start dependencies, parallel branches, route changes, communications, merge points, waits and delivery. Its native dispatch tools preserve decision provenance and validate exact input/scope/budget before queueing tasks. Final proposals must not duplicate already committed runtime dispatch. Host code manages admission, evidence, resources and recovery; it does not derive new scientific tasks from worker suggestions or stage numbers. MAIN unavailability is a runtime blocker.

WAIT specifies relevant tasks, input, resources or user conditions. New relevant evidence can wake MAIN while unrelated branches remain active. Identical polling does not create a paid MAIN request. Paused or replaced routes dispose of associated unsent work atomically; SENT and UNKNOWN identities and actual usage remain.

## Two kinds of delegation

Stage CLI tasks are PMRS-managed independent requests with stage / role / purpose policies, frozen contracts and capture/admission lineage. Each dispatch contains at most 8 tasks. Each harness instance has at most 8 in-flight stage tasks, and every 4.2.2 project and entry point shares 20 global stage slots. Survey uses one stage slot at a time. Reserved, sent and unresolved unknown work remain occupied until original evidence permits release; queueing without reservation does not consume a slot.

MAIN top-level work and Codex native internal delegation are outside both stage pools. PMRS imposes no internal agent count, depth, concurrency, model, attempt or token allowance. This is a PMRS policy boundary, not a claim to override external service capabilities. MAIN requests still consume the authorized finite PMRS top-level allowance. Internal usage remains separately observable where the client exposes it; native aggregates are not double-counted.

Client mode, top-level requested model, transport effort and native delegation evidence are different facts. MAIN stays Astra Ultra. A subordinate transport field need not literally say Ultra, and an internal agent need not use MAIN's model. A capability check cannot require internal delegation to be disabled.

## Communication and scientific qualification

MAIN has a stable instance inbox and can communicate with each owned stage task. It can create and revise directed links or collaboration groups, with scope, version, reason and original exposure evidence. Request-scoped MCP tools actually deliver and read messages. Stored, delivered, read, used and withdrawn are distinct states. Late messages do not retroactively change a sealed request.

Scientific dependency and completion dependency remain separate. Independent checks preserve exact target scope and verdict isolation. MAIN can coordinate status or missing originals with an independent task, but scientific content exposure changes its independence eligibility. A separate internal agent, communication acknowledgement, confident route label or accepted JSON cannot certify a theorem.

The existing scientific contract keeps exact premise endpoints, qualified support, complete argument closure, exact original source identity, review scope, typed conditions and conservative representation-only FORMAT repair. Original rejected responses and finite repair lineage remain auditable. Repairs cannot invent science or replace a sample without evidence.

## P14 and reports

TRH's persistent `instance.run_control` stores `AUTO_P14` or `HUMAN_P14`, round number, state, stop request and control version. Web controls invoke native control events. A pending stop request or manual mode takes precedence over automatic continuation at P14. A reached stop requires an explicit human continue; merely changing mode cannot resume it. MAIN automatic decisions have their own event identity and never masquerade as `HUMAN_DECISION`.

P13/P14 preserves a readable progress account before any next-round decision. The account binds the original target, round, actual evidence, unfinished duties and continuation rationale. Goal achievement needs the existing scientific evidence and independent qualification; otherwise the account remains OPEN. End, budget exhaustion and technical blocking preserve corresponding result descriptions. Formal manuscripts use the selected output or an explicit request, not an automatic writing chain after each stage. New rounds and software recovery preserve the same allowance.

## Persistent native Goal and PHAROS adaptation

The PHAROS addendum strengthens the existing MAIN control chain rather than adding another controller. Each harness has a persistent native thread/Goal association. Native transport observations and synchronization receipts are evidence about client execution; Store control remains the authority for scope and permission. UI must never present desired/mirrored status as an actual native client observation.

TRH automatic P14 continues the same active Goal. Manual P14 and reached stop requests block further dispatch before syncing native pause; explicit continue is required, and does not silently switch manual mode to automatic. FDH ordinary reports and checkpoints permit continuing D0-bounded exploration. Formal D5 handover records a distinct `WAITING_HUMAN_AT_D5` and pauses the same Goal. `CONTINUE_DISCOVERY` resumes its existing scope and allowance; exact candidate adoption can create a new paused TRH, never overwrite either Goal. Ending, no candidates and budget exhaustion cannot masquerade as successful Goal completion. Late events, timer notifications and restart recovery honor the latest persisted control version.

The `research_audit` projection groups `research_clocks`, `research_audit_events`, `research_audits`, `research_checkpoints` and `research_guidance`. Default half-hour checks record runtime/message/wait observations without claiming MAIN analysis. Four-hour deadlines count effective instance research elapsed time, including active internal/stage work without adding parallel hours. Whole-instance pause or pure external blocking freezes the clock; incomplete timing evidence remains disclosed. Complete MAIN audits and their published checkpoints reset the interval; ordinary returns, a new timestamp or restart do not.

Published research checkpoints carry immutable body identity, original target/scope, method and guidance versions, scientific state, routes or candidates, actual progress, failure synthesis, active tasks, constraints and next decisions. They remain separate from Store's reconstructible replay cache. Audits bind trigger/due/completion information, covered events, relevant evidence versions and unexamined increments. Routes retain mechanisms, before/after gaps, evidence, failed attempts, current tasks, decision consequences and reconsideration conditions. FDH retains unknown candidate relations instead of a TRH proof-completion score.

Effective guidance derives from immutable human words with explicit supersedes/revokes and delivery/application history. Viewing, discussing or adding materials while paused does not resume a Goal. Shared strategy memory does not carry prior verdicts into independent stage checks. These records contain observable reasoning summaries and evidence, not hidden chain-of-thought.

During a long native turn, the existing MAIN receives bounded host event navigation through `turn/steer`. Navigation contains event identities and instructions to read them, not scientific verdicts or authorization. `main_runtime_context` returns current original guidance, pending audits, control and frontier; its exact confirmed delivery extends the request's observed input set. Final strategy/checkpoint validation binds these responses to the original execution and sealed capture. A task-state listing does not establish that a new scientific body was read. Unread results remain explicit checkpoint increments and re-enter later MAIN input.

## Native runtime and maintenance admission

The isolated patched native app-server and separately sourced official `codex-code-mode-host` are packaged together and checked against their manifest before MAIN admission. Their distinct source provenance is retained; see the README and native manifests. A persistent Goal has no authority to spend an unreserved PMRS call: the root-turn gate binds one current reservation, original input and control version before sampling. Native internal agents remain outside this PMRS root gate. Native thread/Goal observations remain distinct from the desired control state.

Normal capture recovery revalidates original bytes. Already captured, uncancelled stage work may be admitted while the instance is paused; the recovery does not dispatch new work. MAIN plans remain fenced while paused. Representation-only FORMAT repair is reserved for evidence-backed formatting defects and cannot manufacture a scientific response after a tool-launch failure.

`main_recovery.py` implements a narrow explicit maintenance path for a captured MAIN that could not start any code-mode tool and never read its required material. It verifies the bound original native thread and turn, native non-client-authored launcher failures for every tool call, exact final-capture hash, absence of dynamic deliveries or admitted work, and the repaired native runtime manifest. A typed `MAIN_EXECUTION_RECOVERY_AUTHORIZED` event stores the repair reason and existing user authorization in `main_execution_recoveries`. It leaves the failed request, rejection and usage unchanged, grants no new budget, and does not resume a paused instance by itself.

After normal authorized continuation, that recovery identity permits exactly one new MAIN control request on the same Goal and mission. Its `entry_basis.main_execution_recovery_refs` records which failure it succeeds; a later failed request requires its own evidence and explicit recovery action. Previously unread directions can be supplied again while preserving their original delivery history. This is host repair of execution admission, not host selection of a P/D stage or scientific acceptance.

Candidate22 build, isolated installation and limited single-experiment runtime evidence are summarized in `TEST-REPORT-4.2.2.md`. Mathematics remains OPEN and the experiment was subsequently paused by the user. Private receipts and research outputs are not distributed here.

Authenticated `/api/research-memory` pages exact instance-scoped published checkpoint/audit/guidance/event bodies. `/api/research-memory-file` downloads original bodies, native records and bound original MAIN captures. Draft checkpoints cannot appear as published research memory. The MAIN panel and control view separately expose native Goal evidence, research audits, effective guidance, checkpoint history and original task/output links. TRH uses P14 controls; FDH uses distinct D5 continue/adopt/handoff/end presentation.

Static implementation and actual behavior remain separate claims. The sole HSC experiment supplies runtime evidence; no accelerated clock, artificial four-hour wait, extra probe or FDH/Survey run is authorized.

## Native web evidence

`views.task_artifacts` constructs a task-bound allowlist of exact model task, prompt, packet and materials, original capture, repairs, accepted mathematical bodies, runtime deliveries, communication and executor logs. The authenticated `/api/task-detail` endpoint supplies task, request, decision basis, duties, usage and artifact metadata. `/api/task-artifact` permits only allowlisted files, supports bounded text pages and downloads original bytes. It does not accept arbitrary filesystem paths or user-supplied blob hashes. Live logs are marked as growing; no saved final capture means no final output is claimed.

The UI distinguishes MAIN and stage CLI tasks, instance/global stage occupancy, pending P14 stop and immediate pause. SURVEY omits MAIN and research-route panels. Round progress reports, formal manuscripts and raw task outputs have separate entries. Original mathematical text is rendered with the bundled math renderer and available unchanged for download.

## Evidence boundary

This document describes the implementation contract. The accompanying HSC delivery receipt determines which behavior was actually exercised and the final scientific/runtime state. No paid FDH/Survey run, synthetic scenario, independent test matrix or artificial saturation is part of the 4.2.2 acceptance. Old format compatibility and old research-project mutation are excluded.

## 中文摘要

TRH/FDH 每实例由自己的 Astra Ultra MAIN 从第一步决定研究，宿主只执行、校验、计量、通信和恢复；Survey 保留固定串行控制。两份完整方法手册进入真实输入。阶段任务每次派发最多 8 个、每实例在途 8 个、全局 20 个；MAIN 顶层与原生内部委派不占槽。MAIN 内部委派不受 PMRS 额外限制。

P14 默认在原目标和原额度内自动继续，持久停止请求与人工模式优先，已到节点需明确人工继续。每次 P13/P14 保留可读轮次报告，正式稿件按请求生成。任务详情展示实际输入、材料、原始输出、修复、接纳、科研正文、通信与用量，并支持原件下载。是否在唯一 HSC 真运行中实测及最终 OPEN/完成/阻塞等状态，以真实交付回执为准。
