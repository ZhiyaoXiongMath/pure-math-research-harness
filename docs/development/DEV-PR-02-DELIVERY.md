# DEV-PR-02 开发交付记录

日期：2026-10-13（Asia/Tokyo）。作者角色：本工作包开发负责人，不是独立 Reviewer 或 Development MAIN。

**代码状态：IMPLEMENTED + TESTED。独立审核、MAIN 验收：NOT_EXECUTED。**

本记录对应下面列明的实际代码提交。它在最后一个文档提交中补入；包含本文的最终 HEAD 还必须重新取得 CI 回归，最终精确 HEAD/Run/Job/Artifact 以 [PR #4](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/4) 的开发交付描述及 GitHub 实际回执为准，不循环伪造本文自身的 commit SHA。

`DEV-PR-02-CONTRACT.md` 顶部的 TESTING 是初版实现快照；本文补充其开发验证记录、修复后的约束与遗留限制。它不是 MAIN 的治理状态或合并后 Handoff。

## 1. GitHub 身份与基线

| 字段 | 值 |
|---|---|
| 仓库 | `ZhiyaoXiongMath/pure-math-research-harness` |
| 实际 PR | https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/4 |
| 开发分支 | `feat/dev-pr-02-ports-dto-contracts` |
| Base branch | `main` |
| 派发前与开发时重读 main | `efd2be4e93ca8f1ee9f6a03fa53df6a1f008c8fb` |
| Base tree | `bef94b15e4b0567349d349cc4f74b086c0578962` |
| 首次实际实现提交 | `254a0cc3a06d68a878638a1191818ca00b889632` |
| 通过本记录所列 CI 的代码提交 | `b2a00be10d45724575d989266b79a9f956dc31ee` |
| 对应代码 tree | `78b9d0b45ae011b2c7ff397293cd4f3c9e7083e1` |
| 冻结 legacy tree | `f49a0b4e51d9a9602f82d7dc9fdf33a3e563b7da` |

已读取当前 main 上的 AGENTS、CONTRIBUTING、全部现行 ADR（0001/0002）、ROADMAP、PROJECT-STATE、MAIN-OPERATING-PROTOCOL、ACCEPTANCE-BASELINE、DEV-PR-01 Handoff/独立复验/基线/Findings、架构例外、AST/隔离入口/guard/产物验证器/测试/workflows，以及原实施计划相关章节和审计发现。

最初没有在途 Open PR。GOV-01 PROJECT-STATE 的版本化快照未被改写；本次明确用户授权是 DEV-PR-02 的准入依据。DEV-PR-01 单独历史 MAIN 验收记录缺口不在此补造。没有直接修改 main，没有合并或开启自动合并。

## 2. 完整变更路径与职责

全部为新增文件，不修改原有文件。含本文最终共 33 个新增路径。

| 路径 | 职责 |
|---|---|
| `pmrh/ports/__init__.py` | 八类公开 Port 导出 |
| `pmrh/ports/interfaces.py` | 版本化 Protocol 签名、错误与副作用边界 |
| `pmrh/ports/capabilities.py` | 纯能力匹配，明确拒绝、不做后端降级 |
| `pmrh/ports/dto/__init__.py` | 轻量 DTO 命名空间，避免导入循环 |
| `pmrh/ports/dto/wire.py` | 严格类型、深度不可变、封闭 wire schema、摘要 |
| `pmrh/ports/dto/enums.py` | 错误、状态、能力、单位、来源等受约束枚举 |
| `pmrh/ports/dto/core.py` | 精确引用、统一身份、观测值、四轴状态、安全错误 |
| `pmrh/ports/dto/capability.py` | Manifest、能力要求与预算要求 |
| `pmrh/ports/dto/specs.py` | 完整冻结 Agent/Inference 请求与模型选择 |
| `pmrh/ports/dto/events.py` | 事件信封、原事件引用、游标、分页与 GAP |
| `pmrh/ports/dto/execution.py` | prepare/start/inspect/steer/cancel/recover/capture/usage 值对象 |
| `pmrh/ports/dto/control.py` | 操作意图、非凭据 Permit、授权判定/复验 |
| `pmrh/ports/dto/storage.py` | 读取边界、原件切片与未来事务合同 |
| `pmrh/ports/dto/orchestration.py` | 仅技术编排、具体 MAIN 决策、检查点和 quiesce |
| `tests/devpr02/__init__.py` | 合成测试包 |
| `tests/devpr02/fixtures.py` | 明确 synthetic 项目/模型/证据身份，不读真实项目 |
| `tests/devpr02/fake_policy.py` | FakeClock、FakePolicyGateway，独立 fixture 授权上下文 |
| `tests/devpr02/fake_runtime.py` | FakeAgentRunner、FakeModelProvider，脚本化观察与效果计数 |
| `tests/devpr02/fake_storage.py` | FakeEvidenceRepository、FakeEventRepository、FakeUnitOfWork |
| `tests/devpr02/fake_engine.py` | FakeOrchestrationEngine，不按阶段号自动派工 |
| `tests/devpr02/fakes.py` | 八类 Fake 的测试侧导出 |
| `tests/devpr02/scenarios.py` | 完整正例场景与全部公共 DTO 构造样本 |
| `tests/devpr02/test_dto_contracts.py` | 必填、类型、版本、不可变、wire、资格与错误负例 |
| `tests/devpr02/test_capability_contracts.py` | 十维能力与 A04/B04 硬预算负例 |
| `tests/devpr02/test_runtime_contracts.py` | Runner/Provider 全部方法、授权、幂等、UNKNOWN、捕获 |
| `tests/devpr02/test_storage_engine_contracts.py` | snapshot/CAS/读不写/GAP/具体 MAIN 决策与恢复 |
| `tests/devpr02/test_ci_contracts.py` | 子进程守卫、输出预检、timeout/启动失败/产物 gate 负例 |
| `tests/devpr02/test_fixup_regressions.py` | 初版失败修复的补充回归，不替换原负例 |
| `scripts/offline_contracts.py` | 固定 DEV-PR-02 合成入口，复用未修改的 DEV-PR-01 守卫 |
| `scripts/verify_devpr02_artifacts.py` | 日志、计数、SHA/tree、源码/AST 与必须产物 fail-closed 校验 |
| `.github/workflows/devpr02-contracts.yml` | Python 3.11/3.13 实际 GitHub CI，固定 HEAD 检出与证据上传 |
| `docs/development/DEV-PR-02-CONTRACT.md` | 完整 API、值对象、语义和跨 PR 继承合同 |
| `docs/development/DEV-PR-02-DELIVERY.md` | 本开发交付与失败/修复/限制记录 |

`research_studio/`、原 CLI、原科研 schema、原测试和 workflow、原 AST 扫描器、原安全 guard、架构 exception snapshot 均未修改。没有生产适配器、迁移或旧系统切换。

## 3. 冻结公开 API

Ports 从 `pmrh.ports` 导入；方法签名和纯校验见 `interfaces.py` 及 `capabilities.py`。

| Port | 公开方法 |
|---|---|
| AgentRunner | describe_capabilities / prepare / start / events / inspect / steer / cancel / recover / seal_capture |
| ModelProvider | describe_model / validate_request / stream / inspect / cancel / normalize_usage |
| OrchestrationEngine | accept_event / next_actions / checkpoint / resume_execution / quiesce |
| EvidenceRepository | read |
| EventRepository | read_events / verify_event |
| PolicyGateway | authorize / verify |
| UnitOfWork | begin / stage / commit / rollback |
| Clock | now / monotonic_ns |

`ModelProvider.cancel(provider_request_id, permit=None)` 是显式安全扩展；单参数可调用，但缺少可信授权返回拒绝。`stream` 返回 `Iterator[ProviderEvent | ErrorEnvelope]`；实现不得用内部重试掩盖 UNKNOWN 或重新发送。错误、observer query、研究拒绝和实际发送不是一个状态。

DTO 共 60 个，schema=`pmrh.ports/1.0`。精确公开导入前缀均为 `pmrh.ports.dto`：

| 模块 | DTO |
|---|---|
| core | ExactRef, Scope, TimePoint, ObservedIdentifier, Quantity, InvocationIdentity, ControlSnapshot, StateAxes, ErrorEnvelope；PortError 是别名 |
| capability | CapabilityManifest, BudgetRequirement, CapabilityRequirements |
| specs | ModelParameter, ModelSelection, AgentInvocationSpec, InferenceSpec, ModelDescription, RequestValidation |
| events | EventEnvelope, EventCursor, EventGap, RunnerEvent, ProviderEvent, EventPage, RunnerEventPage, ProviderEventPage |
| execution | PreparedInvocation, InvocationHandle, DispatchReceipt, ExecutionObservation, SteeringMessage, SteeringReceipt, CancellationReceipt, CaptureReceipt, RecoveryEvidence, RecoveryReceipt, UsageDatum, UsageObservation, RawUsageEvidence |
| control | OperationIntent, OperationPermit, AuthorizationDecision, PermitVerification |
| storage | ReadBoundary, EvidenceSlice, EvidenceWrite, VersionExpectation, TransactionHandle, CommitBatch, StagingReceipt, CommitReceipt, RollbackReceipt, EventVerification |
| orchestration | TechnicalAction, ActionRequest, ActionPlan, EventAcceptance, EngineCheckpoint, QuiesceRequest, QuiesceReceipt |

ErrorCode 共 19 项：UNSUPPORTED_CAPABILITY、AUTHORIZATION_REQUIRED、STALE_CONTROL_VERSION、IDEMPOTENCY_CONFLICT、NOT_SENT、SEND_OUTCOME_UNKNOWN、UNOBSERVED、EVENT_GAP、UNSUPPORTED_SCHEMA_VERSION、CORRUPT_CAPTURE、INVALID_WIRE、INVALID_FIELD、MISSING_FIELD、TYPE_MISMATCH、NOT_FOUND、VERSION_CONFLICT、TRANSACTION_CLOSED、INVALID_CURSOR、UNTRUSTED_EVENT。

执行 checkpoint 另有 `pmrh.execution-checkpoint/1`；CI 回执另有 `pmrh.devpr02-ci-receipt/1.0`；它们不改变历史科研 schema identity。

### 实现后补充约束

整数限定 signed 64-bit；wire JSON 文本有 8 MiB 解码上限、tuple 有 4096 项上限、原件 slice 有 1 MiB 上限。二进制科研内容只有有界 base64 slice 和原件引用，不出现在普通错误消息里。

可空嵌套 DTO 的版本或缺失成员错误保持具体 code，不被 union 解码吞成 TYPE_MISMATCH。未知版本不自动迁移、null 不自动填字段、未知用量不记零。

STATIC_DECLARATION 不允许把 tool_isolation 标为 TESTED_ON_PLATFORM。接口可以表达真实观察，但 Fake 的 synthetic receipt 永远不证明用户平台的生产能力。

ProviderEventKind.REFUSAL 表达模型拒绝这一观察，不能混同 AUTHORIZATION_REQUIRED。请求模型与实际观察模型分别保存；观测到不同模型不能倒写冻结选择，更不能自动给科学资格。

Fake Provider 即使没有 provider_request_id，也登记原 inference_id 与幂等键的关系。改变 key 不能盲重发同一个 UNKNOWN inference；保留原 UNKNOWN，不凭空补 provider ID。

Fake UoW 的 commit permit 绑定 StagingReceipt，包括完整 transaction、expected boundary 和 batch digest，而不只绑定 batch。旧 permit 不能被换到另一个期望版本的事务。

## 4. 已执行测试与真实 CI

### 4.1 正负例覆盖

86 个 unittest 方法实际覆盖全部 Port 和 60 个 DTO 的正例构造/roundtrip。包含必填/错类型/嵌套不可变、JSON 重复成员/非法版本/任意对象拒绝、三类空值语义、能力逐项协商、逐 inference 硬预算拒绝、缺授权/伪造主体/错误 grant/跨实例/旧 epoch/control/过期 Permit、same-key 去重与 payload 冲突、UNKNOWN 无重发、游标 GAP、cancel 请求与终止分离、SAVED/READ/ADOPTED 分离、raw capture 非数学资格、读无维护写入、CAS 与回滚、原件损坏拒绝、Engine 只消费具体 MAIN 决策、checkpoint 不恢复旧权限或重放派工、AST 依赖与新循环依赖拒绝。

所有 Fake 仅在内存和合成 scratch 中运行；没有调用真实后端。测试名称存在或 Protocol isinstance 通过本身不算验收，完整场景实际调用方法并检查结果/错误/效果计数。

### 4.2 可复现受控入口

```sh
ARTIFACT_DIR="$(mktemp -d /tmp/pmrh-devpr01-artifacts-XXXXXXXX)"
mkdir "$ARTIFACT_DIR/offline"
PMRH_TEST_ARTIFACT_ROOT="$ARTIFACT_DIR" \
  python -B scripts/offline_contracts.py --out "$ARTIFACT_DIR/offline"
```

实际子进程固定为：

```text
python -B -m unittest discover -s tests/devpr02 -p test_*.py -t . -v
```

`pmrh-devpr01-artifacts-*` 名称是继承原隔离输出预检的明确约束，不表示本轮测试属于 DEV-PR-01。原 `offline_test.py` 的 SUITES 仍只允许 devpr01。新入口没有任意 suite/script/project/backend 选择参数。

### 4.3 修复代码提交上的 GitHub 实测

以下均对应 `b2a00be10d45724575d989266b79a9f956dc31ee`；含本文的最终文档 HEAD 需再验证，不能拿旧 Run 冒充新 HEAD。

| Workflow / Run | Job | 已读取的结果 |
|---|---|---|
| [DEV-PR-02 / 38304050871](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38304050871) | [3.11 / 114993653058](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38304050871/job/114993653058) | SUCCESS；86 tests；AST、测试、必须产物验证、上传均成功 |
| 同上 | [3.13 / 114993652741](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38304050871/job/114993652741) | SUCCESS；测试和必须产物 gate 均成功 |
| [DEV-PR-01 / 38304050885](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38304050885) | [114993652758](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38304050885/job/114993652758) | SUCCESS；原 workflow 未修改 |
| [Phase 0 / 38304050928](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38304050928) | [114993653055](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38304050928/job/114993653055) | SUCCESS；原 workflow 未修改 |

新 CI 固定检出 HEAD，日志中的 checkout SHA 为 b2a00be...，tree 为 78b9d0b...。已下载 [3.11 artifact 11771659086](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38304050871/artifacts/11771659086)，检查 ZIP CRC/摘要、实际 86 条单项成功记录、原日志 digest、全部 276 个源码文件与本地测试版本逐字节一致，并从 archive 内容重算 Git tree 匹配远端对象。

该 artifact ZIP SHA-256：`494c1ae9a312a2711354cb61b9defbc6795146fc1eee52238f437eba08410537`。

该 Python 3.11 原始 unittest log SHA-256：`5e3999aa64b57e976785e145d16616be7f56862d5c879354ce1629576432508c`。

这些是开发者的实际回执核对，不等于独立 Review Chat 完成了复验。最终两个 Python artifact、旧回归原日志与实际 checkout tree 必须在最终 HEAD 再次读取。

## 5. 失败记录与修复

| Finding | 等级 | 发现 / 修复与现状 |
|---|---|---|
| DEV02-CAP-01 | MAJOR，已修复 | 初版 STATIC_DECLARATION 能误标 TESTED_ON_PLATFORM；现在要求非静态来源和观察回执 |
| DEV02-WIRE-01 | MAJOR，已修复 | 可空嵌套 DTO 的 UNSUPPORTED_SCHEMA_VERSION 被 union 改为 TYPE_MISMATCH；现在按精确 DTO 分支解码并保留原错误 |
| DEV02-UNKNOWN-01 | MAJOR，已修复 | UNKNOWN 无 provider ID 时改变 key 可再次发送同一 inference；现在独立登记 inference 身份，明确冲突且 Fake send_effects 不增加 |
| DEV02-TX-01 | MAJOR，开发者检查时修复 | 仅绑定 batch 的许可不能保护 expected snapshot；现在许可同时绑定 transaction 与期望边界，新增负例 |
| DEV02-AST-01 | MINOR，已修复 | DTO package eager exports 形成新循环；改轻量 initializer，并新增 AST 无新 Ports 环检查 |
| DEV02-ERROR-01 | MINOR，已修复 | 增加超大整数拒绝、精确 nested missing-field 和 REFUSAL 与权限错误分离的回归 |

首轮失败 Run：[38302328789](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38302328789)，对应初版提交 `254a0cc3a06d68a878638a1191818ca00b889632`。两个 Python Job 都实际运行 81 项，其中 3 项失败；未删除失败测试、未以重跑相同代码掩盖失败。

已下载的初版 3.11 artifact：`11771591649`，ZIP SHA-256 `5d7ea9a179d7ad95acdb6a436b5c442b64a5e08e9226de0b4bf64543a928138a`。原始 traceback 与日志保留。

本地还出现过一次环境失败：平台 `/opt/pyvenv` Python 预加载 `/opt/pyvenv/lib/python3.13/site-packages/sitecustomize.py`，没有加载项目守卫，导致 socket 拦截负例失败。该运行没有被标为 PASS；未修改守卫或删除负例。

用 `/usr/bin/python3.13` 再次核对加载的是项目 `scripts/offline_guard/sitecustomize.py`，实际跑过 86 项全部通过。最终这次本地 raw log SHA-256：`9de54538ed7c0643f5bda5a690dbda7d3e2c7cbbdc020a3be8e2ddc53ed8c3bf`。本地源码标签为 UNCOMMITTED_LOCAL_DEVPR02_FIXUP；之后已与远端 b2a00be 源码逐字节比较一致，未伪装成当时已提交的 HEAD。

## 6. 验收映射与 NOT_EXECUTED

| 验收项 | 本轮已测试部分 | 未完成的产品级部分 |
|---|---|---|
| A01 | Ports 的完整 AST、禁止依赖与无新增 Ports 环、纯标准库导入 | 完整领域抽取、真实部署与所有历史入口解耦 |
| A03 | 统一 invocation/request/execution/attempt、原事件/游标/GAP、capture 合同及 Fake | 真实 Runtime、断线、原始输入窗口与捕获完整性 |
| A04 | MANAGED_AGENT 与 PMRS_MANAGED_LOOP 能力/用量/预算单位分离 | 真实内部 inference、委派、账单与控制权实测 |
| B04 | 不支持逐 inference 硬预算的后端合同明确拒绝 | 真正 native gate、Provider 硬限额及原子预算控制 |
| 附加合同测试 | 版本/不可变/错误/授权边界/幂等/UNKNOWN/事务/读界限/捕获/日志完整性 | 生产认证、授权、fencing、journal/blob 事务与灾难恢复 |

不能把表中契约级 PASS 写成 A01/A03/A04/B04 的完整产品验收。全部 58 项新增与 46 项继承矩阵没有整体执行，继续 NOT_EXECUTED。

## 7. 安全与已知限制

工具只用于 GitHub 基线/代码对象/分支/PR/Actions 的读取写入，以及本地源码、合成测试和证据文件操作。GitHub 写入只限本开发分支和 PR；没有改原仓库、历史 refs、main 或真实科研内容。

本地测试使用清理后的 HOME/XDG/TMP scratch 与隔离 artifact 目录，不以真实 HOME 保存测试产物。运行 AST 是静态读取源文件，不通过 import 执行旧研究服务。没有 pip 联网安装、Codex/API 凭据获取、生产 Provider 调用或真实研究任务。

实际模型调用遥测：count=null / NOT_INSTRUMENTED，observed_provider_events=NOT_MEASURED，zero_calls_verified=false。Fake send_effects 只表示 Fake 的模拟副作用，不冒充测得真实模型调用次数。GitHub CI checkout/setup/upload 的基础设施网络与测试子进程隔离分开；没有基础设施网络总量遥测。

**尚未解决但不属于本轮生产实现的边界：** Python guard 不是 OS 沙箱；已有硬链接别名、恶意 native/反射/继承 FD、宿主 sitecustomize 覆盖均不属于已证明隔离。Permit/Manifest/TrustOrigin DTO 本身无授权能力；Fake context 不是生产认证，Fake UoW 不是持久化原子事务，Fake grant 检查不是累计预算/全局资源池事务。真实并发、fencing、崩溃恢复及用户平台后端能力均 NOT_EXECUTED。

CI 原日志有 action Node 运行时弃用警告（MINOR 维护提示）；当前 Job 实际成功，不在本工作包擅自升级所有继承 workflow。暂未发现仍未修复的本轮 MAJOR/BLOCKER 合同缺陷；这一开发者判断须接受独立审核，不能推导软件绝无缺陷。

DEV-PR-03/04/05/06/07 分别继承只读、领域、存储、控制、Runtime 合同；没有在本轮启动这些工作包。独立审查和 MAIN 验收仍未执行。

## 8. 回滚与交接

合并前：关闭 PR 可放弃未接入旧系统的新增端口，不需要回滚科研状态。不得擅自删除他人的分支。

合并后：必须通过独立的软件 revert PR 撤销，不重写历史，不删除原始科研 capture，不恢复 MAIN/Goal 或改变预算/科学结论。

包含本记录的最终 HEAD 经源码、PR 文件范围、三个 workflow、四个 Job 和原始产物复核成功后，开发者在 PR 描述中标记 READY_FOR_INDEPENDENT_REVIEW，并保持 PR Open。该标记只表示可交给独立 MAIN 审核，不是 APPROVE、ACCEPTED 或合并授权。
