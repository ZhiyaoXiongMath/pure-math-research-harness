DEV06 最小格式合同 R1 — 供定向复审及人类决定，未批准

本轮仅修订合同，不实现产品。以 input/reviewed-r0-proposal.txt、reviewed-r0-format-example.json 和独立 REQUEST_CHANGES 为基准；R0 原件不改。本稿整体替代其候选定义，不要求读者合并相互矛盾的补丁。源码依据仍为 frozen HEAD 4239f15ad1233cc89cd6556cec284951b5fc2e3e。本文与示例均非 IMPLEMENTED、产品 TESTED、REVIEWED 或 ACCEPTED。

1. 格式及精确启动前缀【F1、M1、CTRL-Q2】

推荐仍为复用 native Journal/blob/HEAD 的 pmrh.commit/2，仅用于可信测试装配新建、显式 opt-in 的 synthetic 项目。仅增加 native 字段不能阻止旧 reader 接受 delta、旧 writer 忽略 owner/outbox；明确 discriminator 是最低合理隔离成本。/2 sticky，实际 HEAD 的完整 ancestry 检查先于 as-of/checkpoint 选择；未知字段/tag、降级、/1 混入一律拒绝。依据 journal.py:73–88、136–159、467–489。正确的 /1 限制是 PMRH_PORT_* 观察出版不得携带控制 delta 或冒充控制权；sticky /1 后续 native 提交仍合法，见 format.py:72–100。

fresh /2 不接收 PORT_*，v1 磁盘 EvidenceRepository/EventRepository/Storage/UnitOfWork 路径对 /2 返回 UNSUPPORTED_CAPABILITY；/1 全部原语义保留。本合同不为将来方便而增加观察/控制集成。公共 pmrh.ports/1.0 的字段、签名、枚举、严格解码及 wire bytes 均不变；内部封闭命令不假扮公共 OperationIntent。

启动器只能持有本次新建目录的可信 setup capability，不能通过扫描、路径参数或 synthetic=true 收编旧项目。允许的 native 前缀精确如下；无任意 initial state、迁移或 /1 激活入口：

| 顺序 | 允许的真实 native 操作及状态 |
| --- | --- |
| 1 | Store.create(..., synthetic=True, initial=None)：唯一 PROJECT_CREATED；原默认空集合、默认预算/能力数据；正常 CHECKPOINT/state_sha256 元数据允许。CAP-HUMAN 文本不是认证。 |
| 2 | TRH：恰一次 changes.prepare_source_input(raw, purpose=PROBLEM) → Store.commit，产生一份原始 source、SOURCE_BOUND Statement/KO 及 SOURCE_PRESERVED provenance；不宣称证明。FDH：恰三次同入口、purpose=PHENOMENON，依次为 phenomenon、immutable_background、allowed_axes 的非空原文，生成三个 source，不生成 target。SURVEY：零 source-input，使用原 normalize_scope 可验证的无来源引用 scope。 |
| 3 | 恰一个 CREATE_INSTANCE：TRH target_ref 必须等于步骤 2 返回的精确 Statement；FDH 的三项 discovery_scope *_ref 必须对应上述 source，discovery_brief_ref=phenomenon_ref；SURVEY 保留其原独立 scope。实例 PAUSED、无 mission/task/request。 |
| 4 | 首个 /2 提交 ACTIVATED；同事务记录 PROFILE、初始 ownership(epoch=1)，控制版本 0→1，仍 PAUSED。PROFILE 绑定 genesis_commit 与步骤 3 的 setup_head；setup capability 验证整段来源和精确 reducer 输出后失效。 |

前缀每一步允许原出版器自行产生的 CHECKPOINT/不可变 blobs/记录与正常序号、scope_versions 元数据；不允许手写 checkpoint 注入字段。除以上 source/target/instance 及原生成元数据外，没有 missions、budget grants、calls、captures、reservations、策略、模型产物、外部引用或控制工作。默认 project_budget.max_calls=0 不等于授予额度。依据 storage_compat.py:14–42、45–83；changes.py:472–535；engine.py:23–45、68–85；workflow_instances.py:36–63、144–151；journal.py:246–265。

一致 TRH 示意轨迹：native #1 PROJECT_CREATED+CHECKPOINT → #2 ORIGINAL_SOURCE_RECEIVED(PROBLEM，返回 target T) → #3 CREATE_INSTANCE(TRH,target=T,PAUSED) → /2 #4 ACTIVATED(epoch1,version1) → #5 明确 AUTHORIZE_MISSION 创建有限 grant、ACTIVE/version2 → #6 STRATEGY_INITIALIZED → #7 CALL_PREPARED(MAIN)。步骤 5 之后才可能调用；示例不提供这些步骤的可运行载荷。最小 profile 激活后不提供 CREATE_INSTANCE、原文上传或候选采用创建新实例入口；因此 /2 不声称完整旧产品工作流覆盖，/1 不受此限制。

2. 封闭持久字段、动作及版本【F1–F3、CTRL-Q1】

以下全为待批格式。S=非空有界字符串；H=64 小写 hex SHA-256；I=exact int、非 bool、0≤I<2^63；R=未修改的完整 v1 ExactRef；T=UTC 时间。所有对象严格字段集，数组至多 4096 项，null 仅在下述许可位置。新增对象统一 schema=pmrh.control/1、kind 为表中闭合标签；未标记的 native 增项不另包 schema。原科学字段不改名。

| 位置 / kind | 精确字段（不重复 schema、kind） |
| --- | --- |
| 激活 blob / PROFILE | profile:SYNTHETIC_TEST_ONLY, project_id:S, genesis_commit:H, setup_head:H, resource_policy:COMPAT_8_20_SURVEY1, pool_id:S |
| instances[i].ownership / OWNER | logical_main_id:S或null, owner_id:S, owner_epoch:I≥1, backend_binding_ref:R或null, authorization_ref:R |
| instances[i]（仅 SURVEY） | infrastructure_control_version:I；不得添加 run_control 或科学 MAIN |
| 决策 blob / DECISION | decision_id:S, scope:{project_id:S,instance_id:S}, principal_ref:R, authn_evidence_ref:R, authority_ref:R, action:本节闭合动作, payload_sha256:H, owner_epoch:I, control_version:I, issued_at:T, expires_at:T, budget_grant_ref:R或null, capability_manifest_ref:R或null |
| budget_grants[g] 增项 | budget_unit:AGENT_INVOCATION, grant_revision:I≥1, grant_status:ACTIVE或REVOKED, authorization_ref:R；保留 max_calls/explicit_unlimited 原互斥约束 |
| blob / RESERVATION | reservation_id:S, identity:v1 InvocationIdentity, grant_ref:R, unit:AGENT_INVOCATION, amount:1, owner_epoch:I≥1, control_version:I |
| requests[r].admission / CALL | operation_id:S, idempotency_key:S, invocation_id:S, logical_agent_id:S, attempt_id:S, owner_epoch:I≥1, control_version:I, spec_ref:R, reservation_ref:R, capability_manifest_ref:R, send_phase:READY或ATTEMPTED或CLOSED, slot_token:S或null, send_boundary_id:S或null, charge:RESERVED或UNKNOWN_RESERVED或SPENT_OR_SETTLED或RELEASED, receipt_ids:[S], not_sent_ref:R或null, termination_ref:R或null, evidence_conflict:bool |
| requests[r].execution_inbox / INBOX | producer_ref:R, binding_ref:R, cursor:v1 EventCursor, state:OPEN或GAP, gap:v1 EventGap或null, last_page_ref:R或null |
| execution_events 的回执载荷 / RECEIPT | receipt_id:S, identity:v1 InvocationIdentity, binding_ref:R, producer_ref:R, receipt_kind:DISPATCH或OBSERVATION或CAPTURE或USAGE或CANCELLATION, receipt_ref:R |
| human_directions[d].provenance / GUIDANCE | principal_ref:R, authorization_ref:R, message_kind:HUMAN_GUIDANCE或GUIDANCE_PROPOSAL, guidance_version:I≥1, receipt_ids:[S] |

CALL 与 reservation/spec 的 scope、request/execution/invocation/attempt、epoch/version、grant 单位与金额必须逐项一致；原 task/purpose/responsibility/attempt_group 不重造。MAIN 的非 null owner.backend_binding_ref 必须匹配该次 spec；worker/SURVEY 使用各自可信已注册 spec binding，不冒用 MAIN 身份。INBOX.OPEN 当且仅当 gap=null，GAP 必须有 gap，last_page_ref 仅初始可 null。RECEIPT 的五个 kind 依次只解码为原 v1 DispatchReceipt、ExecutionObservation、CaptureReceipt、UsageObservation、CancellationReceipt；指导回执直接用完整 v1 SteeringReceipt，不新增公共 DTO。

TRH/FDH ownership.logical_main_id=原 MAIN-<iid>，使用原 run_control.control_version；SURVEY 必须 null，使用 infrastructure_control_version，owner 只拥有基础设施控制权。只有 TRH/FDH 允许 MAIN 与 guidance 操作。owner_epoch 接管严格 +1；控制/owner/grant 变更使控制版本恰增一次（原 reducer 已增则不再增），其他命令不自动增加；scope_versions、strategy revision 各保留自己的含义。grant revision 随授权内容修改 +1、归属/单位不变。journal sequence 每提交 +1；guidance_version 按实例新指导保存 +1。时间、PID、lease 均不能替代版本或执行证据。

/2 commit 顶层沿用 journal.py:136–138 字段。内部事件 schema=pmrh.control-event/1，精确公共字段为 schema,type,operation_id,idempotency_key,scope,expected_head:H,owner_epoch:I,control_version:I,payload,decision_ref:R；scope 同上，type=DECISION.action。闭合 payload 如下，所有 native_event 必须匹配第 5 节唯一静态桥及其原字段校验：

| type | payload 精确字段 |
| --- | --- |
| ACTIVATED | profile_ref:R, owner_id:S, backend_binding_ref:R或null |
| OWNER_ACQUIRED | owner_id:S, backend_binding_ref:R或null, takeover_evidence_refs:[R] |
| CONTROL_APPLIED | native_event:原严格 control event |
| GRANT_REVOKED | budget_grant_id:S, expected_revision:I≥1, reason_ref:R |
| CALL_PREPARED | task_ref:R, candidate_ref:R, spec_ref:R, reservation_ref:R |
| SLOT_CONFIRMED | request_id:S, pool_id:S, token:S, pool_revision:I |
| SEND_STARTED | request_id:S, send_boundary_id:S |
| EXECUTION_RECEIVED | receipt:上述 RECEIPT |
| INBOX_PAGE_RECEIVED | request_id:S, producer_ref:R, binding_ref:R, page_ref:R |
| CANCEL_UNSENT | request_id:S, not_sent_evidence_ref:R |
| CANCEL_REQUESTED | request_id:S, reason_ref:R |
| UNKNOWN_DISPOSED | request_id:S, disposition:ABANDON_UNKNOWN或CONFIRMED_NOT_SENT, evidence_refs:[R] |
| SCIENCE_ADMITTED | request_id:S, capture_ref:R |
| STRATEGY_APPLIED / COMMUNICATION_APPLIED | native_event:第 5 节闭合的原事件 |
| GUIDANCE_SAVED / GUIDANCE_OBSERVED | 分别 direction_ref:R / steering_receipt_ref:R |

RECOVER_RECEIPT 是只读内部动作，参数仅 scope、operation_id；不出版上述事件、不更改 cursor/授权。其当次可信认证仍必需；若审计 context 使用 DECISION.action，则该只读标签也仅允许用于此查询，不能成为 journal type。

3. 请求状态、负债、槽位与 MAIN lane【F2】

CALL_PREPARED 在一个项目事务运行原 PREPARE 后立刻运行原 RESERVE，冻结 task/spec/reservation、建立 READY、初始化 inbox；只发布最终 RESERVED、execution_kind=SYNTHETIC_TEST_ONLY。不存在已出版的 /2 PREPARED/None 过渡。保留 execution.py:210–253、299–327 全部检查：consumer/职责/attempt_group、D0/target、sample/retry、grant/project 额度、非 assistant、report 特许范围、ACTIVE/current mission、未 fenced、task control、阶段/非阶段 lane、executor_contract/model_policy 完全一致及 changes.live_check。发送前重验同一组可变事实，状态前置改为本请求 RESERVED，lane 计数排除自身并采用下述 /2 关闭谓词；不是重新扣一个单位。假来源必须在捕获前固定，防止 changes.py:270 的 HUMAN fallback，capture 独立性凭据仍标 synthetic（execution.py:336–357）。

表中 K 始终 SYNTHETIC_TEST_ONLY；“保持”含 CAPTURED/SETTLED 不倒退。冲突规则优先于其他行；receipt_ids 只追加去重，not_sent_ref/termination_ref 一旦非 null 不覆盖，额外原件留在 receipt 历史，conflict 只能 false→true。phase 只能 READY→ATTEMPTED→CLOSED 或 READY→CLOSED。slot 释放与 MAIN lane 开放不是同一事，capture/科学 SETTLED 本身都不证明 backend 已停止。

| 事件/证据 | native execution_state / acceptance | phase / charge | 槽位与 MAIN lane |
| --- | --- | --- | --- |
| CALL_PREPARED；SLOT_CONFIRMED | RESERVED / NOT_SUBMITTED，K | READY / RESERVED；boundary=null | worker 未确认 slot 禁发；MAIN 无 token 仍占逻辑 lane |
| SEND_STARTED | UNKNOWN / 保持，K | ATTEMPTED / UNKNOWN_RESERVED；boundary 唯一 | 持有；禁重发 |
| 可信 SENT 或 RUNNING | SENT（已捕获/结算则保持），K | phase 保持 / SPENT_OR_SETTLED | 无终止证明仍持有 |
| SEND_OUTCOME_UNKNOWN、普通 UNKNOWN、无终止证明的取消 ack | 保持，K | 保持；已确认消耗不倒退 | 持有；不把 ack 当停止 |
| 有实际 seal 的 CaptureReceipt | CAPTURED / PENDING，K | 未证明终止则 ATTEMPTED，否则 CLOSED；SPENT_OR_SETTLED | 尚无 terminal 则不释放；单独 capture 不接纳数学 |
| 原始证据证明 TERMINATED（含 CancellationReceipt.termination=OBSERVED 且证据核验） | 无 capture 时保留 SENT/UNKNOWN、NOT_SUBMITTED；不造 SETTLED | CLOSED / SPENT_OR_SETTLED；记录 termination_ref | 可释放 worker；无 capture 则 fenced；MAIN 依下述谓词 |
| SCIENCE_ADMITTED | 原 validator 的 SETTLED/实际 acceptance，K | phase 保持 / SPENT_OR_SETTLED | 科学结果与执行终止分别核验 |
| READY 本地确证未越发送边界；或可信原执行 NOT_SENT | CANCELLED_BEFORE_SEND / NOT_SUBMITTED，fenced，K | CLOSED / RELEASED；not_sent_ref 非空 | 可释放；无冲突/GAP 可开放 lane |
| CANCEL_REQUESTED；ABANDON_UNKNOWN | fenced=true，其他保持 | 保持；不退款、不重发 | 无 terminal/not-sent 仍持有 |
| 已认证 SENT/NOT_SENT 相矛盾（任一顺序） | UNKNOWN；已有 CAPTURED/SETTLED 保留历史；fenced，K | CLOSED / SPENT_OR_SETTLED；evidence_conflict=true | 风险占用/全池阻断，MAIN lane 关闭 |

UNKNOWN→SENT 由封闭 /2 receipt reducer 实现，只改上述原请求字段并执行原 strategy.request_sent 的兼容 bookkeeping；不能调用要求 RESERVED/SENT 前置的旧 SENT 分支（execution.py:328–335）。其旧 direction.status=DELIVERED 只作旧视图，不能生成 SteeringReceipt 或 READ/ADOPTED。CAPTURE 仍检查原 execution、bytes、input_window、独立性；冲突/GAP 下只存回执原件，不调用科学接纳。

新 /2 MAIN preparation 代替 strategy.py:277–282 的旧终态判定：旧 MAIN 必须无 evidence_conflict、inbox 非 GAP，且有可信 not_sent_ref，或有 termination_ref 并且（原请求已 SETTLED 或 fenced）。旧 epoch 的 terminal MAIN 被 fenced，允许当前 owner 显式重新准入；没有 capture 仍不是 SETTLED。旧 MAIN 结果可原样封存但不得应用旧策略。对同一 purpose/responsibility/attempt_group 的原未知责任，换 key/epoch 不构成重新采样许可；新 attempt 仍须原有限 retry/repair 规则。

CONTROL_APPLIED 不再允许原 CANCEL_REQUEST/RECONCILE_UNKNOWN；旧取消 PREPARED→CANCELLED_BEFORE_SEND 以及 read_projections.py:6–9 的“见状态即零费用”不可成为 /2 旁路。CANCEL_UNSENT 对 READY 的证明必须由持发送排他锁的可信服务从完整日志产生；ATTEMPTED 只能用原执行通道确证未发。GAP 时可保存 not_sent_ref，但暂不转 CANCELLED_BEFORE_SEND/RELEASED，保留原占用；补齐后重折叠全部证据。CANCEL_REQUESTED 只持久化本地 fence/取消意图，本包没有真实 cancel 运输；CONFIRMED_NOT_SENT 与 CANCEL_UNSENT 同检查。仅 timeout/PID/lease/取消请求永不退款。重开 /2 不调用旧“RESERVED 一律恢复为 UNKNOWN”的规则：无 boundary 的 READY 仍是未越边界，ATTEMPTED 才保守未知；旧格式恢复行为不改。

预算单位固定 AGENT_INVOCATION，每顶层 MAIN turn 也保留 1；不声称内部 inference/token 精确控制。四 charge 桶互斥；remaining=limit−spent−reserved−unknown_reserved，可因后到冲突为负，展示 deficit 并停止准入，不截成看似足额。released 是历史审计，不额外加一次退款。/2 所有 native budget/lane 查询都必须用本表投影，project SCIENCE/total 原边界保留；未观察 usage=null、父子 inclusion UNKNOWN 不求和。

两种冲突顺序都保留两份原件并进入同一隔离结论。SENT→NOT_SENT 不退费；NOT_SENT→SENT 即使此前释放且额度/slot 已被别的请求复用，也将原 reservation 从 RELEASED 改为 SPENT_OR_SETTLED（同一单位，只记一次）、标 conflict，保留原 release 历史，重新计入风险占用。RUNNING/capture/确证执行后终止与 NOT_SENT 冲突同理；READY 却出现可信已执行证据也隔离，不能继续发一次。不得撤销其他已发送事实以“修平”账目。phase 不回 READY，conflict 不自动清除；本最小版无冲突裁决/解除隔离动作，须后续独立决定。已接纳历史不伪造回滚或新数学判定，当前资格冻结供独立复核。

4. 每动作当前授权与 duplicate【F3、CTRL-Q3】

可信 context 由宿主受信装配注入。先验证当次认证、当前 authority 的范围/动作/撤销/有效期、根绑定、当前 epoch/version及本表要求，之后才查重复；CAP-HUMAN/HOST、模型 JSON、历史 DECISION 都不能自己授予权限。CapabilityManifest 是可验证的 backend 能力证据，不是主体授权。issued_at<expires_at，最终发送点仍须未过期。

下表 G/C 精确对应 DECISION.budget_grant_ref / capability_manifest_ref；“null”是必须 null，不是可省略。A=当前 ACTIVE grant 精确 revision；E=当前已有 grant 精确 revision（可 REVOKED）；F=原冻结调用的 manifest，且当前受信 registry 仍确认其相同能力/绑定有效。R=新的、限本 scope/原调用的 recovery 权限；不依赖被撤销的 send grant。每个 mutation 的 event epoch/version 必须是当次 current 值；仅 ACTIVATED 用 0/0。回执原 identity/spec/epoch 保持原值，不重写成当前 owner。

| 动作/子动作 | 当前主体/权限 | G / C；额外前置 |
| --- | --- | --- |
| ACTIVATED | 当前一次性 setup 装配 | null/null；第 1 节精确前缀 |
| OWNER_ACQUIRED | 当前认证 operator | null/null；CAS 原 epoch，接管不消除旧风险 |
| CONTROL: AUTHORIZE_MISSION 新 mission | 当前 operator | null/null；新 grant 内容是输出，旧 mission 持有负债不删除 |
| CONTROL: AUTHORIZE_MISSION future_configuration、EXTEND_MISSION_BUDGET、RESUME；HUMAN_DECISION 的 CONTINUE/CONTINUE_DISCOVERY | 当前 operator | A/null；原精确 human decision/领域 guard；不创造额度 |
| CONTROL: PAUSE、SET_P14_MODE、REQUEST_STOP_AT_P14、CANCEL_STOP_AT_P14；HUMAN_DECISION 的 PAUSE/END/END_WITHOUT_ADOPTION | 当前 operator | null/null；只保留原分支和 report-first 检查，不能借配置恢复 |
| GRANT_REVOKED | 当前 operator 的 revoke 权限 | E/null；payload revision=E；新撤销保留负债 |
| CALL_PREPARED、SLOT_CONFIRMED、SEND_STARTED | 当前 owner 明确委托的 admission/resource/send 服务（各动作独立授权） | A/F；精确原 reservation、amount/单位/身份、binding；CALL_PREPARED 还需剩余 1；其他不再要一个空余单位；MAIN 不调用 SLOT_CONFIRMED |
| CANCEL_UNSENT、CANCEL_REQUESTED、UNKNOWN_DISPOSED | 当前 operator 或获该动作的 R 服务 | null/null；校验原 reservation/历史 grant 存在及证据，不要求它 ACTIVE |
| EXECUTION_RECEIVED、INBOX_PAGE_RECEIVED | 当前获 ingest 权的原 producer 或 R 服务 | null/null；可信原 producer/binding/原调用、证据来源检查；不授 START/steer |
| SCIENCE_ADMITTED（worker/SURVEY） | 当前独立 admission 服务 | null/null；原 reservation/历史 grant/资格与全部科学 live guards；可旧 epoch/PAUSED 原例外，不产生新发送 |
| SCIENCE_ADMITTED（MAIN） | 当前 owner 授权的 admission 服务 | A/F；原 task epoch=current、ACTIVE、原 binding 与全部科学/策略 guards，禁止旧 MAIN 策略 |
| STRATEGY: INITIALIZED/TRIGGERED | 当前 owner 的 strategy 服务 | A/null；当前 mission、策略 CAS；无发送副作用 |
| STRATEGY: LIVE_PROPOSAL；COMMUNICATION 的 live 子集 | 当前 owner 授权、精确原运行调用的服务 | A/F；原 task epoch=current、ACTIVE、原 binding、冻结输入与独立性规则 |
| COMMUNICATION 的 recovery 子集 | 当前 R 服务 | null/null；只确认旧暴露、封窗、撤回/拒绝，不增加输入/任务 |
| GUIDANCE_SAVED | 当前认证人类的 guidance 权限；或明确 proposal-only 权限 | null/null；后者不能写 HUMAN_GUIDANCE；不是预算/继续授权 |
| GUIDANCE_OBSERVED | 当前获指导回执 ingest 权的通道/接收者或 R 服务 | null/null；原 receiver identity；采用效果须当前 MAIN 且第 5 节接纳 |
| RECOVER_RECEIPT | 当前 scope 内 query-original-receipt 权限 | null/null；读取当前授权后的原 operation 结果，绝不调用原动作 |

Mutation 重试先满足上述当前条件（含 applicable grant revision、reservation、F），再以项目内 operation_id/idempotency_key 查同一 canonical command。内容不同冲突。已成功操作可以忽略它已消耗的 expected_head，但不能忽略其过时 epoch/version/grant/F；此时只能走新授权 RECOVER_RECEIPT。CALL_PREPARED 重复核验原占用及其归属，不要求再有剩余 1，也不扣第二次；SEND_STARTED 重复只返回原结果，绝不二次启动。改变 control version/grant revision 的原命令普通重试因版本过时而拒绝，另查回执。恢复入口不接受“旧 START permit 尚未过期”作为新的 read/ingest 权限。原 native 早返回点 execution.py:201–208、strategy.py:683–697 必须在这个 gate 之后。

5. 静态 native 桥、原子边界及排他【F3、M2】

以下是 /2 全部写白名单；外部不得直呼 reducer 或带任意 callback/module/patch。每个桥均先走第 4 节，再获跨进程 egress，复核后才调用静态原代码；内部派生副作用与命令同事务，不另开绕过认证的 facade。/2 reader 也按静态事件契约核对 delta 写集合、上述 cross-field 与单调规则；checkpoint 不能凭额外字段授予权力。

| 写入口 → 唯一允许桥 | 精确允许内容 |
| --- | --- |
| storage_compat.commit_control → CONTROL_APPLIED | 仅第 4 节枚举的 AUTHORIZE_MISSION、EXTEND_MISSION_BUDGET、PAUSE、RESUME、HUMAN_DECISION 三个结束/暂停及两个继续子动作、SET_P14_MODE、REQUEST_STOP_AT_P14、CANCEL_STOP_AT_P14；END 的 rounds.record 后置写不得独立绕门，在最小 /2 禁用此自动后置写、保留已提交 END/原报告要求。 |
| commit_execution → CALL_PREPARED / receipt / SCIENCE_ADMITTED | PREPARE+RESERVE 只由 CALL_PREPARED 同事务产生；SENT/UNKNOWN 只由 SEND_STARTED/已验证 receipt 映射；CAPTURE 只由原 seal 映射；SETTLE 只由科学 admission 结果；其余 raw execution events 拒绝。 |
| storage_compat.commit → SCIENCE_ADMITTED | 只允许已有 request 的原捕获 bytes 经 changes.revalidate/apply_validated；接纳、原 report_event/strategy_change/科学 invalidation、request settlement 同一次 HEAD。不得 /2 后走 source-input、任意 validated dict 或伪造 HUMAN。 |
| commit_strategy → STRATEGY_APPLIED | 仅 STRATEGY_INITIALIZED、STRATEGY_TRIGGERED、STRATEGY_LIVE_PROPOSAL；最后者必须原 MAIN 当前运行请求，不能早 duplicate；HUMAN_DIRECTION_SUBMITTED 只由 GUIDANCE_SAVED 私有生成。 |
| commit_communication → COMMUNICATION_APPLIED | live 子集恰为 COMMUNICATION_LINKS_REVISED、COLLAB_GROUP_BOUND、MESSAGE_PUBLISHED、MESSAGE_ACKED、INPUT_DELIVERY_PREPARED；recovery 子集恰为 MESSAGE_WITHDRAWN、INPUT_DELIVERY_CONFIRMED、INPUT_WINDOW_SEALED、TOOL_CONTROL_REJECTED。各保留原 payload/读写集/独立性校验，不准补发暴露。 |
| main_session.submit_direction → GUIDANCE_SAVED | 保留原 text/kind/source/supersedes/revokes；provenance 由可信 context 生成，DISCUSSION/proposal 不进入授权入口。 |
| host_pool acquire/release → 第 7 节 typed pool；native_main 控制入口 → 已列控制命令 | native_main 的真实 execute/Rpc/turn/bind/usage writer 全部 /2 禁用；slot MAIN 豁免仍注册根。 |

直接 commit_usage/commit_report/commit_survey/commit_assistant/commit_incident/commit_native_main、未列 strategy/control/execution 事件和独立 rounds 后置写均拒绝 /2；只保留科学 reducer 内已验证的派生报告/SURVEY 结果。这是候选 profile 的明确功能限制，不改变 /1。v1 UsageObservation 在 inbox 原样保存，不擅自伪造成 native BACKEND_OBSERVATION。源码入口依据 storage_compat.py:45–191；strategy.py:100–166、607–681；communication.py:175–252；input_delivery.py:67–109；changes.py:394–455。

egress 必须为跨进程 OS 排他锁，位于可信装配固定的锁根，key=H(canonical([pool_id,project_id,genesis_commit,instance_id]))，不能用进程内 threading.Lock、未验证路径、PID 或模型字符串当锁身份。所有上述 direct/native 桥、owner/pause/revoke 与发送都参加。多实例影响先按 (project_key,instance_id) 排序取得涉及的全部 egress，复核实例集合。全序：egress → pool.lock → project.writer；可省略未用前缀，禁止反向升级/同时持两个项目 writer。

发送在 egress 下、pool→project 下重验，先提交 SEND_STARTED(UNKNOWN)，释放 project/pool 锁后仍持 egress，在真正有界首次副作用点再次检查许可期限，只启动一次。PAUSE 在取得同锁并提交后生效；已经过边界的执行仍在途。进程死亡自动释放 OS 锁不消除 UNKNOWN。未来 backend 若不提供该可验证边界则 UNSUPPORTED_CAPABILITY；现有同步 start/stream、Popen、native root gate 不被假定满足它，本轮无真实运输。

数据顺序：原 bytes → reservation → 含 reservation_ref 的 v1 spec → command（事件去掉 decision_ref）hash → DECISION/event → delta/journal → HEAD 后派生 committed refs。owner/guidance/grant 的 authorization_ref 可指本次 DECISION，但命令输入不含这些生成后的授权元数据；新 grant 决策的 G=null，修改旧 grant 的 G 只指先前已提交 revision。PROFILE 只指过去 genesis/setup_head。禁止自己 commit/hash 或互相循环引用。GUIDANCE_OBSERVED 的 ADOPTED 仅能引用已提交的实际策略回执，或在同一科学/策略事务形成确认（不引用未来 commit）。SAVED/DELIVERED 不推断 READ；原 input_delivery 未确认暴露也必须进 seal。

6. 最小执行 inbox 游标事务【CTRL-Q1、F3】

每 request 仅一个固定 RUNNER 流，stream_id=invocation_id；不实现 provider 流、多订阅者、一般消息系统或 DEV07 运输。CALL_PREPARED 从可信 synthetic producer/binding 初始化 INBOX：cursor(after_sequence=0,last_event_id=null)、OPEN、gap=null、last_page_ref=null。binding 与原 spec/handle 一致，创建后不换源。用完整、未变更的 v1 EventCursor/RunnerEventPage；依据 dto/events.py:89–103、150–224。INBOX 的 cursor 是执行源进度，不是项目 journal cursor，更不是 communication.inbox。

INBOX_PAGE_RECEIVED 验证当前 ingest 授权、原 producer/binding、scope、原 invocation/request/execution/attempt；envelope.status=OBSERVATION、trust_origin=classification=SYNTHETIC_TEST_ONLY、actor_kind=SYNTHETIC，actor_principal_ref=原 producer_ref，owner_epoch/control_version 与原冻结调用相同，payload/hash/raw refs 可验证。STARTED.payload 只接受 v1 ExecutionObservation(SENT或RUNNING)，OUTPUT_AVAILABLE 只接受已 seal 的 CaptureReceipt，TERMINATED 只接受 ExecutionObservation(TERMINATED)，USAGE 只接受 UsageObservation；不满足此窄映射拒绝整页。DISPATCH/CANCELLATION 仍走 EXECUTION_RECEIVED，直接回执不移动 stream cursor。

| 输入 | 单次项目事务效果 |
| --- | --- |
| COMPLETE 且 requested_cursor 精确等于 durable cursor | 全页验证、保存原 page/event/receipt refs、按第 3 节折叠副作用、去重事实及 next_cursor 一起提交；任一无效不提交部分页。receipt_id=event_id，序号必须连续，next.last_event_id 必须是末事件。 |
| EMPTY | 必须 cursor 不变、无 events/gap；可只回只读结果，不出版无变化 HEAD。不能把已有 GAP 清空。 |
| GAP | v1 page 要求 events 空、next=requested；保存页与 gap，INBOX.state=GAP，cursor 不变；其 first_missing_sequence 必须紧接 durable cursor+1，否则不能声称已消费中间事件。 |
| 有效 COMPLETE 的 requested_cursor 超前 durable cursor | 保留原页作诊断，生成 v1 EventGap(DISCONTINUITY, durable+1..requested.after_sequence, resnapshot_ref=null)，置 GAP；不摄入该页事件、不前进 cursor。 |
| 旧页/重投 | 只有每个 seq/event_id/hash 与已提交历史完全相同且整页已消费，才返回原结果；不回退 cursor、不二次作用。交叠但含未消费尾部拒绝 VERSION_CONFLICT，要求从当前 cursor 重取，不能裁剪后偷偷应用。 |

序号→event_id/hash、event_id→原 hash、receipt hash 去重索引从已提交 intake 事件/page 按前态重放，仅登记实际摄入的连续页，不把超前诊断页当已消费；不新增第二份可变账本。同 ID 异 bytes 拒绝，不覆盖原件；相同 receipt bytes 换 ID 可保留发生记录但不重复扣款/接纳。page.duplicate_event_ids 只可引用该流已知一致的原事件，不授予去重豁免。结构合法但含相互矛盾的有效回执仍原样提交、cursor 可前进，同时设置第 3 节 conflict；“消费过”不表示可信科学结果。

GAP 阻断本请求的科学接纳、lane/slot 释放和该实例新准入；仍可在新的 ingest 授权下读取/保存原回执。只能从原 cursor 连续补齐缺段：部分补齐收紧 gap.first_missing_sequence，补到原 last_missing_sequence 才 OPEN/null；cursor 永不跳跃。若 retention 导致无法补齐，本最小 profile 停留 GAP；可读固定快照了解事实，但 EventGap.resnapshot_ref 不自动改 cursor，不实现 snapshot-skip/重设流。所有 gap 页/诊断保留 journal 历史。源确认/ack 只能在本地 HEAD 成功之后；不假设真实源有 ack 或 exactly-once。

7. pool、跨账及保守恢复【F2、M2】

pool 仍用 pmrh.host-pool/1，精确字段 schema,pool_id:S,revision:I,projects:map,slots:map,demands:map,cursor:I。project_key=H([project_id,genesis_commit] canonical)，projects 行={project_id,genesis_commit,root_binding_id}；root_binding_id 由可信注册解析目录 capability，不读项目内路径。所有项目包括只有 MAIN 的项目，在激活前注册同一池；相同 genesis/key 换根即拒绝，不得因 slot 豁免跳过。pool_id/锁根/运行根由可信装配唯一指定，环境变量不能分裂全局池。

token=H([pool_id,project_id,genesis_commit,instance_id,prepare_operation_id,request_id] canonical)；slots 行精确字段 project_key,instance_id,operation_id,request_id,reservation_ref:R,state:HELD或RELEASED,release_evidence_ref:R或null。HELD 时 release=null，RELEASED 时非空，tombstone 保留。demands 的 key=H([project_key,instance_id])，行={project_key,instance_id,ready:I}；仅公平提示，cursor 原轮转语义。总文件 4 MiB、各 map 4096 行，revision 有效修改 +1，超限拒绝。

项目 intent+预算 → pool HELD → 项目 SLOT_CONFIRMED，不假装跨文件原子事务。每次 pool acquire/confirm/release/send（包括 MAIN）在 pool 锁下读取所有已注册项目的已验证 HEAD/相关 request，核对根、slot 与负债；读失败或不符合协议阶段的单侧记录就停止新发送、保留风险。合法 READY 等 slot、HELD 等项目确认是可恢复中间态，前者不得发送、后者计占用，不误判成可删除孤儿。注册后尚未激活的根只能匹配第 1 节 setup 前缀且不能发送。逐项目固定 HEAD 有界读取，不持另一项目 writer；所有会改执行负债/释放资格的 receipt/intake/cancel/science 桥也按 egress→pool→project 排他，故观察冲突与其他项目发送可排序。普通观察不改变预算也不能走绕过门的旧 writer。

slot 的有效占用=HELD，或其原 request.evidence_conflict（即使 tombstone 已 RELEASED）。发现冲突阻断整个共享池的新准入/发送，计算过量风险但不谎报它从未超售；MAIN 冲突虽无 worker slot 也阻断池。无需再加可丢失的 quarantine ledger。项目先记录冲突后若进程崩溃，下一池操作仍从项目 HEAD 发现并阻断。先有可信项目 terminal/not-sent 且无 GAP/conflict，才可幂等写 RELEASED；PID/lease 不释放。限制继续为阶段 8、host 20、SURVEY 1；MAIN 不占阶段槽但耗预算且占逻辑 lane。此保守有界全注册表核验适用于小型离线 fixture，不承诺大规模性能。

旧 host_pool.py:21–39、44–114 不识别新 schema，也把 MAIN 在注册之前豁免；故新 ledger 只在旧 runtime 无法访问的 synthetic root，不能声称旧池天然 fail-closed。真实根、生产共存/切换/迁移均未授权。

8. 定向成对测试与崩溃矩阵（PLANNED / NOT_EXECUTED）

| 项 | 正例 / 负例及边界 |
| --- | --- |
| F1 | 上述精确 TRH 前缀可激活；缺 target、注入 state、旧项目、混 /1、额外 mission/source、假 checkpoint 拒绝；FDH 三源与 SURVEY 无 MAIN 配对。 |
| F2 状态 | PREPARE+RESERVE 原检查全过才见 RESERVED+SYNTHETIC；任一 live/contract/lane 检查失败无 HEAD；UNKNOWN 后真实 SENT 可映射，对照 raw native SENT 拒绝；捕获无终止不释放，终止无捕获不造 SETTLED。 |
| F2 负债 | READY 确证未发释放；UNKNOWN/取消 ack 不释放；SENT→NOT_SENT 和 NOT_SENT→SENT 都隔离；后者另配已复用额度/slot，断言补记一次、负 remaining、有效风险占用、全池停止。 |
| F3 | 当前授权重复返回原请求且额度无需额外 1；撤销 grant/manifest/owner 后相同 key 拒绝；新 recovery 权限仍接纳原证据/只读找回；复用旧 START、伪造主体、跨 scope、错原 binding 拒绝。逐个白名单桥测 gate 在 duplicate 前；全部未列 writer 拒绝。 |
| CTRL-Q1 | 连续页一次提交 receipts+cursor，重复页无二次作用；错 scope/producer/hash、跳 seq、未知 payload 整页拒绝；超前页/GAP 不前进，补齐才解除；交叠尾页不裁剪；direct receipt 不动 cursor；删投影后重建去重/进度。 |
| M2 | 两个进程竞争同 canonical egress，只能一方越边界；pause 两种先后顺序；clone 改路径、另造 pool、MAIN 绕根注册均拒绝；两个合成项目测 8/20/SURVEY1 与 MAIN 计费。 |
| 兼容/科学 | 原 /1/native 语义不变、旧 reader 对 /2 HEAD/as-of 拒绝；旧 epoch MAIN 只封存；原 paused sealed worker 例外仍受科学 guard；D5/P14 等待不会因 timer/guidance 恢复；ADOPTED 必须有真正策略接纳证据。 |

| 崩溃点 | 恢复合同 |
| --- | --- |
| 原 bytes 后、项目 intent HEAD 前 | orphan 不可见；只重做获当前授权的本地准备 |
| intent 后/响应前；pool HELD 后/项目确认前 | RECOVER_RECEIPT 找回原操作；同 token 补确认，不再次扣款/按 PID 清理 |
| SEND_STARTED HEAD 后、启动前或启动后/回执前 | 都保守 UNKNOWN；绝不自动 retry |
| page bytes 后/inbox HEAD 前 | durable cursor 不动，源可重投整页 |
| inbox HEAD 后/ack 或响应前 | receipts、charge、cursor 全在同一边界；重投无第二次作用 |
| NOT_SENT release 后、迟到 SENT；或冲突 HEAD 后/pool 操作前 | 原释放历史保留，项目负债补回；下次全池核验阻断，不清空 tombstone |
| terminal/inbox HEAD 后、pool release 前 | 证据与 GAP/conflict 全验后幂等释放；不把观察当科学结算 |
| owner 接管/旧 MAIN 未停止；HEAD/fsync 结果未知 | 保留原 epoch 身份和风险；先查已发布事实，不开第二 MAIN、不重发 |

真实 backend E07/C02/B03、DEV07 S3、真实 root gate/取消/steer/capture 不在本次测试范围；fake 有一次效果不证明远端 exactly-once。不重跑无关已接受 DEV02/05 suites，原 58+46 测试定义不改。

9. 实施边界、文件与限制

待格式批准后拟改文件及直接消费者：新增 pmrh/application/control.py（上表命令、当前授权及协调）；pmrh/adapters/storage/control.py（封闭 /2、intake/replay）、pool.py（typed pool/跨进程锁）；改 adapters/storage/journal.py、format.py（sticky/preflight）、pool_read.py 与 application/read_projections.py（新 charge/lane/risk 只读投影）；research_studio/storage_compat.py、store.py（全部门控入口），execution.py、scheduler.py、runner.py（准备/准入/发送），workflow_instances.py、strategy.py、main_session.py（owner/控制/指导），host_pool.py、communication.py、input_delivery.py、native_main.py（各精确桥/拒绝真实执行），changes.py 的 validator_identity（实际验证依赖闭包）。如 engine.py facade 被接入 /2，它只能调用已列内部命令；本最小版直接旧 facade 非白名单入口拒绝，故不承诺修改它或全面兼容 UI。

待批准的定向测试文件仍为 tests/devpr06/test_control.py、test_recovery.py、test_format.py；架构边界登记 config/architecture-exceptions.json、scripts/architecture_deps.py、scripts/check_legacy_scope.py，拟新增 scripts/control_scope.py；隔离入口 tests/devpr06/child.py、scripts/offline_control.py、scripts/control_sandbox.py、.github/workflows/devpr06-offline.yml。只有实际依赖需要时才修改这些声明路径，禁止通配放行。pmrh/ports/interfaces.py 和 dto/ 无修改；以上全是候选修改清单，本轮修改源文件数为零。

保留原格式限额：普通 reader 完整 closure ≤4096 files/128 MiB，DTO ≤8 MiB/4096 元素/depth64/nodes262144，证据 write/slice ≤1 MiB；所有新增 decision/page/spec/raw refs 纳入闭包，orphan/未来/跨 scope 引用不读，checkpoint/SQLite/索引可丢弃但 journal 仍可恢复。原 legacy 单 blob 256 MiB 不扩大 /2 closure。超限不出版 HEAD；未知格式/动作不得降级到旧 writer。

部署只限全新 synthetic fixture。回滚先停新准入、保留兼容 reader 和全部原件/负债；禁止把 HEAD 指回 /1、清零 pool、删除 UNKNOWN、用旧备份声称远端已停止。/2 无 PORT 磁盘接口、无真实运输、无 gap snapshot-skip、无冲突自动解锁、无新实例/上传/完整报告服务，均是明确最小范围。

审批前没有值得接入的完整无格式 DEV06 切片：持久 owner、可恢复重复、reservation/outbox/inbox 都依赖本格式；不写临时 policy stub。本轮仅门禁/角色隔离、针对性源码阅读、文档与 JSON 标准库一致性检查。R2 isolation PASS 不等于产品验收，最初 STOP 保持原记录。本稿交 Controller 定向复审与人类格式决定；作者不自称修复已被接受，也不实施或等待后续授权。
