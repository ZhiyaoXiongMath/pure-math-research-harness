# DEV-PR-02 — Ports、不可变 DTO 与显式错误合同

状态：IMPLEMENTED / TESTING。不是独立审核结论，不是 MAIN ACCEPTED。

开发基线：`efd2be4e93ca8f1ee9f6a03fa53df6a1f008c8fb`；Git tree：`bef94b15e4b0567349d349cc4f74b086c0578962`。

分支：`feat/dev-pr-02-ports-dto-contracts`。最终 PR 编号、HEAD、运行证据在 PR 描述及开发交付报告中记录，不能把本文中的版本化状态当成实时 GitHub 状态。

## 1. 范围、权威与兼容边界

依据当前 AGENTS、CONTRIBUTING、ADR-0001/0002、ROADMAP、MAIN-OPERATING-PROTOCOL、ACCEPTANCE-BASELINE、DEV-PR-01 Handoff/独立复验及原实施计划 §2/4–8/13/15。GOV-01 快照中的 DEV-PR-02 未授权记录保留历史身份；本轮用户明确授权是进入本工作包的依据，不补造 DEV-PR-01 历史 MAIN 验收。

只增加标准库 Port/值对象/纯校验、离线测试、受控测试入口和 CI。没有接入旧执行路径，没有真实 Runtime/Provider/Storage/Auth adapter，没有推进 DEV-PR-03，没有模型、科研项目或数据迁移。

`research_studio/` 继续保持原 tree `f49a0b4e51d9a9602f82d7dc9fdf33a3e563b7da`；原 CLI 默认行为、PROJECT_ASSISTANT 禁令、证据 schema 身份、MAIN/Goal 和预算不变。没有更改架构例外或原 DEV-PR-01/Phase 0 workflow。

## 2. 公开导入与版本

正式公开 Ports 从 `pmrh.ports` 导入：

```python
from pmrh.ports import (
    AgentRunner, ModelProvider, OrchestrationEngine, EvidenceRepository,
    EventRepository, PolicyGateway, UnitOfWork, Clock,
)
from pmrh.ports.dto.specs import AgentInvocationSpec, InferenceSpec, ModelSelection
from pmrh.ports.dto.core import ErrorEnvelope, PortError
from pmrh.ports.dto.wire import ContractViolation, decode_wire
```

实际 Protocol 定义：`pmrh.ports.interfaces`。纯能力匹配：`pmrh.ports.capabilities.check_capabilities`。

所有 DTO 的 wire schema 为 `pmrh.ports/1.0`，另有 `dto_type` 精确区分类型。Engine checkpoint 的执行 schema 单列 `pmrh.execution-checkpoint/1`，不替代数学证据 schema。CI 回执另用 `pmrh.devpr02-ci-receipt/1.0`，不得与产品 DTO 混用。

本版本采用严格封闭 schema：未知类型、字段、enum、主/次版本均拒绝；缺失字段不能从模型文字或 adapter 默认值推断。即使字段允许 null，wire 中也必须显式存在。没有自动编号、迁移、向下转换或忽略未知字段的行为。后续新增/重命名字段必须经过兼容性评审及版本决策。

### 2.1 全部公共值对象

| 模块（均在 `pmrh.ports.dto` 下） | 公共 DTO |
|---|---|
| `core` | ExactRef, Scope, TimePoint, ObservedIdentifier, Quantity, InvocationIdentity, ControlSnapshot, StateAxes, ErrorEnvelope（PortError 为同一类型别名） |
| `capability` | CapabilityManifest, BudgetRequirement, CapabilityRequirements |
| `specs` | ModelParameter, ModelSelection, AgentInvocationSpec, InferenceSpec, ModelDescription, RequestValidation |
| `events` | EventEnvelope, EventCursor, EventGap, RunnerEvent, ProviderEvent, EventPage, RunnerEventPage, ProviderEventPage |
| `execution` | PreparedInvocation, InvocationHandle, DispatchReceipt, ExecutionObservation, SteeringMessage, SteeringReceipt, CancellationReceipt, CaptureReceipt, RecoveryEvidence, RecoveryReceipt, UsageDatum, UsageObservation, RawUsageEvidence |
| `control` | OperationIntent, OperationPermit, AuthorizationDecision, PermitVerification |
| `storage` | ReadBoundary, EvidenceSlice, EvidenceWrite, VersionExpectation, TransactionHandle, CommitBatch, StagingReceipt, CommitReceipt, RollbackReceipt, EventVerification |
| `orchestration` | TechnicalAction, ActionRequest, ActionPlan, EventAcceptance, EngineCheckpoint, QuiesceRequest, QuiesceReceipt |

受约束取值集中于 `dto.enums`；不是任意字符串或 `supports_everything`。`dto.wire` 的注册表只加载本包源码定义的 DTO，不按 wire 中的名称导入第三方模块。公开类型必须有正例构造并完成 roundtrip；测试将样本覆盖集合与实际 DTO 注册集合比较。

## 3. 方法签名与副作用边界

所有方法是同步 Python Protocol。成功返回明确值对象；操作拒绝/外部失败返回 `ErrorEnvelope`。构造/解码失败抛 `ContractViolation`，其中 `code` 为同一错误枚举；缺少 Python 构造关键字由 Python 抛 `TypeError`。不把原始异常信息塞进普通诊断。

| Port | 方法 | 契约 |
|---|---|---|
| AgentRunner | `describe_capabilities()` | 返回有来源的 manifest；不探测登录或推理 |
| | `prepare(spec)` | PreparedInvocation 或错误；允许明确声明的本地准备，不是无副作用 query，更不是启动 |
| | `start(prepared, permit)` | DispatchReceipt 或错误；必须在发送边界重新验证许可；SENT、NOT_SENT、SEND_OUTCOME_UNKNOWN 独立 |
| | `events(handle, cursor)` | RunnerEventPage 或错误；保留原事件引用、连续序号、游标、缺口 |
| | `inspect(handle)` | ExecutionObservation 或 UNOBSERVED；不创建新 turn |
| | `steer(handle, message, permit)` | SteeringReceipt；SAVED 不意味着 DELIVERED，DELIVERED 不意味着 READ/ADOPTED |
| | `cancel(handle, permit)` | CancellationReceipt；请求确认与终止观察分开 |
| | `recover(handle, evidence)` | RecoveryReceipt；仅检查、重新附着既有执行、读取原 capture；没有重新采样模式 |
| | `seal_capture(handle)` | 原件 CaptureReceipt；不产生数学资格 |
| ModelProvider | `describe_model(selection)` | 冻结选择对应支持说明；actual_model 不伪装成观测结果 |
| | `validate_request(spec)` | 验证可支持参数/模式，仍要求 inference permit |
| | `stream(spec, inference_permit)` | `Iterator[ProviderEvent | ErrorEnvelope]`；最多一次明确准入的发送尝试；惰性实现须在实际发送前复验 |
| | `inspect(provider_request_id)` | 已观察执行或 UNOBSERVED；不生成不存在的 provider ID |
| | `cancel(provider_request_id, permit=None)` | 兼容单参数调用，但无有效授权明确拒绝；取消本身不能授权新 inference |
| | `normalize_usage(raw_evidence)` | 只接收原始证据身份 DTO，不接收 SDK response；计数及包含关系保持未知 |
| OrchestrationEngine | `accept_event(event, boundary)` | 先经可信仓储核验 exact committed event，再去重 |
| | `next_actions(request, permit)` | 只消费有具体 MAIN 决策依据的已选技术动作，不按 P08/P09 等编号选路 |
| | `checkpoint()` | 运行位置和已提交依据；不作为数学真相或控制授权 |
| | `resume_execution(checkpoint, permit)` | 检查当前控制；不得用旧 checkpoint 恢复旧权限/预算或重放发送 |
| | `quiesce(request, permit)` | 阻止新派工，不抹掉在途身份，不暗示已终止 |
| EvidenceRepository | `read(ref, boundary, offset=0, max_bytes=65536)` | 精确版本/边界内有界 bytes slice（base64 wire）；不修复或写回 |
| EventRepository | `read_events(cursor, boundary, limit=256)` | 权威 journal 的连续分页；真实缺口必须 GAP |
| | `verify_event(event, boundary)` | 不能仅信任 DTO 的 COMMITTED/actor/trust_origin 文本 |
| PolicyGateway | `authorize(intent)` / `verify(permit, intent)` | 可信调用方、注册决定、scope/action/payload/control/grant/capability/budget 的判定边界 |
| UnitOfWork | `begin(expected)` / `stage(tx, batch)` / `commit(tx, permit)` / `rollback(tx)` | Stage 未发布；commit 同一边界复验权限及 CAS；冲突不部分提交；不承诺跨全局池原子性 |
| Clock | `now()` / `monotonic_ns()` | 注入时间；单进程 monotonic 不冒充跨进程因果序列 |

读仓储采用只读 Ports，写入统一通过 UnitOfWork 合同。真实事务、journal/blob、版本回放和原始编号兼容实现留给 DEV-PR-05。没有 SQL、SQLite connection、进程 handle、Store 或网络 SDK 对象穿过 DTO。

## 4. 冻结身份、null 与不可变性

AgentInvocationSpec 保留原计划 §4.1 的全部字段组：项目/实例/Goal、逻辑 Agent/角色/职责/用途、invocation/request/execution/attempt、epoch/control、原范围/方法/指导、精确输入/read-set/可见性、输出/通信合同、runner/model binding、grant/unit/reservation、sandbox/tool、幂等/parent/correlation。

增加显式 `execution_mode`、`model_selection` 和 `capability_requirements`，避免 adapter 猜测。ModelSelection 的 wire digest 必须匹配 authorized_model_selection_ref；该“authorized”名称不是权限证明，仍须可信决策核验。

可空规则：parent_invocation_ref 的 null 表示根调用；WORKER/INDEPENDENT_REVIEWER 不能缺 stage_responsibility；MAIN/OBSERVER/ADVISOR 可无编号职责。guidance_version=0 明确表示冻结时没有指导版本，不是未观测。effort/tier/schema null 表示明确未指定/不适用，不能偷偷补一个不同选择。credential_ref 只有引用与摘要，不是凭据值。

未知 provider/backend 身份用 ObservedIdentifier：OBSERVED 必须有真实观察到的值；UNOBSERVED/NOT_APPLICABLE 必须 value=null。Quantity 同理：OBSERVED+0 是已测量零；UNOBSERVED+null 是未知；NOT_APPLICABLE+null 是不适用，三者不相等。

`frozen=True, slots=True` 之外，字段递归限制为 exact 标准标量、Enum、tuple 和已注册的同类型 DTO。构造拒绝 list/dict/任意对象；wire 的 object/array 递归重建为 DTO/tuple。输出的 JSON-compatible dict/list 是新副本，修改它不会修改原对象。拒绝 bool 当 int、静默 enum/number coercion、NaN、非法 Unicode、重复 JSON key 和任意类加载。普通赋值与嵌套容器无法改变构造后的值。

这是程序值对象合同，不是对同进程恶意反射、object.__setattr__、修改注册表或任意原生代码的沙箱保证。所有 ID 与引用应由可信应用层赋值，不可把私人正文/凭据当作“ID”。

## 5. 能力与计量

十项能力逐项给出受约束 enum 与不支持状态：continuation、steering、cancellation、dispatch_idempotency、root_turn_gate、tool_isolation、raw_input_capture、usage_coverage、internal_delegation、structured_output。

CapabilityRequirements 对每项列出明确可接受取值集合；不凭隐含强弱排序替换后端。platform/build/evidence_origin 可被固定，不自动 stock/native fallback，也不更改 model/effort/tier。

Manifest 包含 schema、adapter version、backend build/hash、platform、origin、时间和 test receipts。STATIC_DECLARATION、OFFLINE_PROBE 与 RUNTIME_OBSERVATION 不互相升级。Fake 的 SYNTHETIC receipt 只支持合成测试，不代表用户平台实测。manifest 本身也不能靠模型伪造标签得到信任；真实应用必须绑定可信来源和对应测试回执。

计量与强制控制分离：usage_coverage 只是观察覆盖；budget_gate 和 hard_budget_units 才声明可强制边界。普通 MANAGED_AGENT 的 invocation admission/aggregate usage 不得声称逐 inference 硬预算。只有显式 native inference gate 与 native root gate、足够 usage coverage 的托管合同才可以表达该能力；这里没有实现或验证任何真实 native backend。PMRS_MANAGED_LOOP 的 caller inference gate 不允许反向冒充接管托管后端内部 loop。

UsageObservation 保留 inclusion=DISJOINT/INCLUDED_IN_PARENT/RELATION_UNKNOWN。父子包含关系未知时不自动求和；内部 inference 不可见时不记为零。Fake 的 send_effects 等仅测量 Fake 副作用，不是实际模型调用计量。

## 6. 授权、幂等、UNKNOWN 与错误

OperationIntent 显式绑定 scope、操作、operation_id、payload digest、epoch/control、grant/unit/requested units/reservation、能力需求及 manifest 引用。claimed_principal_ref 只是未可信的声明。

OperationPermit 是决策描述，不是 bearer credential。仅构造、复制、反序列化、把 principal/epoch/grant 填得看似正确，都不能授予权限。PolicyGateway 必须从外部认证上下文取得主体，查询原决定、当前控制及 grant/capability 依据，并在副作用边界再次核验。真实认证、原子 fencing、累计预算/保留金额、并发撤销与最终发送竞态属于 DEV-PR-06/07，未在本轮安全验收。

FakePolicyGateway 使用仅由测试设施持有的对象身份和单独登记表演示该边界。此对象不是生产凭据方案，Python fixture context 不是认证系统，不保证分布式事务安全。

同一 key 与相同 payload 返回同一 Fake 效果；不同 payload 返回 IDEMPOTENCY_CONFLICT。NOT_SENT 必须携带确认依据；UNKNOWN 不回退 PREPARED，不生成不存在的 provider_request_id，不循环调用 Provider 或 Runner。新外部尝试必须由后续可信应用单独准入、保留原 UNKNOWN 风险和独立尝试身份。本包没有 SDK 重试或通用 retry owner。

ErrorCode 包括：UNSUPPORTED_CAPABILITY、AUTHORIZATION_REQUIRED、STALE_CONTROL_VERSION、IDEMPOTENCY_CONFLICT、NOT_SENT、SEND_OUTCOME_UNKNOWN、UNOBSERVED、EVENT_GAP、UNSUPPORTED_SCHEMA_VERSION、CORRUPT_CAPTURE、INVALID_WIRE、INVALID_FIELD、MISSING_FIELD、TYPE_MISMATCH、NOT_FOUND、VERSION_CONFLICT、TRANSACTION_CLOSED、INVALID_CURSOR、UNTRUSTED_EVENT。

ErrorEnvelope 携带操作/作用域/相关调用、原证据引用、固定可行动消息及 recovery_safety。普通错误禁止原异常/凭据/研究正文；消息来自固定安全词表，不回显失败字段值或未经信任的字段名。automatic_retry 恒为 false。科学反驳不是 transport 错误，科学 OPEN 不代表程序失败。

## 7. 事件、原件与状态轴

EventEnvelope 覆盖 schema/event/aggregate/project/instance/journal/commit 身份；aggregate/journal 序号；occurred/observed/committed 时间及 clock source；actor、trust origin、classification、visibility；correlation/causation/operation/idempotency；invocation/execution/request/attempt/activation；logical MAIN/epoch/control；backend/provider/request；payload/raw evidence refs 与摘要。

未观察到的外部身份、发生时刻等明确保留 null/UNOBSERVED。跨进程时间不替代 journal sequence 与因果关系。OBSERVATION 不带权威 commit metadata。COMMITTED 要求完整精确提交元数据；即使 DTO 能构造，Engine 还要向可信 EventRepository 核对精确 event，不能只相信标签。

EventCursor 绑定实例、stream kind、stream ID、位置和前一 event ID。COMPLETE 页必须逐一连续；EMPTY 页不移动游标；GAP 页必须含真实缺口范围，保持原游标并要求固定快照。重复事件身份单独保留，不能通过遗漏区间的空列表伪造连续性。

CaptureReceipt 只返回原 output、actual input window、raw events 与封存身份，qualification 恒为 RAW_CAPTURE_ONLY。StateAxes 分开 Control/Execution/Admission/Science；TERMINATED、CAPTURED、ACCEPTED（接纳轴）不会自动得到科学支持资格。

## 8. 测试、CI 与证据语义

测试仅位于 `tests/devpr02/`，Fakes 包含八类正式 Port。覆盖：全类型构造/roundtrip/不可变/版本；全部核心方法；能力不支持；硬预算负例；伪造/缺失/过期/越范围/旧代次授权；相同 key 重放与冲突；UNKNOWN 无重采样；raw capture、取消、指导状态分离；仓储 snapshot、CAS、原版本不可覆盖、损坏拒绝、读无修复；event gap/重复/来源核验；Engine 无 MAIN 决策不派工；检查点不覆盖 quiesce。

新增 `scripts/offline_contracts.py` 固定发现 DEV-PR-02 测试，复用原 `offline_test.environment`、受控 artifact root、descriptor 写入与 sitecustomize guard；不扩张原 SUITES。普通 `--suite`/任意命令不能进入此入口。继承的临时根名仍为 `pmrh-devpr01-artifacts-XXXXXXXX`，是重用原路径安全校验，不是把新测试伪称 DEV-PR-01。

运行命令（isolated root 必须预先创建于系统临时根）：

```sh
ARTIFACT_DIR="$(mktemp -d /tmp/pmrh-devpr01-artifacts-XXXXXXXX)"
mkdir "$ARTIFACT_DIR/offline"
PMRH_TEST_ARTIFACT_ROOT="$ARTIFACT_DIR" python -B scripts/offline_contracts.py --out "$ARTIFACT_DIR/offline"
```

CI 使用 Python 3.11/3.13 矩阵、固定 action commits、exact PR head checkout、完整历史只读校验与 legacy 冻结检查。源码快照由 git archive 产生，只是审计当前软件源码，不是重新迁移 Git 历史。测试子进程使用合成 HOME/XDG/TMP、禁常见 socket/process 操作、不读取真实科研项目、不写源码。旧 DEV-PR-01/Phase 0 CI 保持原样并需最终 HEAD 回归。

必要回执字段：source_sha、checkout_sha/tree、schema_version、test_command、test_environment、test_count、pass_fail_status、raw_log_sha256、artifact_identity、known_unexecuted_checks、源码逐文件 SHA-256。timeout/start failure 保留结构化 ERROR 与已有原始日志；缺文件、digest/源码不一致、未逐测试记录成功、源码修改、模型计量伪零等均使证据 gate 失败。上传步骤不把失败隐藏为 PASS。

网络分层：GitHub checkout/setup/upload 等 CI 基础设施会访问网络；不能用子进程 Python guard 断言整台 runner 无网络。研究模型调用计数为 null/NOT_INSTRUMENTED，observed_provider_events=NOT_MEASURED，zero_calls_verified=false。没有完整遥测时不能记零。

## 9. 验收与后续工作包

| 条目 | 本轮可验证范围 | 留给后续，NOT_EXECUTED |
|---|---|---|
| A01 | 新 Ports 的静态依赖与受控离线导入 | 完整数学内核抽取及真实部署依赖隔离 |
| A03 | 统一 invocation/event/capture DTO；Fake 方法与原件身份 | 真实 Codex/Provider transcript、断线、原始输入窗口 |
| A04 | 模式、能力、预算单位和计量包含关系的分离 | 实际调用控制、内部委派和账单核验 |
| B04 | 不支持逐 inference 硬限额的 manifest/请求明确拒绝 | 原生 gate、Provider 强制限额与端到端预算 |
| 本轮扩展 | 深度不可变、版本拒绝、显式错误、Fake 授权/幂等/游标/捕获/事务 | 真实认证/fencing/journal/崩溃恢复/生产权限 |

DEV-PR-03 继承 ReadBoundary、只读 repository、ExecutionObservation、StateAxes/错误；DEV-PR-04 继承版本化值对象与科学/执行分离；DEV-PR-05 实现精确证据与事务适配；DEV-PR-06 实现真实授权、控制、预算、outbox/inbox/fencing；DEV-PR-07 实现经过验证的 Runtime/Provider 与原始事件/usage 适配。这里没有启动这些工作包。

58 项新验收与 46 项继承验收没有整体执行，不得把 Fake 或类型测试扩展为产品 PASS。完整旧测试、真实模型/native、OS 对抗隔离、科研正确性、用户平台及项目迁移均 NOT_EXECUTED。

## 10. 评审边界与回滚

审查须重新核对最终 HEAD、changed paths、Actions head_sha、actual checkout SHA/tree、Job/Step 原日志及下载 Artifact 内容，不能只相信本文或脚本打印的 PASS。架构/授权重要跨 PR 决策由 MAIN 后续批准，不在此擅自扩大职责。

合并前关闭本 PR 可放弃未接入的端口；不自行删除他人分支。合并后通过独立软件 revert PR 撤销，不重写 Git 历史、不删原始 capture、不恢复 Goal、不改变科研事实。最终独立审核与 MAIN 验收仍由独立 MAIN 处理。
