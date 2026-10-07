# Pure Math Research Studio 4.0.0

[English](README.en.md)

PMRS 是本机运行的数学研究工作台。定题研究（TRW）围绕精确命题开展推导和审查；表述发现（TFDW）从现象、不变背景和允许探索的范围出发，形成并比较候选。两种流程共享知识与原始材料，分别记录任务、授权、预算和状态。

4.0.0 是当前原生产品的独立发行。它不包含旧版源码、项目升级器、迁移读取器、兼容适配层或真实研究项目样本。新仓库从审核后的文件快照建立全新历史。当前验收记录见[测试报告](TEST-REPORT-4.0.0.md)；尚未实际运行的检查不会计为通过。

## 安装与打开

目标环境是 Ubuntu 26.04，运行时需要 Python 3.11+。从同版本 Release 下载 `pmrs4-graphical-installer_4.0.0_all.deb` 并核对 `SHA256SUMS.txt`。用 Ubuntu 图形软件包安装器安装，完成系统授权后，从应用菜单打开“安装纯数学研究工作室 4.0.0”。选择新的个人安装目录，再点击安装；包内 wheel 离线创建独立环境。缺少的 Python venv、Zenity 系统组件由 Ubuntu 软件源提供。

从应用菜单打开“纯数学研究工作室 4.0.0”。4.0 使用独立的软件包、菜单入口、个人安装目录、配置和默认工作区，不自动接管已有研究。默认工作区是 `$XDG_DATA_HOME/pure-math-research-studio/4.0/workspace`（未设置 XDG 时位于用户的 `.local/share`），配置位于 `$XDG_CONFIG_HOME/pure-math-research-studio/4.0`（默认 `.config`）。安装目录与工作区分开。

如果 `.desktop` 文件打开成文本，请使用 `.deb` 和应用菜单入口。普通使用不需要编辑启动器。已有安装目录和同版本菜单入口不会被覆盖；同版本菜单已存在时安装会明确拒绝。关闭浏览器不会终止后台研究；重新点击应用入口可重开同一工作区。需要停止后台时先暂停研究，再使用页面底部的退出按钮。

在“设置与登录”中选择已有 Codex CLI、Tectonic、离线资源或公共 CA 文件，或明确安装所列官方组件。登录由官方客户端处理，不把密码或令牌粘贴到项目中。缺少 PDF 组件不阻止普通知识阅读和不依赖 PDF 的研究；依赖检测不等于实际报告渲染通过。

## 功能与使用

1. “新建项目”选择 TRW，输入精确题目及假设；选择 TFDW 时分别填写现象、不变背景和探索范围。支持保存原始 UTF-8 材料。创建暂停项目不调用模型。
2. “开始本轮研究”明确目的、调用上限和并发数，查看阶段、角色和用途的模型与推理强度策略。策略编辑只影响未来任务，单项覆盖或恢复默认不覆盖其他作用域，既有冻结任务保留原配置。能力不支持时明确拒绝，不静默降级。
3. 同一项目可以创建多个具名流程实例。完整 TRW P0–P14、TFDW D0–D5 图默认突出当前流程和主路径；选中阶段打开详细职责、策略、任务及产物，分支和回流按需显示。双图总览与全部路径仍可查看。阶段活动不是证明完成百分比；未选择对应实例的图只展示结构和未知状态。
4. “当前知识”“原始材料”“开放问题”“研究历史”“任务与配置”提供当前原生项目的正文与日志。历史来自本项目的不可变提交和事件。后台轮询自动补上新任务、状态和可用操作，保留正在阅读的正文快照和展开状态。切换项目或实例会清除不适用的阶段详情和筛选。
5. 暂停保留在途请求和已捕获结果。“接纳已捕获结果”读取原响应，不重新发送。UNKNOWN 可放弃等待但保留消耗；确认未发送必须选择实际传输证据原件并明确绑定原请求，说明文字本身不是证据。
6. 提交响应丢失时查询原操作。未确认结果持久保存在工作区，重启或换端口后仍可发现；完成结果直接恢复，PENDING 不自动重发，失败先查看并明确确认。明确的新操作使用新编号，同样输入仍可再次执行。
7. 候选比较和采用按精确候选与范围交接，创建新的暂停流程，不自动授予证明资格。研究报告包含讲义版和精简版，分别记录语义检查与实际页面检查；报告失败不会自动阻止其他获授权的研究决定。
8. “导出备份”保存本项目的原生归档。“恢复原生备份”先检查，再恢复到新的独立项目。恢复保留原生知识、材料、日志和捕获，暂停流程，不自动恢复旧任务执行。不符合当前原生合同的输入会明确拒绝，不转换或修改原件。

无模型调用的输入输出例子：新建 TRW，项目名 `Arithmetic example`，题目 `For every integer $n$, $n + 0 = n$.`。创建后的预期结果是一个暂停实例，原文保留为材料和目标，调用次数为 0；它不会因为被保存就获得证明资格。首页模拟示例使用独立合成项目，不是真实研究结论。

## 范围与边界

本版保留当前原生存储结构和安全的原生备份恢复。内部格式标识独立于产品版本；保留存储标识不表示承诺旧版兼容。本版没有旧格式导入、升级或转换命令，不包含历史源码、具体研究原件或续接包。退役要求和保留验收范围见[4.0 验收范围](ACCEPTANCE-SCOPE-4.0.0.md)。

原始材料、保存成功、任务完成、报告输出都不等于数学证明。支持与资格按精确对象、版本和检查范围记录；本版不提供形式化验证。费用及客户端未返回的有效配置或用量保持未知。付费研究只会在用户明确授权后启动；开发验收使用可控模拟。

## 高级维护与开发

普通操作可在网页完成。高级 CLI 共享同一服务层：

```bash
python3 -m research_studio --help
python3 -m research_studio project init --problem examples/problem.zh-CN.md --out ../new-project
python3 -m research_studio status ../new-project
python3 -m research_studio audit ../new-project
python3 -m research_studio project restore BACKUP.zip --out ../restored-project
```

在已验证解包的 release ZIP 目录中进行离线前缀安装：`python3 scripts/install-local.py --prefix NEW_PREFIX --bin-dir NEW_BIN --venv`。使用新目录；需要应用菜单时传入 `--desktop-dir`。维护验收使用独立的私有菜单目录，不覆盖已有同版本菜单。测试与构建产物放在源码树外：

```bash
python3 -B scripts/test-runner.py --out ../validation/suite.json
python3 -B scripts/validate-groups.py --out ../validation/required --browser-evidence ../validation/browser-evidence.json
SOURCE_DATE_EPOCH=315532800 python3 -B scripts/build-release.py --out ../artifacts
```

验收必须使用本版本实际执行的记录，不能复用旧版本 PASS。构建输出源码 ZIP、安装用 release ZIP、wheel、图形安装器 `.deb`、制品清单与哈希；构建成功只确认打包完整性。

更多：[架构](ARCHITECTURE-4.0.0.md)、[更新说明](CHANGELOG-4.0.0.md)、[Ubuntu 安装与验收](UBUNTU-E2E-GUIDE.md)、[许可证](LICENSE)。
