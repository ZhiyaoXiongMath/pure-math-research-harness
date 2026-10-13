# PMRH DEV-PR-02 — 独立定向复验 R3

**审核日期：**2026-10-13（Asia/Tokyo）  
**报告生成：**2026-10-13T18:25:43+09:00  
**审核角色：**原 Independent Review Chat；GitHub 只读＋隔离合成复验  
**交回：**PMRH Development — MAIN | DEV-PR-02  
**最终建议：**`APPROVE_FOR_MAIN_ACCEPTANCE`

> **六项 Finding 尚非全部关闭：四项 MAJOR 和 REV02-DOC-01 已关闭；REV02-HELPER-01 的新版实现复核为 INCONCLUSIVE，普通／`-O` 独立执行为 NOT_EXECUTED。**
>
> 本轮代码契约及关键 GitHub 证据充分，没有仍未关闭的 BLOCKER／MAJOR。对外部 helper 继续采用上一轮 H.6 已明确的“非阻断 MINOR、不得作为单一权威 gate”处置，不把开发者 28/28 当作独立通过。建议 MAIN 将此限制及补交责任单独留账；本报告没有替 MAIN 接受风险，也不是 MAIN ACCEPTED 或 GitHub 合并。

## 1. 冻结身份与证据来源

### 1.1 实时 GitHub 身份

| 项目 | 独立复核结果 |
|---|---|
| 仓库／PR | [pure-math-research-harness / PR #4](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/4) |
| 分支 | `feat/dev-pr-02-ports-dto-contracts` |
| Base／最后回读 main | `efd2be4e93ca8f1ee9f6a03fa53df6a1f008c8fb` |
| 上一审核 HEAD | `dd044d09acaae7ddc250e9f96cd0ba4e940bf467` |
| **本轮审核 HEAD** | **`bdc698873999d3fc1773e76588339276ddc581ca`** |
| 唯一父提交 | `dd044d09acaae7ddc250e9f96cd0ba4e940bf467` |
| **本轮 Git tree** | **`9dc07cf45cb02ba31e047f266380be85717a64f2`** |
| 新增提交 | 1；`fix(dev-pr-02): remediate independent review findings` |
| 提交时间 | 2026-10-13T08:12:25Z，即日本时间 17:12:25 |
| PR 状态 | Open／非 Draft／merged=false／mergeable=true |
| 旧→新差异 | 恰好 11 路径，8 修改＋3 新增，830 插入／34 删除 |

已通过 GitHub Connector 重新读 PR metadata、main ref、开发分支 ref、Git commit、commit diff／compare、Actions、Job／Step 和原始日志。结束前再读 main、开发分支与 PR，身份没有变化。直接对象依据：[新 commit](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/commit/bdc698873999d3fc1773e76588339276ddc581ca)、[旧→新 compare](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/compare/dd044d09acaae7ddc250e9f96cd0ba4e940bf467...bdc698873999d3fc1773e76588339276ddc581ca)；机器索引见 `results/live-github-observations.json`，该索引是审核者对真实读取的转录，**不是**假装原始 API 响应。

两份重新下载的 DEV-PR-02 Artifact 各含 280 文件的 `source.tar.gz`。审核者按原路径、文件模式和内容独立重建 Git blob／tree 哈希，均得到上表 tree；旧快照重算得到 `82d02d5b4adce11429df748b211fd72f9f42be28`。因此本地读取／测试的字节绑定真实 GitHub commit，不是只相信 receipt 的 `source_sha`。没有将源码快照称为完整 Git clone 或历史迁移。

### 1.2 四类证据不混同

| 类别 | 本轮用途 |
|---|---|
| GitHub 原始记录 | 实时 ref／commit／PR／run／job／step；重新下载 Artifact ZIP；核实远端来源与实际运行 |
| 审核者独立计算与执行 | ZIP CRC／SHA、全 Git tree、源码差异、方法 AST 比较、完整测试 ID 比较、反例与新边界测试 |
| 开发者提交的副本 | 当前 Local-Git-CI ZIP、Job 日志副本、本地 helper 28 项记录、开发者适配探针结果 |
| 开发者解释 | 本机正常 Git push、bubblewrap 配置、此前平台写入阻塞、helper 已修复的陈述 |

后两类不因存有 manifest 或 PASS 字样就升级为独立结论。GitHub 基础设施联网与测试子进程的模型调用是不同问题；本轮没有真实模型计量，维持 `count=null / NOT_INSTRUMENTED / NOT_MEASURED`。

## 2. 变更范围与源码审阅覆盖

本轮沿用上一轮针对旧 HEAD 的完整审阅，只重新审查 **全部 11 个差异文件、其实际 diff 与必要相邻合同**，没有重复从零审计全部 36 个 PR 路径。

| 路径 | 实际差异 | 本轮审阅深度 |
|---|---:|---|
| [docs/development/DEV-PR-02-DELIVERY.md](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/docs/development/DEV-PR-02-DELIVERY.md) | +8/−1 | 全部差异、历史本地日志 SHA 对应段与修订注释 |
| [docs/development/DEV-PR-02-REMEDIATION.md](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/docs/development/DEV-PR-02-REMEDIATION.md) | +144 | 全文；区分修复说明、开发者复跑、推送前 BLOCKED 历史 |
| [pmrh/ports/dto/core.py](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/pmrh/ports/dto/core.py) | +6 | 全部差异与 ErrorEnvelope／port_error 完整关联逻辑 |
| [pmrh/ports/dto/events.py](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/pmrh/ports/dto/events.py) | +6 | 全部差异、共同页不变量、三类 page 与单事件身份约束 |
| [pmrh/ports/dto/wire.py](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/pmrh/ports/dto/wire.py) | +91/−12 | 完整 304 行；类型检查、预算、内部 decoder、公开入口及异常路径 |
| [scripts/offline_contracts.py](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/scripts/offline_contracts.py) | +12/−3 | 完整 118 行；启动前预检、固定子命令、异常／receipt／写入逻辑 |
| [scripts/verify_devpr02_artifacts.py](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/scripts/verify_devpr02_artifacts.py) | +93/−7 | 完整 209 行；可信源码清单、原始日志、原有摘要与失败门槛 |
| [tests/devpr02/fake_runtime.py](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/tests/devpr02/fake_runtime.py) | +21/−10 | 全部差异与 Provider 路径；Runner events 返回路径及相邻幂等逻辑 |
| [tests/devpr02/test_ci_contracts.py](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/tests/devpr02/test_ci_contracts.py) | +3/−1 | 全部差异；setUp 正夹具及原测试断言没有弱化 |
| [tests/devpr02/test_remediation_artifacts.py](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/tests/devpr02/test_remediation_artifacts.py) | +153 | 全文、13 个测试及合成源码／日志夹具 |
| [tests/devpr02/test_remediation_contracts.py](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/tests/devpr02/test_remediation_contracts.py) | +293 | 全文、7 Wire＋6 Event＋7 UNKNOWN 测试及夹具 |

完整 diff 见 `independent-delta.diff`；每个修改文件的 Git blob、SHA-256 及行数见 `delta.json`。完整 source tree 重算为逐文件身份提供共同认证；并非声称每个文件都分别进行了一次 HTTP blob 下载。

**回归保护：**独立比较旧 86 个 test 方法的 AST，全部仍在且方法体不变。当前源码共 119 个方法，新增 33；`test_ci_contracts.py` 的变化只为合成 artifact 正夹具写入真实可解析的测试类及匹配 ID。不存在删除原失败用例或删断言获得绿灯的情况。

`research_studio/` tree 仍为 `f49a0b4e51d9a9602f82d7dc9fdf33a3e563b7da`。旧 guard、AST 扫描器、架构例外、全部 workflow、Port 接口签名及 legacy schema 均不在差异中。主干仍是同一治理基线，沿用有效 ADR-0001／0002 及 MAIN 协议；PROJECT-STATE 的历史未授权快照不替代本消息的明确复验授权。

## 3. 四项 MAJOR 的逐项独立关闭

### 3.1 REV02-WIRE-01 — CLOSED

**修复位置：**[pmrh/ports/dto/wire.py](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/pmrh/ports/dto/wire.py#L132-L219) 的 `_wire_budget`／`_decode_dto`；[pmrh/ports/dto/wire.py](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/pmrh/ports/dto/wire.py#L261-L304) 的公开入口；嵌套 `_typed` 对 DTO 使用内部 decoder 的差异。

统一预算为 canonical UTF-8 JSON **8,388,608 bytes**、深度 64、节点 262,144；tuple 原上限 4096 不变，单 evidence slice 原上限 1 MiB 不变。`to_wire` 在返回传输对象前检查整个聚合；`to_json`、`wire_digest` 继承同一检查；`from_wire` 与 registry decoder 同样先做全局预算。嵌套 DTO 不再重开一个独立聚合预算。共享对象按出现次数累计，不按 Python 对象身份去重。

输入 JSON 文本另有包括空白／转义在内的原始文本 8 MiB 上限。因此“canonical 内容恰好 8 MiB 再追加空白”仍被文本入口拒绝，这是明确的传输文本限制，**不是**原先“本 codec 成功编码却无法读回”的矛盾。合法小对象带普通空白可正常读取。

**原反例重放：**七个各自合法 1 MiB slice、相同 operation/key，独立构造的 wire 仍为 **9,789,080 bytes**。旧源上原反例仍失败；新源的对象／registry／JSON 解码全部以 `INVALID_FIELD` 拒绝，三种公开编码（wire、JSON、digest）也拒绝。

**独立新增实证：**精确 8 MiB 对象在三个解码入口均等于原 DTO，digest 等于独立 SHA-256；多一字节在六个编码／解码入口全部拒绝。Unicode 与 JSON 转义按真实 UTF-8 计数；深度、循环对象、共享子列表导致的总节点超限均明确拒绝。这里检查的是当前显式资源边界，不主张完成通用恶意 native 内存隔离证明。

证据：`results/reviewer-adapted-on-new/independent-results.json` 中 WIRE-19/20/21/22；`results/reviewer-targeted-on-new/targeted-results.json` 中 **27 项 R3-WIRE** 全部 PASS；原始 stderr／stdout 一并保留。原版本／Optional 嵌套错误码、signed64、不可变、60 DTO roundtrip 检查同时通过。**该 MAJOR 已关闭。**

### 3.2 REV02-EVENT-01 — CLOSED

**修复位置：**[pmrh/ports/dto/events.py](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/pmrh/ports/dto/events.py#L155-L190)，共同 `_page_invariants` 第 181–186 行：Runner 逐项要求 `envelope.invocation_id == cursor.stream_id`；Provider 逐项要求 `inference_id == cursor.stream_id`。原 scope、序列、末尾 cursor、EMPTY／GAP 语义未放宽。

独立构造三个事件的合法页，保持同一 scope、连续序列、原件引用及 last_event_id 正确，仅替换中间一个或全部事件的 stream 身份。Runner／Provider 两种页分别在 **构造、from_wire、from_json、decode_wire** 四入口拒绝；正确三事件页均可往返。

另实际启动合成 FakeRunner 后读取正确页，再仅污染其内存事件夹具，验证 `events()` 返回路径不能生成错误流页，send_effects 保持 1。FakeProvider 真实合成 `stream()` 返回的事件用于组装 ProviderEventPage，身份和 roundtrip 正确。不是凭测试名猜测返回路径。

证据：原 EVENT-RUNNER／PROVIDER-cross-stream 现在 PASS；新增 **20 项 R3-EVENT** 全部 PASS。相邻的显式 EventGap 不推进 cursor、伪造 COMMITTED 仍须通过 EventRepository 校验等原探针通过。**该 MAJOR 已关闭。**

### 3.3 REV02-UNKNOWN-01 — CLOSED

**修复位置：**[tests/devpr02/fake_runtime.py](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/tests/devpr02/fake_runtime.py#L223-L303) 的 `validate_request/stream/inspect/cancel`；[pmrh/ports/dto/core.py](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/pmrh/ports/dto/core.py#L156-L201) 的 `ErrorEnvelope` 不变量。

有冻结 spec 的 Provider 错误绑定 `operation_id=spec.inference_id` 和原 parent `InvocationIdentity`。STREAM 上游授权／能力拒绝保留原 code、evidence 与恢复约束，规范化到当前具体 inference。Known STREAM／VALIDATE_REQUEST 错误不允许 operation_id 缺失。没有新增远端 request ID，也没有把本地 inference ID 声称为 provider request ID。

独立复现同 parent 下两次不同 inference 的 UNKNOWN：返回 operation ID 各自匹配，整个错误不再相等；Fake send_effects=2，远端 ID 登记数=0。相同 inference 改 key 仍返回幂等冲突且 send_effects=1；相同 key 改成不同 inference，冲突错误标明被拒绝的 inference。原相同请求缓存回执、防重发路径及恢复安全枚举没有回退。

新增六种场景分别检验 NOT_SENT、UNKNOWN、缺 permit、stale control、跨 key、同 key 不同 inference。都保持正确本地 identity 和 JSON roundtrip。NOT_SENT 的效果数为 0；UNKNOWN 为 1；授权拒绝为 0；冲突不增加额外效果。**Fake 计数只是模拟效果，不是真实模型计量。**

证据：原 UNKNOWN-01/02 及新增 **6 项 R3-UNKNOWN** 全部 PASS；119 项套件同时覆盖同请求重复返回、缺失 operation_id wire 拒绝、能力／模型拒绝等。**该 MAJOR 已关闭。**

### 3.4 REV02-CI-01 — CLOSED

**修复位置：**[scripts/verify_devpr02_artifacts.py](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/scripts/verify_devpr02_artifacts.py#L31-L116) 的 `expected_test_ids/validate_test_log`；`validate` 第 118–189 行保留源／摘要门槛；[scripts/offline_contracts.py](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/scripts/offline_contracts.py#L43-L106) 将同类身份校验接入测试入口。

可信清单由**已认证的冻结源码**静态解析，不从 receipt 的可改写计数推导。当前批准形状为顶层、无装饰器、直接 `unittest.TestCase` 的普通直接 test 方法；不支持的继承／动态收集／重复定义／身份 override 等显式拒绝。该策略不是任意 Python 的完整动态证明，调用方仍须先认证 source_root。

本次 source_root 已通过独立 Git tree 重算认证；真实 CI 在固定 HEAD checkout、legacy gate 和工作树不变检查后调用验证器。在“只篡改日志及 receipt”的原威胁模型中，攻击者不能同时改掉冻结源码而仍算同一审核版本。独立另写 AST 清单提取代码，确认两份远端原日志均含与源码完全相同的 119 个唯一 ID；不是仅引用新 verifier 自己返回的 ID。

| 必须重放的攻击 | 如何避免由普通摘要差异提前拒绝 | 实际新结果 |
|---|---|---|
| 成功摘要后追加 `FAILED (errors=1)` | 同步更新 raw_log_sha256 | 拒绝：final success footer absent or contradicted |
| 仅保留一个真实测试，计数改 1 | 同步改计数、摘要；补充攻击再同步改 expected／validated ID 数组 | 拒绝：IDs differ from complete frozen source suite |
| 将同一个真实 ID 重复 **119 次** | 保持总计数 119，同步改摘要；补充攻击也改 receipt ID 数组 | 拒绝：Duplicate test identities |
| 失败之后再补一个伪造 OK 尾部 | 同步改摘要 | 拒绝：Unexpected terminal material |

正常 Python 3.11／3.13 真实 Artifact 均继续 PASS；不存在为了拒绝旧 86 项而故意使用 119 与 86 的简单数量差。旧源码＋旧 Artifact＋旧验证器的原三攻击依然实际错误 PASS，红／绿对照明确。

在独立 scratch 中新增一个合法 source-defined 测试后，清单变为 **120**：旧 119 项日志被拒绝；加入对应完整记录并改正确 120 尾部后被接受。证明未硬编码 86／119。所有实验只改 scratch，不改仓库。开发者新增 13 项 artifact 测试亦实际通过，原五项 artifact gate 测试断言未弱化。

证据：原 ARTIFACT 三攻击现在 PASS；新增 **6 项 R3-CI** 全部 PASS；`results/ci-crosscheck/summary.json` 保存独立 ID 匹配及真实三份 Artifact 的验证器正对照。**该 MAJOR 已关闭。**

## 4. 两项 MINOR：一项关闭，一项复核材料不足

### 4.1 REV02-DOC-01 — CLOSED

新 [docs/development/DEV-PR-02-DELIVERY.md](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/blob/bdc698873999d3fc1773e76588339276ddc581ca/docs/development/DEV-PR-02-DELIVERY.md#L179-L183) 已把抄录值改为：

```text
a4abd794597343acdbd5671ae540cd5fed3e9dc93abbac0b1a376beab224febd
```

审核者重新读取原交接 ZIP 内 `evidence/local-system-86-pass/unittest.log` 及对应 `receipt.json`，独立 SHA-256 恰为该值；原日志字节未为适配新文档而改写。当前 diff 只有文档勘误及历史说明，没有重写日志。原件副本在 `results/historical-local-unittest.log`、`results/historical-receipt.json`；原件来源／长度见 `results/integrity-r3.json`。

原错误 `9de54538...` 是人工文档笔误；本轮已在真实新 HEAD 纠正，**不再只是开发者外部勘误**。该 MINOR 已关闭。

### 4.2 REV02-HELPER-01 — INCONCLUSIVE；独立执行 NOT_EXECUTED

当前实际提供的 `PMRH-DEV-PR-02-R2-Local-Git-CI-Evidence-2026-10-13.zip` 含 158 文件。审核者核对了全部成员和 157 个内部摘要，并搜索当前可用材料；未找到新版：

```text
audit-helpers/verify_devpr02_downloads.py
audit-helpers/verify_devpr02_final.py
```

包中存在 `helper_regressions_local.py`、28 项 results 以及对应 stdout／stderr。这一 `.py` 是**调用 helper 的监督测试脚本**，其实际输入依赖 `/workspace/audit-helpers`；不是两个被审核 helper 的实现。另有本地路径／原包摘要说明，但没有把该原包字节一并交进来。源码缺失时不能独立检查是否确已移除 assert、是否 `-O` fail-closed、是否拒绝坏 ZIP 或缺文件。

开发者记录 `28/28` 已读，但保持为开发者证据；**本审核没有执行这 28 项，也没有伪造新的 helper 替换原工具再宣布原 Finding 关闭。**旧 helper 不冒充新版，当前编写的 reviewer 辅助脚本也不替代此缺口。

上一轮完整报告 H.6 已明确该问题“**不单独阻止 MAIN**”，接受条件为不把 helper 作为单一权威 gate、使用独立认证原件与对象，并登记修复责任。本次三份关键远端 Artifact、源码 tree、计数及原反例均已有不依赖 helper 的独立核验，故继续按这一原严重度处置，而不新增软件 MAJOR 或强行要求改 PR。

**最小闭环材料：**原交付者补交那两份 handoff/2 helper 及必要支持文件／manifest，或原 `PMRH-DEV-PR-02-Remediation-R2-Handoff-2026-10-13.zip`（开发交付引用摘要 `4e2cf53ac4519f8a9d49860fd46ef14d2c89de6cd3ce4c0b6c8edbe08000f247`）。然后只对这两个工具做正常／`-O`、错误摘要、坏 ZIP、缺文件与相关反例的定向复验。**无需改当前 PR 的 Ports 接口，也无需重新审核全部 36 文件。**MAIN 负责留账，原 Development／本地交付者负责补材料，Reviewer 负责后续工具定向核查。

## 5. 审核者独立执行记录与原脚本适配

### 5.1 真实结果表

| 执行／核查 | 本轮实际结果 | 分类 |
|---|---:|---|
| 原始 probe 原字节＋旧冻结源码／旧 Artifact | **59：50 PASS、9 FAIL、0 HARNESS_ERROR** | 旧缺陷红对照；不是当前失败 |
| 原始 probe 原字节＋新冻结源码 | 前 **18 项 PASS**；随后在包装外 `big.to_json()` 抛 ContractViolation，exit 1 | 编码修复触发的预期中止；后 41 项未执行，不能写 59/59 |
| 审核者适配原 probe＋新源码／新 Artifact | **59/59 PASS，0 HARNESS_ERROR** | 独立复验；保留原语义及输入 |
| 审核者新编补充边界脚本 | **59/59 PASS，0 HARNESS_ERROR** | 27 Wire＋20 Event＋6 UNKNOWN＋6 CI；含与原行为重叠的路径，不声称全为全新需求 |
| 本地原 DEV-PR-02 套件 | **119/119 PASS** | 对真实冻结快照的复跑 |
| 本地原 DEV-PR-01 | **48/48 PASS** | 有限继承回归 |
| 本地原 Phase 0 | **6/6 PASS** | 有限 smoke／静态回归 |
| 本地完整 AST | **PASS** | 与远端 counts、源指纹、直接／传递图、SCC 等逐项一致 |
| 新版外部 helper 普通／`-O` | **NOT_EXECUTED** | 实现字节未提供，不采用开发者 28/28 代替 |
| 开发者 adapted-probe 源码及 diff 比较 | **NOT_EXECUTED** | 当前包只有结果／监督记录，缺 adapted 脚本和 diff |

所有原始输出与执行回执见 `results/`。首次原样运行新源码的非零退出完整保留；没有改称“原脚本直接全绿”，也没有删掉错误栈。当前源码上的两个独立脚本以及三个原套件没有软件失败或 HARNESS_ERROR。

### 5.2 审核者适配范围

原始 probe SHA-256：`55ad9f3e1d95ffc153c0b32d5bc18bb0254174fc744b2c2e2fd715ff2a3aa97a`。

只调整：（i）新 HEAD／tree 和匹配的 119 项 Artifact 夹具；（ii）在测试包装外，改由独立 JSON 组装生成**原样 9,789,080 字节对抗输入**，不调用应拒绝的聚合编码；（iii）WIRE-22 的实际判据兑现其原文字“编码拒绝或成功读回均可”，不把应有编码拒绝当脚本错误；（iv）重复 ID 攻击次数与正对照计数由旧 86 更新为当前 119。

审核者适配 SHA-256：`d362d4d4a52c07da2c5845459a93993953ac7c5218c95f1709d163676b36fa91`。完整逐行差异：`results/reviewer-adapted-probe.diff`；变更说明：`results/probe-adaptation.json`。没有改动被测产品代码或删除不利断言。

开发者 adapted-probe 的实现／diff 不在本次提供包中，不能声称已核对它。其 59/59 不作为上述独立结果的来源；用保留的原始 reviewer probe 自行重做包装已经完成四项 MAJOR 的判别性验证。因此这一缺口不让代码修复重新变成未知，但它仍限制开发者交接的完整可复现性。

### 5.3 安全执行环境

本地为 `Linux-6.18.44-x86_64-with-glibc2.41`，`/usr/bin/python3.13` 为 **3.13.5**；不是开发者的 Ubuntu 26.04.1／Python 3.14.4。没有把开发者 bubblewrap 声明当成本审核运行环境。

独立 probe 子进程使用新的 `/tmp/pmrh-r3-independent-*`，隔离 HOME／XDG／TMP，环境变量白名单，不继承模型／代理凭据，启用原样 `scripts/offline_guard/sitecustomize.py`。运行前验证实际加载路径与 socket 拒绝，随后进行 guard 源码写入／硬链接／私有路径的合成负例。监督进程设定 CPU／地址空间／输出文件预算和超时；只复制软件与合成证据。源码运行前后摘要一致。

三个原套件遵守各自已审核入口：DEV02／DEV01 复用受控 launcher；Phase0 用隔离 HOME/XDG/TMP 的原六项 smoke，允许其已审阅的惰性 CLI 子进程。未运行旧 `research-studio`、完整历史 runner、模型、科研项目或原生产品服务。**Python 级 guard 不是 OS 沙箱**；本轮没有声称完成恶意 native／反射／继承 FD 的对抗隔离验收。

本地是独立认证的源码快照，非 Git checkout。传给 receipt 的 PMRH_CHECKOUT_SHA／TREE 是与独立 tree 重算一致的快照标签；真实 Git checkout 证据来自远端 Job，不冒充本地 `git rev-parse`。

## 6. GitHub Actions、Artifacts 与交付完整性

### 6.1 真实新 HEAD CI

| Workflow／Run | Job | 实际 Python／测试 | 状态与源码 |
|---|---|---|---|
| [DEV02 38367753519](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753519) | [115196874290](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753519/job/115196874290) | 3.11.17；119/119 | completed/success；精确 checkout 新 HEAD |
| 同一 DEV02 Run | [115196874368](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753519/job/115196874368) | 3.13.16；119/119 | completed/success；精确 checkout 新 HEAD |
| [DEV01 38367753326](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753326) | [115196873632](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753326/job/115196873632) | 3.12.3；48/48 | completed/success；PR 测试合并引用 |
| [Phase0 38367753356](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753356) | [115196873741](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753356/job/115196873741) | 原六项；6/6 | completed/success；PR 测试合并引用 |

三个 Run 的 head_sha 均对应 `bdc698873999d3fc1773e76588339276ddc581ca`。四个 Job 的关键 Step 已直接重新读取：checkout、源／legacy 校验、相应 AST／合成套件、必须产物 gate 和 upload（该 workflow 存在时）均成功。原始日志证实实际检出、测试 receipt、出口状态和 artifact upload digest。119 是独立方法数，在两 Python 环境分别执行，不写成 238 个不同方法。

继承 workflow 的实际检出为 [测试合并 commit e8588ba…](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/commit/e8588ba4927c5eaf446e70f711febf8bb6673496)，已直接读取 Git commit 对象：父提交为 base 与新 HEAD，tree 仍为 `9dc07cf45cb02ba31e047f266380be85717a64f2`。这是 GitHub 的 PR 测试引用，**不是** PR 已合并至 main；也不声称存在另一次 post-merge main CI。

GitHub CI 时间为 **2026-10-13 08:13 UTC／17:13 JST**。仓库保留的 R2 BLOCKED 文档是推送前历史；最新 PR 描述已明确这一点。其历史文字不与当前真实提交／CI 混算，不为纠正历史措辞要求额外提交。

### 6.2 本轮重新下载的原始 Artifact

| Artifact ID | ZIP 字节数 | 独立 SHA-256 |
|---|---:|---|
| [11797304019／py3.11](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753519/artifacts/11797304019) | 1,944,331 | `e9146b5835fcb70047ca991df80fb45f271c571d8b7cbbbbecb3b402e2642479` |
| [11796649547／py3.13](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753519/artifacts/11796649547) | 1,944,329 | `8ec21e5afcfb582d3cfc1820a2563e71d81f42efa6093587f3612087894bb9d8` |
| [11796719438／DEV01](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38367753326/artifacts/11796719438) | 70,189 | `350d1182c0993426e3099e43d326b31d64139c825f2ab19fe4c38e74720d33b5` |

三份均从本次 Connector 下载取得，CRC 通过，与远端 API digest、upload 日志及用户 ZIP 中相应副本一致。两个 DEV02 包各有 6 文件，DEV01 有 4 文件。Phase0 的真实 artifacts 列表为空，原 workflow 本来就不上传 Artifact；本轮使用真实 Job 日志，不伪造第四个 ZIP。

原始 unittest 日志摘要：

```text
py3.11  9ddf2143b1b218f7fb2369ab1d8eac592d9b42745f4d02cb700228e9296e2881
py3.13  eb3b163027d5bc391e7038bdd963670b80a1570811b17ec5acf8a6e3dcd05adb
DEV01   22d7e672bb5b630f9d645f5728f3387652d8b8e5f4e439a2c4a772d28f9ad9be
```

独立核对完整唯一 test IDs 为119／119／48，均与各自冻结源码方法集一致。DEV01 的三项负例诊断跨行，按完整测试记录核查为48，不把单行正则得到的45误报为缺测。所有原始结果字节保留。

两 DEV02 产物 source.tar.gz 全 280 文件逐字节一致；36 个 contract 指纹与 receipt 一致；176 个 Python 源指纹与 AST 一致。完整直接／传递图与本地重新扫描逐项一致。三个正常远端 Artifact 再调用其相应已审阅 verifier 全部 exit0，这只是额外正对照，不是独立判据的替代。

### 6.3 当前用户交付 ZIP 的实际覆盖

当前 `PMRH-DEV-PR-02-R2-Local-Git-CI-Evidence-2026-10-13.zip`：8,318,776 bytes；本轮独立 SHA-256：

```text
076f8e2b16e36794ac06a36f8993a35d5804f2f96bc3c7a12086cc9d5b35cfc6
```

158 个成员，CRC 正常；没有重复名称、路径穿越、绝对路径或链接成员。`EVIDENCE-SHA256SUMS.txt` 覆盖其余157文件，全部逐项匹配。`input-R2.patch` 独立摘要为 `491d7c523cfcbad086abb4d886c993103c27b388d8719074b934657814861144`，与其声明一致；真实 source diff／tree 已另行核实。

报告中引用的 `4e2cf53...` 指**另一个原 R2 Remediation-Handoff ZIP**，并非当前 Local-Git-CI ZIP。原包的163成员／162摘要是开发者对另一包的记录，不能套用到当前158成员；也不能把两个不同文件的摘要不同误判为损坏。

当前包完整性通过不意味着被它引用但未包含的 helper／adapted 脚本也已交付。这是 §4.2 的具体证据缺口，不影响已独立下载并认证的三份关键远端 Artifact。

## 7. 回归判断与新风险

**未发现新的 BLOCKER／MAJOR，原四项的修复没有可复现的回退。**当前拒绝发生得更早：超限 DTO 编码时失败、错误 stream 构造时失败、有 parent 的 inference 错误不允许丢失 operation_id。这些是本次要求的合同强化，不是应为兼容旧漏洞而放宽的行为。

原八类 Ports／十维能力分离未改；托管汇总计量不能满足逐 inference 硬预算；permit 仍须与可信 FakePolicyGateway 登记匹配；旧 epoch／control version、UoW 期望版本／permit 事务重定向仍被拒绝；UNKNOWN 换 key 不重发；COMMITTED 标签不能取代真实 Fake repository 校验。这些相邻回归由原套件与独立原 probe 实际复跑支持，而非重做所有后续运行时测试。

CI 清单抽取只支持已声明的静态 unittest 形状；将来引入参数化装饰器、继承型 suite 或动态测试，必须先更新清单契约与反例，不能静默缩减。验证器依赖调用方认证 source_root；不能把任意本机可写目录加任意伪造日志称为某个 GitHub HEAD。新 CI 的 checkout／工作树检查和本轮 tree 重算满足当前前提。

Node action 弃用告警沿用原 workflow，真实 Job 仍成功。本次无 workflow 变更，不据该维护提示增加本轮阻断项。新 helper 的实现未知保留原 MINOR，不能归纳成“已经证明新版 helper 仍有漏洞”，也不能写已修好。

## 8. G1–G8 与原验收矩阵的范围化状态

### 8.1 八个审核门

| Gate | R3 结论 | 支持范围／剩余边界 |
|---|---|---|
| G1 依赖方向与隔离 | PASS，合同级定向复核 | 新完整 AST：176 Python、1194 直接边、6463 传递边；0 新违规／解析失败／新层未解析；唯一 SCC 属 legacy；旧 guard／例外不变 |
| G2 DTO／Schema／Wire | PASS，REV02-WIRE-01 CLOSED | 60 DTO 原往返、schema／strict type 回归；统一聚合／字节／深度／节点边界实测 |
| G3 Ports／能力协商 | PASS，合同级 | 接口签名与能力策略不变；Provider 错误关联修复闭环；不等于生产适配器验收 |
| G4 授权／幂等／UNKNOWN | PASS，REV02-UNKNOWN-01 CLOSED | inference身份、NOT_SENT区别、跨key防重发、permit／CAS相邻负例通过 |
| G5 Event／Evidence／四轴 | PASS，REV02-EVENT-01 CLOSED | 正确／错误／混合stream与Fake返回路径；GAP、原件和科学状态区分保持 |
| G6 Fakes／测试入口／CI安全 | PASS，REV02-CI-01 CLOSED | 119原套件、两组独立probe；出口状态与唯一完整ID；原Python guard有限保证保持 |
| G7 GitHub CI／Artifacts | PASS | 三Run／四Job；新HEAD或同tree测试合并引用；三份ZIP重新下载核字节；Phase0实际原日志 |
| G8 历史／开发报告／交接一致性 | PARTIAL，非阻断MINOR留账 | DOC-01 CLOSED；源／核心Artifacts／历史对照充分；HELPER-01 INCONCLUSIVE、缺适配脚本diff；不冒充全部交接工具已复验 |

G8 不粉饰为无条件全绿；但其剩余项不是尚未关闭的 MAJOR，也不是当前源／CI 身份缺失。接受非阻断 MINOR 的最终管理决定仍由 MAIN 单独记录。

### 8.2 A01／A03／A04／B04

| ID | DEV-PR-02 范围内 | 不能据此授予的产品 PASS |
|---|---|---|
| A01 | IMPLEMENTED／TESTED／REVIEWED：Ports依赖方向、标准库DTO、无新层环 | 完整领域内核抽取、真实部署隔离 |
| A03 | IMPLEMENTED／TESTED／REVIEWED：调用／事件／游标／capture合同；本轮跨stream与inference错误身份关闭 | 真实Runtime输入窗口、断线、恢复、capture端到端 |
| A04 | IMPLEMENTED／TESTED／REVIEWED：两执行模式、能力、用量覆盖与预算单位分离 | 托管内部inference／委派／账单控制实测 |
| B04 | IMPLEMENTED／TESTED／REVIEWED：不支持逐inference硬预算时明确拒绝 | 真实native root gate、Provider限额、累计／原子预算 |

本轮这些标记只针对合同部分。`MAIN ACCEPTED` 未由本 Chat 发出；`GITHUB MERGED=false`；未执行部分为 `NOT_EXECUTED`。不能把 119 个软件 Fake 测试变成完整58＋46矩阵或数学证明验收。

## 9. NOT_EXECUTED 与建议 MAIN 接受的剩余风险

**未执行：**真实生产认证／fencing／撤销竞态、累计及原子预算、journal/blob持久化与崩溃恢复／迁移、真实Codex／Provider、数学研究／正式项目、模型和账单遥测、恶意进程OS隔离、完整legacy产品套件及58＋46未来矩阵。本轮没有本地Python3.11／3.13.16矩阵重跑，相关版本结果来自真实GitHub CI；本地实际版本为3.13.5。

**本轮材料特有的未执行：**新版helper实现审阅及普通／`-O`反例；开发者adapted源码／diff比较。上述缺口的原因是字节未提供，不是工具测试失败，也不作PASS。

建议MAIN按原H.6记录一个外部交接工具MINOR：这些helper暂不作为权威验收入口；使用已认证GitHub对象／远端Artifact及本次独立结果；保留原交付者补交责任。没有据此要求提前做生产Provider／Store，也没有对已关闭四项MAJOR追加无证据的重构范围。

## 10. 最终结论与 MAIN 交接

# `APPROVE_FOR_MAIN_ACCEPTANCE`

本轮对新冻结HEAD的11文件完成定向审阅，重新认证真实CI和三份Artifact，并亲自重放原失败反例与必要新边界；四项MAJOR全部关闭，DOC-01关闭，未发现新的重大阻断项。

**六项并未全部关闭：HELPER-01保持INCONCLUSIVE／NOT_EXECUTED，按上一轮已登记的非阻断MINOR处理，不计入通过。**这不影响源／CI已经独立认证的结论；MAIN应明确留账其不作为权威gate及补交责任，而不是把它写成“28项独立复验通过”。若要把该条也关闭，最小动作只是补齐两个外部helper及必要支持材料后做工具级定向复验；当前没有必须再次修改PR源码的返工集合。

审核对象只限 `bdc698873999d3fc1773e76588339276ddc581ca`／`9dc07cf45cb02ba31e047f266380be85717a64f2`。后续HEAD变化必须按实际差异再评估，不把此结论套给未知版本。本Chat没有改GitHub文件、提交Review、合并、启动DEV-PR-03、触及MAIN／Goal／预算／科研证据或运行真实研究。

**MAIN 下一管理动作：**以本报告及证据包作独立审阅材料，单独记录是否MAIN ACCEPTED、如何处置外部helper MINOR；任何GitHub持久化或合并仍由MAIN在适用授权下组织。

---

## 附录：交付索引与复验入口

随附证据包保留本报告、逐文件delta、独立摘要／tree结果、原始reviewer probe及适配diff、两组新独立运行和旧红对照、套件重跑日志、远端原始ZIP与关键结果。开发者helper／adapted的已有运行记录单独放在developer-records，不与reviewer-results混放。

`reproduce_r3.py` 从固定摘要的远端Artifact中安全建立新临时软件快照，重算Git tree，再运行包内审核者脚本和限定原套件。它不联网、不调用真实模型、不执行缺失的开发者helper，不修改GitHub。运行前应阅读README及该脚本；其结果只支持相同限定范围。`reviewer-code/integrity_r3.py` 记录本次对原始用户附件的完整计算，复跑该附件级检查另外需要同一批原始上传文件；便携入口不伪造这些输入。

文件完整性以随附SHA256SUMS为准。审核建议、MAIN正式验收、GitHub合并、软件合同通过和数学科学资格始终是不同记录。

**交付前便携复验：**本审核已实际执行随包 `reproduce_r3.py`，在另一新临时目录重建并认证新旧源码树；旧50/9红对照、原脚本预期提前拒绝、审核者59/59＋59/59、原119/48/6及AST均再次得到预期结果。外部helper仍NOT_EXECUTED；原始便携复验stdout/stderr保存于`results/portable-reproduction.*.log`。
