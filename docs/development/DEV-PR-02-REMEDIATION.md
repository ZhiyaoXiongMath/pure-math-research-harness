# DEV-PR-02 — MAIN 定向返工记录（R2）

日期：2026-10-13。角色：原 Development Chat。PR：[#4](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/4)，仍使用 `feat/dev-pr-02-ports-dto-contracts`。

**本记录是开发者修复与测试记录，不是独立复验或 MAIN ACCEPTED。**
独立审核及 MAIN 的上一结论均为 `REQUEST_CHANGES`。**当前状态 BLOCKED：本地修复已测试，但 GitHub create_tree 写入被平台拦截，没有生成新 tree/commit/HEAD；远端仍为 dd044d09...。本文和其代码是未提交的候选文件，不能当作远端已完成的返工。**

## 1. 冻结基线与原始证据

main：`efd2be4e93ca8f1ee9f6a03fa53df6a1f008c8fb`；返工前 PR HEAD：`dd044d09acaae7ddc250e9f96cd0ba4e940bf467`；tree：`82d02d5b4adce11429df748b211fd72f9f42be28`。本轮开工通过 Connector 重新读取 main、PR 和分支 ref，三者与独立审核一致。没有创建新分支或新 PR。

附件按原字节保存：

| 文件 | SHA-256 |
|---|---|
| `PMRH-DEV-PR-02-Independent-Review-2026-10-13.md` | `8089d2323d8ba3ff381857cfd5d511722fbbffb0bdb3e24101bdfd8b240e5060` |
| `PMRH-DEV-PR-02-Independent-Review-Evidence-2026-10-13.zip` | `bf7866b5dde3d67932894685229f9a3364996c3dd8c2a4a71a199efc5d42330c` |

两项外部摘要、ZIP CRC、包内 451 项文件摘要均核对。开发用旧源码来自原 GitHub Artifact 的 277 文件快照；按路径、模式和 bytes 重算 tree，与冻结 GitHub tree 一致。这不是完整 Git clone，也不用于冒充历史迁移。

先阅读审核 H、I、J 和附录，再阅读测试脚本及其全部副作用路径。原 `independent_probes.py` 摘要为 `55ad9f3e1d95ffc153c0b32d5bc18bb0254174fc744b2c2e2fd715ff2a3aa97a`。在冻结源码上**原样复现**：59 项，50 PASS、9 FAIL、0 HARNESS_ERROR。两份原 helper 的原始探针另行安全复现：6 项，4 PASS、2 FAIL。输入源码和原始证据没有修改；本次复现另存输出，不覆盖审核者日志。

## 2. 六项修复

### REV02-WIRE-01 / MAJOR

`pmrh/ports/dto/wire.py` 新增统一 `_wire_budget`：公开 `to_wire`、`to_json`、`wire_digest`、`from_wire`、`from_json`、`decode_wire` 共享完整文档的 canonical UTF-8 预算 **8 MiB**，没有提高旧大小常量。结构预算为深度 64、节点 262144，序列原限制 4096 保留。

预算按每个出现位置累计，不因多个 slice 引用相同对象而漏算。字符串按真实 UTF-8 与 JSON 转义后长度计算。编码在返回可传输对象/文本或 digest 前拒绝超限。文本接收另外限制输入文本本身（包括空白）为 8 MiB；由本 codec 成功生成的 canonical 文本必定满足该界限。

`_decode_dto` 是完成一次完整 preflight 后使用的内部嵌套 decoder，避免每个子 DTO 重启全局预算、反复序列化整个子树。深度和节点预算在构造 wire DTO 之前检查，循环对象输入明确失败。合法值对象可在本地构造；超出传输预算的聚合在编码时拒绝，不能生成自己读不回的 wire 文档。

回归包括七个合法 1 MiB slice 聚合、较小多 slice roundtrip、六 slice 调整至精确 8 MiB 与再多一字节、Unicode/转义导致字符数与 UTF-8 字节数不同、深度/循环与总节点限制。

### REV02-EVENT-01 / MAJOR

`pmrh/ports/dto/events.py:_page_invariants` 在已有作用域、序列、GAP 和 next cursor 检查之外，对每个 Runner event 要求 `envelope.invocation_id == cursor.stream_id`，对每个 Provider event 要求 `inference_id == cursor.stream_id`。

同一构造不变量覆盖直接构造、两个 decoder 和 registry decoder。新增同 stream 正例、整个错误 stream、多事件中混入一项、FakeRunner 返回页遭错误 fixture 污染，以及实际 FakeProvider 事件生成合法页的测试。没有改为独立 opaque stream ID 或引入真实适配器。

### REV02-UNKNOWN-01 / MAJOR

`tests/devpr02/fake_runtime.py:FakeModelProvider` 中，有冻结 spec 的 validation、stream、UNKNOWN、NOT_SENT、幂等冲突和提前拒绝，都绑定 `operation_id=spec.inference_id` 与完整 parent `InvocationIdentity`。上游 policy/validation 拒绝进入 stream 返回时保留 code、原证据和 recovery safety，并明确标为正在尝试的 STREAM 操作。

`pmrh/ports/dto/core.py:ErrorEnvelope` 对已知 parent identity 的 STREAM/VALIDATE_REQUEST 错误禁止缺少 operation_id。这里 operation_id 是 PMRH 的本地 inference 身份，**不是** provider_request_id，也不创造远端身份。没有可用 spec 的描述操作可以保持未知；已知 Provider cancel 的拒绝也保留 inference 关联。

原 `inference_keys` 跨 key 防重发、相同 key/payload 返回原回执、UNKNOWN 的 DO_NOT_RESEND 均保留。新增同 parent 两 inference 的错误不同、wire 保留、无 provider ID、早期拒绝关联、冲突和同操作重试的副作用计数回归。

### REV02-CI-01 / MAJOR

`scripts/verify_devpr02_artifacts.py` 的 `expected_test_ids` **只读解析冻结源码 AST**，建立唯一的完整 unittest 方法清单，而不信任可与日志同时篡改的 receipt count，不永久硬编码 86 或 119。批准的套件形状是顶层、直接继承 `unittest.TestCase`、普通未装饰的直接 test 方法；不支持的继承、动态收集、重定义、身份 override 等返回错误，不悄悄缩小清单。该限定不是任意恶意 Python 动态行为的完整静态分析。

`validate_test_log` 要求最终外层成功 footer、每条成功记录的方法名/完整 ID 一致、ID 唯一、ID 集合与冻结源码完全一致，且 count 匹配。最后记录与最终 footer 之间只能存在空白/分隔线；不能在失败后追加一个新的 OK 摘要掩盖矛盾。普通 fixture 文本中的 FAIL 不会被全文搜索误判。

保留原 source SHA、tree、源码指纹、日志 hash、缺文件、执行失败、模型次数未测量和 NOT_EXECUTED 检查。受控入口 `scripts/offline_contracts.py` 也使用相同的清单和结果核验，在结构化 receipt 中保留预期/核验后的 IDs。子进程命令、安全 guard、旧 devpr01 allowlist、隔离路径与输出描述符规则均未放宽。

原 CI 正例夹具原本只有空 `test_example.py`；现改为含一个真实的源码定义 test 方法，日志 ID 绑定实际 module/class/method。原 86 个 test 方法的 AST 方法体全部不变，仅该 `setUp` 夹具升级以适配加强后的清单核验。

新负例保留审核三种完整篡改（都同步更新日志摘要/必要计数），并增加未知 ID、方法名错配、非通过单项记录、源码新增方法、重复定义、动态收集及多重最终摘要。新验证器已用旧真实完整 Artifact 与其旧冻结源码作正常对照；最终新 HEAD 的 Artifact 因写入阻塞尚不存在，仍须后续验证。

### REV02-DOC-01 / MINOR

`DEV-PR-02-DELIVERY.md` §5 的错误摘要修正为：

`a4abd794597343acdbd5671ae540cd5fed3e9dc93abbac0b1a376beab224febd`。

添加本次修订说明；旧日志和同次 receipt 原件不变，错误文本仍可在历史 commit 追溯。

### REV02-HELPER-01 / MINOR

新版 **handoff/2** 交接包中的 `audit-helpers/verify_devpr02_downloads.py` 和 `verify_devpr02_final.py` 改为参数化、显式条件/异常/非零退出码，不用 assert 承担关键检查。不加入生产包，不修改旧交接 ZIP。

两程序均测试正常/优化模式下的合法输入、错误 SHA、缺文件、错误计数、重复 ID、追加失败、只剩一个 test；共 **28 项 PASS**。测试主管先审阅程序，仅在独立 scratch 中启动受原 guard 约束的两个 Python 程序。它们不是可信来源认证、OS 沙箱或独立审核；manifest 的 head/tree/下载摘要仍需 MAIN 与真实 GitHub 核对。

## 3. 本地测试与已知失败

当前源码的受控 Python 3.13.5 suite：**119/119 PASS**（原 86 + 新 33）；命令：

```sh
ARTIFACT_DIR="$(mktemp -d /tmp/pmrh-devpr01-artifacts-XXXXXXXX)"
mkdir "$ARTIFACT_DIR/offline"
PMRH_TEST_ARTIFACT_ROOT="$ARTIFACT_DIR" \
  /usr/bin/python3.13 -B scripts/offline_contracts.py --out "$ARTIFACT_DIR/offline"
```

这些是 pre-commit 本地源码指纹回执，source_sha 保持 UNVERIFIED_LOCAL，不冒充已经提交的 GitHub HEAD。

本轮首次新 suite 跑 106 项时，两个新增资源边界夹具使用了超过既有 1024 字符限制的 ModelParameter，因而 ERROR。没有放宽该限制：改用合法 EvidenceWrite 多 slice 精确边界及每参数不超过限制的 Unicode 参数集合。失败源码快照、106 项原日志和 receipt 保留。后续 118/118 PASS；增加矛盾多 footer 负例后，119/119 PASS。

## 4. 审核九项失败与新的复验方式

| 原 Probe ID | 新预期与对应直接回归 |
|---|---|
| WIRE-19-large-from-wire | 拒绝完整超限对象；WireRemediation.test_WIRE19_20_21_aggregate_decode_limits_are_identical |
| WIRE-20-large-decode-wire | registry 同样拒绝；同上 |
| WIRE-22-valid-DTO-roundtrip-closure | 超限在编码时明确拒绝；test_WIRE22_encoder_refuses_unreadable_aggregate_including_digest |
| EVENT-RUNNER-cross-stream | 拒绝错误 invocation；EventRemediation 相关构造/wire/Fake 测试 |
| EVENT-PROVIDER-cross-stream | 拒绝错误 inference；同上 |
| UNKNOWN-02-per-inference-error-identity | 两个错误 operation_id 分别为两个 inference_id，无伪造 provider ID |
| ARTIFACT-terminal-failure | 同步改 hash 后仍因最终状态异常拒绝 |
| ARTIFACT-one-test | 同步改 count/hash 后仍因冻结 suite 不完整拒绝 |
| ARTIFACT-duplicate-test-ids | 同步计数/hash 后仍因重复 ID 拒绝 |

原审核探针把 `big.to_json()` 放在 case 之外预先执行。修复后它会在该行正确拒绝，因此原脚本不能未经调整继续执行后面的探针。新版交接包另附**显式标记为开发者适配副本**：用七个独立合法 slice 手工构造同一对抗 wire；WIRE-22 分别观察编码拒绝与成功编码后 roundtrip，不把 decoder 拒绝冒充成功。由于远端写入被拦截，没有新的真实 CI Artifact；后测让**新验证器**核验**旧真实 86 项 Artifact 及其冻结旧源码**，正对照通过，三种篡改都在同步修正 hash/count 后被拒绝，不利用 86/119 的普通计数不符制造假绿灯。Ports 测试实际导入本地修复源码。适配后的 59 项全部 PASS、0 HARNESS_ERROR；原脚本在新源码上也原样试跑，确在 case 外编码超限聚合处正确拒绝而中止，不能标为完整 59 PASS。原脚本、适配 diff、旧版红灯、原样后测中止日志和适配后测分别保存；原 Independent Review Chat 仍须自行复验。

## 5. G1–G8 / A01、A03、A04、B04

开发者测试映射（不是新独立审核 verdict）：

| Gate | 本轮证据范围 |
|---|---|
| G1 | 继承 AST 与 guard；原 legacy/source/CLI 不动；最终 CI 再验证 |
| G2 | 全文档资源预算及自编码闭合、多 slice/Unicode/精确边界 |
| G3 | 原八 Ports、六十 DTO、十九错误码保持；Provider 已知 spec 拒绝关联加强 |
| G4 | UNKNOWN inference 身份和原防重发、授权拒绝/CAS 回归 |
| G5 | Runner/Provider 精确 stream 绑定；原 GAP、证据/四轴状态继续保留 |
| G6 | 可信源码完整 test IDs + 最终外层结果 + 原 SHA/hash/错误 gate |
| G7 | 新的最终 HEAD 必须有 Python 3.11/3.13、DEV01、Phase0 真正 CI；仅有本地结果不代替此门 |
| G8 | 原审核/红灯历史保留；文档摘要修正；helper 优化模式修复和单列交接版本 |

A01：Ports 静态依赖方向；A03：身份/stream/error/capture 的契约部分；A04：两模式能力与计量粒度分离；B04：不支持硬 inference 预算则拒绝。只能更新这些契约级部分，不能给产品整体 PASS。

## 6. 安全、未执行与回滚

没有修改 `research_studio/`、原始 Git refs/tags、现有 CLI、安全 guard、例外 snapshot、正式科研记录或 MAIN/Goal/预算。没有真实 Codex/Provider 推理、数学研究、生产数据库或后续工作包开发。本轮 GitHub 只读、一次成功的状态评论、一次被拦截的 tree 写入尝试与后续 PR 元数据更新分别记录；本轮没有成功分支 commit 或新 CI，历史 CI 基础设施网络另记，不把 Python 测试子进程防护说成整机断网。

模型调用计量始终 count=null / NOT_MEASURED，Fake 效果不是模型遥测。
NOT_EXECUTED：生产认证/fencing、原子预算/跨存储事务、journal/blob 崩溃恢复/迁移、真实 native root gate/Provider、OS 对抗隔离、完整旧产品与真实科研，以及全部 58+46 产品矩阵。

合并前关闭 PR 可放弃本轮软件；合并后只能独立软件 revert PR，不重写历史或删除科研事实。完成最终 CI 与证据复核后，开发者最多标记 `READY_FOR_INDEPENDENT_RE_REVIEW`；独立复验、MAIN 接受和合并分别另行决定。

## 7. 平台阻塞与可移交的本地候选

`GitHub.create_tree` 尝试在旧 tree 上加入修复的 `core.py` 和 `wire.py`，平台返回：

> This tool call was blocked by OpenAI because we couldn't determine the safety status of the request.

没有 tree/commit 返回。随后重新读取开发分支仍为旧 HEAD；没有改走其他写接口重试、没有 force push。新 HEAD、new commits、对应最终 HEAD 的 Python 3.11/3.13、DEV01/Phase0 GitHub Actions 均不存在，记为 NOT_EXECUTED / BLOCKED。旧成功 CI 不能冒充修复版验证。

本地 Python 3.13.5 的 119 契约测试、48 DEV01、6 Phase0 均已实际通过；完整 AST 新违规为 0。新校验器针对旧真实 Artifact 的正常及三种篡改输入有真实探针对照；这些仅证明候选文件行为，不是新远端 HEAD 的 CI。

新版 handoff/2 包保存完整未提交源码、相对于 dd044 的补丁、文件摘要、全部原始测试输出及输入证据。MAIN 后续需要在正常可用且已授权的代码写入能力下将候选变更正式提交原 PR，并重新获取新 HEAD 的完整 CI，再交原独立审核 Chat。此交接不授予绕过平台限制的权限；本 Chat 不自行启动其他执行会话。

**最终开发状态：BLOCKED。不是 READY_FOR_INDEPENDENT_RE_REVIEW，不是 MAIN ACCEPTED。**
