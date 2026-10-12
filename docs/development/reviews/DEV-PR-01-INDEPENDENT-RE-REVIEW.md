# PMRH DEV-PR-01 Independent Re-Review Report

**日期：**2026-10-12  
**审核角色：**Independent Security & Architecture Reviewer（GitHub 只读＋严格隔离合成核查）  
**最终结论：**`APPROVE_FOR_MAIN_ACCEPTANCE`  
**权限说明：**此结论仅表示可以提交 PMRH Development — MAIN 作正式验收与合并决定；**不是**本 Chat 宣布 `ACCEPTED`，本 Chat 没有合并 PR。

## A. Review Identity 与审核边界

| 字段 | 经 GitHub Connector 独立确认 |
|---|---|
| Repository | `ZhiyaoXiongMath/pure-math-research-harness` |
| PR | <https://github.com/ZhiyaoXiongMath/pure-math-research-harness/pull/2> |
| PR 状态 | `open`，`merged=false`，`mergeable=true`，非 draft |
| Base SHA | `977e866d64bba5cf7b5549f17a3d4b5599a4c20a` |
| 旧审核 HEAD | `419a180fdf4b114691e8e44c8bf955e10a410970` |
| 本次冻结 HEAD | `f8f93e962100010489946f4d82e302ea187c9874` |
| 开发分支 | `chore/dev-pr-01-static-offline-baseline` |
| 新增提交 | 旧审核 HEAD 后 12 个 commits |
| PR 改动文件 | 共 12 个，旧审核 HEAD 后涉及 9 个 |
| 原始 PMRS 固定源码 | `e4de0210f9985224e030ac4cfd2f7e2904005b37` |

本次先阅读了上一轮完整《PMRH DEV-PR-01 Independent Security & Architecture Review Report》（上一结论 `REQUEST_CHANGES`），以及当前 PR 在冻结 HEAD 下的 `docs/development/DEV-PR-01-INDEPENDENT-REVIEW-FINDINGS.md`。后者明确记录 4 MAJOR、2 MINOR 的开发者修复结果，而没有冒充独立验收。

审阅方法：独立读取 GitHub PR metadata、旧新 HEAD compare、修复涉及的全部源码及测试、CI workflow、两个最终 Actions 的 run/job/step、成功与先前失败的原始日志；下载最终 artifact 到隔离容器核对字节与依赖图；另将 CI artifact 验证器**按冻结 GitHub blob 原字节复原**并针对缺失/篡改证据执行新的临时合成测试。没有重新审计已可靠覆盖的无关运行时，也没有执行真实科研、模型调用或旧测试套件。

### 差异范围

PR 的完整 12 个文件：

1. `.github/workflows/devpr01-offline.yml`
2. `config/architecture-exceptions.json`
3. `docs/development/DEV-PR-01-BASELINE.md`
4. `docs/development/DEV-PR-01-INDEPENDENT-REVIEW-FINDINGS.md`
5. `scripts/architecture_deps.py`
6. `scripts/offline_guard/sitecustomize.py`
7. `scripts/offline_test.py`
8. `scripts/verify_devpr01_artifacts.py`
9. `tests/devpr01/__init__.py`
10. `tests/devpr01/test_review_closure.py`
11. `tests/devpr01/test_review_regressions.py`
12. `tests/devpr01/test_static_and_offline.py`

与上一审核 HEAD 相比，实际变动为 workflow、两份开发文档、三个原有实现脚本，以及新增验证器和两个新测试模块，共 9 个文件；原 8 文件中的 exception policy 与原测试不变。全部文件仍属 DEV-PR-01 的 AST、受控离线测试、安全防护、CI 证据及审查文档职责范围。没有修改 `research_studio/`、科研证据 schema 或任何 MAIN/Goal 代码，未加入 DEV-PR-02/03 的实现。冻结前后再次检查 PR/head/main：`main` 仍为 Phase 0 SHA，PR HEAD 仍为 `f8f93e9...`，未合并。

## B. Evidence Verification — 独立读取 GitHub、日志和 artifact

| 项目 | 原始真实证据 | 本次核查 |
|---|---|---|
| DEV-PR-01 | [Actions 38234570618](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38234570618), Job `114761973046` | `completed/success`，每个 step success；48/48 synthetic `OK`；强制四文件证据校验 success；上传 success |
| Phase 0 | [Actions 38234570610](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38234570610), Job `114761972816` | `completed/success`，每个 step success；6/6 `OK` |
| 原反例红灯 | [Actions 38233107438](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38233107438) | `completed/failure`；30 个测试中 SEC-01、AST-01、AST-02 三项新增负例失败，明确证明当时仍有漏洞 |
| 扩充测试红灯 | [Actions 38234040946](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38234040946) | `completed/failure`；48 项中 1 项测试断言把 YAML 注释与表达式中的 `||` 视为吞错；后改为仅检查执行层复制命令，负例未删除，完整性 gate 未放宽 |

两个最终成功 run 的 `head_sha` 均为 `f8f93e962100010489946f4d82e302ea187c9874`。GitHub Actions 的 checkout 实际为测试合并提交 `023b81634a6561870ec42c5f543f1aa583b1a868`；分别独立读取两个 Git commit 对象，确认其 Git tree SHA **均为** `5681becd4810657210643d99928f5f663c9f9760`。因此执行源码树与本次 PR HEAD **字节身份一致**，不是简单相信 `PMRH_SOURCE_SHA` 环境变量。

### Artifact 身份与逐文件验证

[Actions artifact #11739533909](https://github.com/ZhiyaoXiongMath/pure-math-research-harness/actions/runs/38234570618/artifacts/11739533909) 仍存在、未过期。已通过 GitHub Connector 下载到隔离容器，重新计算其完整 ZIP SHA-256：

`f779fb2ee83f27e9e57b4cb865e4d703a7f1c3ea720c2475a41c532f5ad12145`

与 GitHub API 的 artifact `digest` 和 Actions 上传日志一致；ZIP CRC 无错误。包含**恰好 4 个**必要文件：

| 文件 | 经独立计算的 SHA-256 |
|---|---|
| `ast/dependency-graph.json` | `1c697e4aad98c5a1b5b4d01e0736d8542328931810773236186ef7a3f2074aee` |
| `ast/architecture-audit.md` | `8d464159a3ab51549122d8069e6d3ec00ff9a2c978fec04891cd101b086d1b47` |
| `offline/receipt.json` | `e375cad1af600550fade540645f4c574fcbaedf49272c795227e4a95fb4e92a0` |
| `offline/unittest.log` | `8a193ddac396e903302837b20d14ab993ca4dc471df93ccbdf6b9bdde3acca2b` |

全部四个文件摘要与 CI `PMRH_REQUIRED_ARTIFACTS=PASS` 回执相同，且原始 unittest 日志的 SHA-256 与 `receipt.json.output_sha256` 相同。完整日志以 `Ran 48 tests in 0.241s` 及 `OK` 结束，`exit_code=0`、`status=PASS`、`execution_error=null`。部分测试打印了嵌套合成错误回执或 argparse 诊断，造成个别 `... ok` 与日志内容同线/交错；并未出现最终失败，`unittest` 实际计数为 48。

### AST 图的独立计算

从实际 JSON 的 148 个图节点（144 个源文件＋4 个 namespace 虚拟节点），独立枚举邻接表、直接边及逐节点可达性，与 JSON 的传递闭包逐项完全一致：

| 统计 | 本次验证值 |
|---|---:|
| Python 源文件 | 144 |
| Namespace 虚拟节点 | 4 |
| Local import occurrences | 1,483 |
| 唯一直接依赖 | 987 |
| 唯一传递可达关系 | 6,160 |
| 非平凡 SCC | 1 |
| Legacy provisional cross-layer entries | 442 |
| Named architectural couplings | 4 |
| 当前工具报告的新层违规 | 0 |
| AST 解析失败 | 0 |
| 工具支持模式下的新层 unresolved | 0 |

报告源文件清单摘要：`b40dd8e38ab6b80c15e75ab43d2be4b97f375665d0bb5d501facd7f51774c3f1`，与最终 CI 输出一致。统计一致性不是通用 AST 算法正确性证明；具体最小反例在下一节逐条核查。

## C. 六项独立复验 Findings

| Finding | 前次等级 | 独立结论 | 源码与检验重点 |
|---|---|---|---|
| **SEC-01** | MAJOR | **PASS** | `scripts/offline_guard/sitecustomize.py:168–179` 全面拒绝 `os.link`，原硬链接→沙箱路径写入的通道关闭；原反例和普通沙箱写入分别为负/正测试 |
| **AST-01** | MAJOR | **PASS** | `scripts/architecture_deps.py:119–151,190–226,411–416` 识别 importlib 直接/模块别名/函数别名，shadowed/nonliteral 明示 unresolved，新包 unresolved fail closed |
| **AST-02** | MAJOR | **PASS** | `scripts/architecture_deps.py:291–300,365–410` 令未知 `pmrh` 根模块 fail closed，并核对经 bridge 的禁止传递关系；合法 root initializer/CLI 测试仍通过 |
| **CI-01** | MAJOR | **PASS** | workflow `49–90` 不再忽略 `cp` 错误；`verify_devpr01_artifacts.py:17–104` 对四文件、HEAD、哈希、日志结果做成功门槛；本地 exact-blob 验证器补做缺失/篡改负例 |
| **TEST-01** | MINOR | **PASS** | `scripts/offline_test.py:167–222` 对 TimeoutExpired 和 OSError/SubprocessError 写入结构化 ERROR 回执；真实最终 log 包含两种合成回执，且 tests/model counts 均保持未知 |
| **AST-03** | MINOR | **PASS** | `scripts/architecture_deps.py:423–437` 将 4 个 Named Coupling 与 442 条 provisional cross-layer entries 分开；4 项均在实际 `direct_imports` 中逐项匹配 |

### SEC-01 — 硬链接安全绕过

上一轮的关键反例为 `os.link(source_file, scratch/alias)` 然后写入 `scratch/alias`，使同一 inode 的原源码被改写。新 `guarded_link(*args, **kwargs)` 统一抛出 `PermissionError` 并覆盖 `os.link`；比尝试判定源/目标路径更加保守，因此不允许通过同一解释器创建源码至 scratch 的硬链接。`tests/devpr01/test_review_regressions.py:27–44` 保留**原反例**，验证直接源写入和硬链接创建都拒绝、源 SHA-256 未变，正常独立合成文件仍可写。

旧红灯运行中该测试实际因“未抛出 PermissionError”失败；新 HEAD 原样保留并通过。确认在**该 Python monkeypatch 承诺范围**内修复，没有退回到单纯文档免责。剩余 pre-existing hardlink aliases、native syscalls、继承 FD 等不归此 guard 声明保证。

### AST-01 — `import_module` 别名静默漏报

原反例 `from importlib import import_module as load; load("pmrh.adapters")`，目标 `pmrh/adapters/` 无 `__init__.py`。新增 `dynamic_import_bindings` 对已知 `importlib`/`builtins` 的模块及函数别名建立保守 AST 绑定；`graph_from` 将已知字面目标加入原有 namespace 依赖图。对别名重新赋值、非字面动态目标、相对包名无法解析等情况写入 `dynamic_unresolved`，而 `run()` 将 `pmrh` 中未解析导入列为 `architecture_violations`，由 `--check` 拒绝。

核验了 `test_review_regressions.py:58–70` 的原反例，以及 `test_review_closure.py:73–123` 对 direct alias、`as load`、`import importlib as il`、`__import__`、nonliteral、shadowed 和合法同名普通函数的正反用例。原红灯失败、新最终 CI 通过。实现仍非任意运行期反射或任意赋值的数据流分析，已准确披露。

### AST-02 — 未分类 root bridge 绕过依赖约束

原反例 `pmrh/domain/reader.py → pmrh/bridge.py → @namespace/pmrh/adapters`。新 `layer()` 将未知 `pmrh` 根模块归为 `unclassified`，`run()` 在任何源模块未分类时直接报告违规，且对边的未知端点和经过中间模块的禁止可达关系另做检查。根 `__init__.py`、`__main__.py`、`cli.py` 的受限归属通过显式映射处理。

实际保留 `test_review_regressions.py:72–99` 原反例和合法正例；`test_review_closure.py:125–159` 还测了孤立 unknown root、initializer 非法导入以及合法应用→端口→领域依赖。原红灯失败、新最终 CI 通过。没有以删除中间层节点、放宽 domain→adapters 或禁用传递图掩盖问题。

### CI-01 — 必需四份 artifact fail closed

新版 workflow 的 staging 复制在 `set -euo pipefail` 下执行，不再使用 `cp ... || true`；子测试失败后按退出码使 Job 失败，同时保留能够复制的诊断。验证步骤显式调用 `scripts/verify_devpr01_artifacts.py`，检查四份文件是否存在、非空且非符号链接，并校验 graph schema/violations、命名耦合、测试 PASS/计数、原始日志哈希、精确 HEAD、未测量模型次数语义。Upload step `if: always()` 与 `if-no-files-found: error` 只提供失败诊断，不能把先前失败变成最终 success。

**独立加做的实际合成测试：**将 GitHub 提供的验证器源码恢复为本地 Python 文件，使用 `git hash-object` 验证其 Git blob 与冻结文件 SHA **完全相同**：`3630d6593a23ac8bf112ceb9fe1659b62997a59f`。然后在临时目录中以最终真实 ZIP 四文件运行 `validate()`，返回 PASS；删除 `offline/receipt.json` 后返回 `ValueError: required CI artifact missing...`；恢复后向 `unittest.log` 追加字节返回 `ValueError: raw unittest log checksum mismatch`。真实最终 GitHub CI 的四文件强制步骤成功、上传步骤成功。该 MAJOR 已关闭。

### TEST-01 — Timeout / spawn error 的证据真实性

`_execute_guarded` 在 `subprocess.TimeoutExpired` 下保留可用的部分 stdout/stderr，生成 `execution_error.kind=TIMEOUT`；对 `OSError`/`SubprocessError` 生成 `PROCESS_START_OR_TRANSPORT_ERROR`。两类路径的 `status=ERROR`、`exit_code=null`、未知 `tests=null`、模型 `count=null`，并写同一 SHA-256 所约束的 `unittest.log` 与 `receipt.json`。最终 CI 的**原始测试日志中实际出现两份内嵌模拟失败回执**，经独立 JSON 解析核对类型、partial flags、状态和未知计数均符合上述规则。`tests/devpr01/test_review_closure.py:207–239` 的负例通过。系统被 SIGKILL、磁盘耗尽等更强故障下无法保证产生完整回执，CI 仍须失败，不列入本 PR 的独立阻塞。

### AST-03 — 具名 Legacy 耦合与 442 项预估迁移边界

独立从最终 `direct_imports` 与 `legacy_migration_blockers` 逐项重算四个具名关系：

| 具名耦合 | 直接导入 occurrences | 跨层迁移 entries | owner | 状态 |
|---|---:|---:|---|---|
| `store.py → native_main.py` | 2 | 0 | DEV-PR-05 | MATCHED_DIRECT_EDGE |
| `codex_client.py → runner.py` | 3 | 0 | DEV-PR-07 | MATCHED_DIRECT_EDGE |
| `workspace.py → native_main.py` | 1 | 1 | DEV-PR-08 | MATCHED_DIRECT_EDGE |
| `scheduler.py → host_pool.py` | 1 | 0 | DEV-PR-06 | MATCHED_DIRECT_EDGE |

四项 source/target、实际直接导入计数、跨层计数与报告完全一致，且缺失具名边会触发违规。保留 442 条 *provisional* 迁移边为另一组数据，不冒充最终完整重构清单。这一 MINOR 已关闭。

## D. 新回归检查及 Remaining Limitations

本轮新直接回归检查结论：**没有发现足以阻止 DEV-PR-01 合并的 BLOCKER 或 MAJOR。** 实际证据表明旧测试未被移除；新增三项红灯最小反例在修复后成为绿灯；语义仍为“静态 AST + Python 级安全守卫 + 合成测试”，没有扩大科研权限或修改旧科研实现。CI 执行完整后旧 `research_studio/` Git diff 为零，PR 实际改动仅 12 文件。

以下为准确披露且不阻止本次合并的 **ACCEPTED LIMITATIONS**：

- **Python 级防护≠OS 沙箱。** 对已有硬链接别名、继承 FD、原生扩展、系统调用及恶意改变运行环境没有强保证；临时 artifact root 必须由可信 CI/操作人员提供。不得因此声称可安全执行不受信任的旧 suite。
- **静态 AST≠完整运行时依赖。** 任意计算式导入、运行时 `exec`、反射、插件加载及无法识别的别名数据流未得到完全闭合。新代码对其支持的已知别名及 unresolved 模式保守报告；后续新模块仍须新增针对性测试。
- **模型调用次数未被真实测量。** 最终回执 `research_model_calls.count=null`、`measurement=NOT_INSTRUMENTED`、`observed_provider_events=NOT_MEASURED`、`zero_calls_verified=false`，不存在伪称“实测 0 次模型调用”。
- **NOT_EXECUTED：**历史 `scripts/test-runner.py` 和全套旧测试、原生 Codex、真实 MAIN/Goal、正式科研项目路径与权限、目标 Ubuntu 26.04/browser/PDF 产品门、真正的 provider 调用与系统级沙箱验证、未来 58+46 项科研产品验收、科研证据迁移。它们属于相应后续授权/PR 范围。

GitHub hosted Actions 获取 checkout/action 时具有基础设施网络连接，“合成 Python 子进程禁止常见 socket/process”不能被表述为整台 CI runner 完全无网络。

## E. 最终结论与交付 MAIN 的 Next Action

**Final verdict：`APPROVE_FOR_MAIN_ACCEPTANCE`**。

六项上一轮 Finding 全部在本次规定的、可验证的 DEV-PR-01 契约范围内判定 **PASS**。旧失败与新通过有真实 GitHub 日志对应；最终 HEAD、CI test-merge Git tree、四个 artifact 和测试计数及 SHA 链相互一致；不存在新发现的合并阻塞项。

**建议 MAIN：**可基于本报告正式验收 DEV-PR-01，再在独立授权流程中合并 PR #2。正式 `ACCEPTED` 和实际 merge 仅由 PMRH Development — MAIN 决定。如合并前 GitHub HEAD 再次改变，则重新核对新提交和 CI，不能将本报告自动应用到不同 tree。DEV-PR-02/03 不在本轮执行。

**实际操作界限：**本 Chat 只进行了 GitHub read-only 检查和隔离临时文件的安全合成验证；没有 GitHub 写入、提交、审查评论发布、合并、运行正式科研项目、调用研究模型、修改私有科研文件或启动 DEV-PR-02/03。
