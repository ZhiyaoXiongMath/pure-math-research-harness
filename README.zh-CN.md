# 纯数学研究 Harness（PMRH）

**当前开发：只读状态查询 MVP，尚未发布科研运行时。** PMRH 保留原 Pure Math Research Studio 4.2.2-preview 的历史与兼容代码。新命令读取已有原生项目事实，不启动科研、不对账资源池、不刷新认证、不重建索引。帮助与版本入口保持无运行操作；控制命令仍不支持。[English](README.md)

在源码 checkout 根目录使用 Python 3.11+、POSIX/Linux，并禁用字节码写入；状态查询不需要原生程序、模型凭据或额外 Python 依赖：

```sh
python3 -B -m pmrh status ./existing-project --instance INSTANCE --json
```

已安装入口使用 `PYTHONDONTWRITEBYTECODE=1 pmrh status ./existing-project --instance INSTANCE --json`。`PROJECT` 是包含 `project.json` 与 `HEAD` 的原生项目目录，不是工作区目录。可选 `--as-of COMMIT` 指定已有完整 journal SHA-256。退出码：项目状态可读为 0，项目数据不可用为 1，参数错误为 2。例如，查询不存在的 `./missing-project`，JSON 包含 `"available": false, "unavailable_reason": "NOT_FOUND"`，该目录仍不存在。

项目各投影共用一个提交；全局池有独立观测时间和原件摘要，池缺失时计数为 null。运行时、认证与配置均为未观测；此命令不核验报告文件。PAUSED、UNKNOWN 与精确科研范围保持原义。参见 [DEV03 合同与限制](docs/development/DEV-PR-03-CONTRACT.md)。

开发约束：[AGENTS](AGENTS.md) · [CONTRIBUTING](CONTRIBUTING.md) · [工作包规划](docs/development/ROADMAP.md)。以下保留原 PMRS 4.2.2-preview 历史说明，其运行能力陈述不代表 PMRH 验收。

---

# 纯数学研究工作室 4.2.2 预览版

[English](README.md) · [架构](ARCHITECTURE-4.2.2.md) · [变更](CHANGELOG-4.2.2.md) · [验证限制](TEST-REPORT-4.2.2.md)

PMRS 面向纯数学研究者，在本地项目中保存原始来源、候选命题、原生 Argument、独立评估、研究决策、通信和可观测模型用量。模型输出在获得所需科研资格前，仍是候选研究材料。

本分支是 **candidate22 的代码预览版**，包含公开前清理及文档更新。candidate22 已构建、隔离安装，并经历唯一 HSC eigenvalue 真实 TRH 实验及软件修复。该实验数学状态仍为 **OPEN**，后续已按用户要求**暂停**，原生 Goal 也已暂停。这**不代表全部功能验收通过**；FDH、SURVEY 和实验未自然覆盖的行为均不标为实测通过。本仓库不分发私人材料、数学输出、原始会话、认证状态或本地日志。本次代码推送不创建 tag 或 GitHub Release。

## 已实现的能力

| 产品 | 输入 | 控制与结果 |
| --- | --- | --- |
| **TRH — Targeted Research Harness，目标研究 harness** | 完整原命题、假设、约定及材料 | 独立 `gpt-6-astra` Ultra MAIN 动态决定 P0–P13 工作及 P14，保留证据和具有明确资格或 OPEN 的结果 |
| **FDH — Formulation Discovery Harness，表述发现 harness** | D0 现象、不可变背景及允许探索轴 | 另一独立 Astra Ultra MAIN 动态选择 D1–D4；正式 D5 将有证据的候选和比较关系交给研究者 |
| **SURVEY — Survey Workflow，综述工作流** | 主题、所选来源和输出要求 | 宿主线性推进来源研究与报告，不拥有 MAIN Goal |

每个 TRH/FDH 实例拥有独立持久原生 Codex 线程和 Goal，绑定原目标或 D0 范围、验收条件及有效授权。完整动态方法进入真实 MAIN 输入，恢复或压缩上下文后仍可取得。阶段、路线、并发、回流、通信和交付由 MAIN 决定；宿主负责资源准入、执行有效决策和记录。MAIN 不可用时不会退回宿主自动规划科研流程。

当前实现包括：

- MAIN 派发的阶段 CLI 任务、定向通信、依赖和明确等待。单次派发及每实例在途阶段任务各最多 **8** 个；所有项目共享 **20** 个阶段槽。SURVEY 串行且计入全局池。
- MAIN 和 Codex 原生内部委派不占阶段槽；PMRS 不另设内部数量、并发、层次、模型或 token 限制。已授权 PMRS 顶层调用额度有限且累计，续轮与维修不会重置。未知用量保持未知；父子计量重叠不明时不相加。
- 原始来源版本、原生 Argument、精确范围和 P9/P12/D4 独立性。独立的内部 agent 或输出格式接纳，本身不构成独立数学资格。
- 网页可展开实际 MAIN/阶段输入、材料、原始输出、修复版、接纳结果、科研正文、通信、错误和用量，并下载原件。
- 事件驱动的指导与结果处理共用一个 MAIN 执行流。默认每 30 分钟轻量检查控制状态，距上次完整审计约四小时有效研究后提醒完整战略审计；均可配置。正常等待不额外发起付费分析。实例整体暂停与纯外部等待冻结研究时钟，并行 agent 工时不叠加。MAIN 产生的检查点不可改写，独立于可清理的重放缓存。
- 每次 P14 前保存可读 P13 报告。正式稿件/PDF 仅由明确请求或已选择的输出设置生成，不为每阶段追加写作链。界面支持英文和简体中文。

## 环境和安装

原生运行环境当前面向 **Linux x86_64**，需要 **Python 3.11+** 和浏览器。阶段任务需要已认证的官方 Codex CLI 及所配置模型模式的访问权限。PDF 另需配置 TeX/编译器资源；图形安装器使用 Python Tk。PMRS 检查能力，不静默降低 MAIN 强度。

这是**仅含源码的分支**，两个已编译原生可执行文件不存入 Git。仅安装 Python 包不足以运行 MAIN。[原生运行环境说明](docs/NATIVE-RUNTIME.md) 记录固定源码版本、准入补丁、许可证、配套程序精确来源及已知构建限制。

在新目录获取代码：

```sh
git clone --branch 4.2.2-preview https://github.com/ZhiyaoXiongMath/Pure-Math-Research-Studio.git pmrs-preview
cd pmrs-preview
```

打包前须准备原生程序对。可以按原生说明提供此前已核验的一对程序及匹配清单，也可以使用自行取得的官方配套程序构建修改后的 app-server：

```sh
# 设置为你自己的、已核验官方配套程序的绝对路径。
# 所需 SHA-256 记录在 docs/native-code-mode-source.json。
export PMRS_CODE_MODE_HOST="$PWD/../native-tools/codex-code-mode-host"
sh scripts/build-native-main.sh "$PWD/../pmrs-native-build" "$PMRS_CODE_MODE_HOST"
```

原生构建需要 C/C++ 工具链、pkg-config、OpenSSL 开发头文件、curl、tar、patch、网络和足够的本地构建空间；脚本使用隔离 Rust 工具链。同源码版本配套程序的构建曾因上游 V8 归档不可用而受阻，不能假定任意 Codex 配套程序均兼容。本次源码推送未重跑该原生构建或新增模型探测。

准备并核验原生程序对后，在本地构建并安装到**全新**目录：

```sh
python3 -B scripts/build-release.py --out ../pmrs-packages
python3 -B scripts/prepare-release.py \
  ../pmrs-packages/Pure-Math-Research-Studio-4.2.2-release.zip \
  --out ../pmrs-unpacked --desktop-dir ../pmrs-applications
python3 -B ../pmrs-unpacked/Pure-Math-Research-Studio-4.2.2/scripts/install-local.py \
  --venv --prefix ../pmrs-install --bin-dir ../pmrs-bin \
  --desktop-dir ../pmrs-applications
../pmrs-bin/pmrs-desktop --workspace ../pmrs-workspace
```

`build-release.py` 只生成本地产物，不发布 GitHub Release。`prepare-release.py` 核对包清单并保留安全可执行权限。安装器拒绝已有前缀或启动器；传输产物后请核对生成的 SHA-256 清单。工作区和认证资料保存在 checkout 外。4.2.2 不迁移旧项目格式，旧项目继续使用原版本。

## 使用与控制

1. 打开**设置与登录**，选择官方 Codex CLI，核对认证、模型能力及可选报告依赖。不要提交认证文件或带会话凭据的网址。
2. 创建项目，选择 TRH、FDH 或 SURVEY，输入完整目标/范围并添加原材料。选择或查看已有工作本身不启动研究。
3. 通过**开始研究轮次**提交具体意图、来源选择和明确的有限顶层调用额度。阶段角色遵循配置的阶段/角色/purpose 矩阵，研究选择由 MAIN 决定。
4. 查看**实际任务输入输出**、路线/候选、有效指导、审计、消息和报告。区分 PMRS 请求的控制状态与实际观测的原生 Goal 状态及同步错误。
5. TRH 默认**自动推进**，P14 在原范围和原额度内续接同一 Goal。选择**每次 P14 等待人工决定**或**在下次 P14 停下**，在相应节点交回控制权。取消标志、查看暂停项目或切换模式本身不恢复；一次明确继续不会暗中更改 P14 模式。
6. FDH 正式 D5 暂停后由人选择继续发现、明确采用候选、保持暂停或结束。交接 TRH 只建立拥有独立 MAIN/Goal 的暂停新实例，启动仍需授权；普通候选综合不暂停发现工作。

**立即暂停**停止新派工；已发送工作和用量继续保留。关闭浏览器不暂停后端。阶段结束、暂停、用户结束或预算耗尽都不等于 Goal 成功。新目标和追加预算需要用户决定。

## 输入输出示例

以下为**操作示意**，不是此次新增执行的验收场景。仓库[教学材料](examples/readme/finite-geometric-sums.teaching.md) 已明确标注教学性质。

- **输入：**新建 TRH 项目，目标为“对正整数 n 与实数 q 建立有限等比和公式，单独处理 q = 1”。附加教学来源，在启动表单中选择明确有限额度。
- **预期产品输出：**不可改写的来源条目；真实 MAIN 及其所选阶段任务输入输出；候选命题/Argument 和审查记录；注明精确范围、证据和剩余缺口的 P13 报告。示例不承诺成功判词，教学材料也不是独立审查。
- **查看：**展开任务并下载原始输出，对照其接纳状态、数学支持与报告；失败或 OPEN 结果仍可见。

保留已有示例、fixture 和正常测试源码，但它们不构成 candidate22 实测验收。本次代码推送未运行模拟场景、压力测试、新科研调用、FDH/SURVEY 付费验收或测试矩阵。详见[验证限制](TEST-REPORT-4.2.2.md)和[验收范围](ACCEPTANCE-SCOPE-4.2.2.md)。

## 许可证

PMRS 采用 [Apache-2.0](LICENSE)。源码资源保留相应许可和归属，包括 MathJax 与原生客户端补丁的上游许可。本分支不包含原生二进制或私人实验记录。

DEV05 开发检查入口：`python3 -B scripts/offline_storage.py --out <新建证据目录> --oracle <冻结的DEV05基线>`。
入口必须先验证 bwrap 隔离；无法隔离时停止，不回退到裸执行。执行状态和范围见
[DEV05 合同](docs/development/DEV-PR-05-CONTRACT.md)。仅使用旧接口的项目保持原 journal 格式；
显式合成测试项目可由可信装配启用 `pmrh.commit/1`，旧版本会拒绝读取。未提供正式项目激活或迁移。
