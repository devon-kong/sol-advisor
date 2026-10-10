# Sol Advisor：Codex Cloud 安装与使用手册

核对日期：2026-10-10。适用于账号级个人插件与支持通用子 Agent 调度的云任务。

## 1. 先确认你拿到的是哪一版

**使用 `cloud-full` 的前提是取得已适配的插件包。** 本仓库当前原版为 `0.10.0`；本次文档修改前的 `main` 为 `ad2722705b6f427fdff19672b6ad3b8236ea7bc7`，原生代码基线仍为 `6c5b9d8a425ea6581cc4299c965cda26a21e03b8`。个人云适配沿用协议 `SA-CLOUD-FULL-1`：`0.10.1` 已完成一次云端 fixture 验收，本文修正后的 Reviewer 续审规则适用于已发布的个人插件 `0.10.2`；独立云端烟测已验证同一最后 Reviewer 对新候选两次续审通过，证据限制与程序偏差见第 6 节。个人插件的安装与升级不会自动更新 GitHub 源码、本地克隆或原版角色配置。

`0.10.1` 的旧云规则曾把两个 Reviewer 身份与最多一次审核后修复绑定，并禁止最后 Reviewer 对新候选续审。本文撤销这项云端特有限制：**`max_reviewers` 是每阶段最多新建的 Reviewer 身份数，不是修复轮数。** 原生 `0.10.0` 已采用身份预算耗尽后续接最后 Reviewer 的策略，本次只改文档，不改原生代码。旧任务需要明确迁移并重新绑定当前候选，不能因本文更新就视为已迁移。

| 内容 | 本仓库原版 | 单独的个人云适配包 |
|---|---|---|
| Skill | 原生 `solo / delegate / audit / full` 路由 | 增加宿主选择与 `cloud-full` 指引 |
| Agent 调度 | 指定原生 `agent_type`，使用已安装的 TOML 角色 | 通用 spawn，显式指定模型和推理等级；新身份用 fresh 上下文，预算耗尽后续接最后 Reviewer |
| Reviewer | TOML 请求只读，仍需观察实际权限 | 共享文件系统中的行为只读，无逐 Agent 强隔离保证 |
| 适配说明 | 没有 `cloud-adapter.md` | Skill 必须链接 `references/cloud-adapter.md` |

本仓库未包含云适配代码，也未提供该适配包的公开下载地址。**直接 clone `main`、下载本仓库 ZIP，或只安装原版插件，都不能得到账号中单独维护的适配。** 请先从有权提供该包的维护者取得适配包；尚未取得时，停在准备阶段，不要把原版 `full` 宣称为 `cloud-full`。

原版依据：[插件版本](../plugins/sol-advisor/.codex-plugin/plugin.json)、[Skill](../plugins/sol-advisor/skills/orchestration/SKILL.md)、[原生操作契约](../plugins/sol-advisor/skills/orchestration/references/operations.md)。本文只说明安装与使用，不替代适配包内的完整契约。

## 2. 准备与打包

需要能使用个人插件的账号、可运行目标项目的已发布云环境，以及允许创建子 Agent 的宿主。`cloud-full` 的 Implementer 和 Reviewer 都需要 `gpt-6.1-sol` / `high`；模型不可用时应报告阻塞，不静默换模型或降低等级。

账号级安装负责提供 Skill，项目云环境负责代码、依赖与工具。插件安装不会自动注册原版的用户 TOML 角色，也不会替你配置云项目环境。原版 companion installer 的用途见 [README 安装说明](../README.md#install-from-github) 和 [安装脚本](../plugins/sol-advisor/scripts/install-agents.sh)；不要将该本地角色安装流程当成云适配步骤。

如果已经取得完整归档，可直接进入下一节。如果取得的是已适配目录，先检查它是一个自包含的插件目录。以下是结构示意，不是本仓库可直接生成的云适配包：

```text
sol-advisor/
  plugin.json
  skills/
    orchestration/
      SKILL.md
      references/
        cloud-adapter.md
        ...其他被 Skill 引用的文件
  ...适配包要求的脚本与资源
```

便携格式的根 `plugin.json` 声明 Agent Plugins 1.0 schema、`name`、`version` 与 `description`；OpenAI 展示配置放在 `extensions.com.openai`。`skills/` 位于插件根目录，每个 `SKILL.md` 具有 YAML frontmatter 的 `name` 和 `description`。兼容布局 `.codex-plugin/plugin.json` 仍受支持；若适配包同时保留两种 manifest，应保持身份与版本一致，不要只重命名原版 manifest 就声称完成了云适配。格式依据：[官方插件打包文档](https://developers.openai.com/plugins/build/plugins)。

确认 `SKILL.md` 实际链接云适配说明，说明中定义 `SA-CLOUD-FULL-1`，并保留所有被引用的文件。核对适配的具体修订规则：`max_reviewers` 只限制身份数，预算耗尽后允许最后 Reviewer 续审新候选。按包的验证说明运行检查；仅有版本号 `0.10.2` 不足以证明适配存在或续审策略已生效。

将单个插件目录打包为 ZIP 或 tar.gz，归档放在该目录外，包含隐藏兼容文件。例如，在示例目录的父目录运行：

```sh
zip -r sol-advisor-cloud.zip sol-advisor
unzip -l sol-advisor-cloud.zip
```

包内应只有该插件及其必要文件，排除 `.git`、依赖目录、缓存、符号链接、凭据、会话记录与私人数据。整个 GitHub 仓库归档与独立插件包的根目录结构不同，不要混用。

## 3. 保存到账号并安装个人插件

这是个人插件安装，公开插件目录发布是另一项操作。

1. 在支持个人插件的 ChatGPT / Codex 界面，通过文件入口提供已核验的归档。
2. 使用 `@plugin-creator`，说明这是现有 Sol Advisor 的云适配包，请保存为账号的个人插件。首次保存用创建流程；已有同一插件时用更新流程，避免再创建同名副本。示例请求：

   ```text
   请将我提供的 Sol Advisor 云适配归档保存到当前账号的个人插件。
   若已有同一插件，请更新该插件；保留包内 cloud-full 契约，不公开发布。
   ```

3. 确认保存结果成功，并核对插件名称和版本。若当前界面缺少保存能力或权限，保留归档并报告安装待完成；上传了文件不等于插件已保存。
4. 打开 **Plugins → Personal**，查找 **Created by me / Created by you** 或 **Shared with me** 中相应插件；打开详情，用安装按钮完成安装。已保存的作者插件也应在 **Installed** 中确认可用。界面标签可能因客户端或语言不同而变化，以当前实际界面为准。
5. 在 **Installed** 中核对目标插件，并新建任务，让 Skill 重新发现。只有保存在本机的插件目录或 CLI 安装，不能据此断言另一云任务已获得该 Skill。

个人插件目录、安装与新会话的官方说明见 [Plugins](https://learn.chatgpt.com/docs/plugins)。技能包保存流程由当前可用的 Plugin Creator 提供；这里不提供任何私人插件 ID、账号详情链接或公开下载链接。

## 4. 新建云任务并验证发现

在网页或桌面端选择 **Work in → Cloud**，选择目标项目的已发布环境，然后创建新任务。环境必须能读取目标代码并运行验收所需工具；如果尚无环境，先完成环境准备与验证。官方入口与配置说明见 [Cloud environments](https://learn.chatgpt.com/docs/environments/cloud-environments)。

先进行一次只读发现检查：

```text
请确认当前任务可发现已安装的 Sol Advisor orchestration Skill。
只读取 Skill 及其链接指引，确认是否包含 references/cloud-adapter.md
和 SA-CLOUD-FULL-1，并确认 max_reviewers 限制身份数、预算耗尽后续接
最后 Reviewer；说明实际 spawn 与 follow-up 能力是否支持该策略；暂不改文件。
```

检查实际 Skill 内容与工具 schema，不只看插件名称。`cloud-full` 需要通用 spawn 支持 `task_name`、`message`、`fork_turns`、`model`、`reasoning_effort`，并有向同一 Agent 发送 follow-up 的能力，用于同一 Implementer 修正及预算耗尽后续接最后 Reviewer。如果工具接受原生 `agent_type` 且对应角色实际可用，应按原生契约选择宿主路径；产品名称中有“Cloud”不构成调度能力证明。

账号级个人插件已在一次新云任务中实测自动发现 Skill。安装、更新后的旧任务不能假定会热加载；发现结果仍须在新任务中确认。不要通过修改 `CODEX_HOME`、启动嵌套 CLI 或读取受限本地会话来绕过能力限制。

## 5. 触发 cloud-full 与执行顺序

在已确认适配可用的新云任务中，使用以下触发语，并补充目标、允许修改的文件、接口约束与验收要求：

```text
用 Sol Advisor cloud-full，让 Implementer 开发，再由独立 Reviewer 审核；每阶段最多两位 fresh Reviewer。
```

Root 应在任务工具之前声明 `mode: full`、`adapter: cloud-full`、协议 `SA-CLOUD-FULL-1` 及本次风险或显式多 Agent 请求，并确定阶段、文件所有权、验收标准与预算。

1. **Implementer 开发。** 新上下文使用 `gpt-6.1-sol`、`high`、`fork_turns: none`，接收完整规格，完成代码、测试和自审。交付后停止写入。
2. **冻结候选。** Root 记录真实交付、基础版本、完整候选与验收输入，确认文件所有权和证据完整；不要仅凭“已完成”接受结果。
3. **Reviewer 1 独立审核。** 新 Agent、新上下文，同样使用 `gpt-6.1-sol` / `high` / `fork_turns: none`，只读检查累计候选、相关消费者与验收证据，并独立挑战主要风险。
4. **有阻塞则交回同一 Implementer。** 由原开发者修正并验证，Root 冻结新候选；Reviewer 不自己改代码。修改后的内容不能沿用旧 verdict。
5. **有身份槽则新建下一位 fresh Reviewer。** 默认预算下创建 Reviewer 2，检查累计候选及继承问题。Reviewer 1 已完整通过时可直接进入接受，不必用完两个名额。
6. **用完身份槽后续接最后 Reviewer。** 默认是同一个 Reviewer 2：若它拒绝，仍由同一阶段 Implementer 修正并验证，Root 冻结新候选，再通过 follow-up 请 Reviewer 2 重新复审。每次都绑定新候选，保留全部历史问题、关闭证据与未审范围。这是 `same-context` 复审，不能称为 fresh，也不新建 Reviewer 3。
7. **Root 接受。** 只有当前候选获得 `REVIEW_STATUS: valid`、`VERDICT: ship`、完整覆盖且有效阻塞全部关闭，才能接受。发布、推送和业务操作仍受用户授权约束。

每阶段 `max_reviewers` 默认 2，可由用户明确指定其他正整数；它限制新建 Reviewer 身份数，不限制修复次数，也不要求用完身份槽。预算为 1 时，Reviewer 1 就是后续复审的最后 Reviewer；预算为 3 时，有剩余槽则依次创建 fresh Reviewer 2、3，用完后只续接 Reviewer 3。无效或不可用的新身份也消耗预算，不能借恢复、迁移或无效 review 自动增加身份。

预算耗尽不构成停止已授权修正和复审的理由，也不要求为每次正常修正重复确认。每次修改都会使旧 verdict 对新内容失效，但不会使最后 Reviewer 的身份失去复审资格。最后 Reviewer 必须检查继承阻塞、修正、相关消费者与剩余覆盖；不能复用旧 verdict，也不能改用更早的 Reviewer。如果最后 Reviewer 无法恢复，报告受影响阶段的阻碍，不能默默新建第三位或其他替代身份；扩展身份预算需要用户明确授权。

这一策略不取消权限、架构冲突和真实运行时限制。`rethink` 或超出授权的修正应交回 Root 处理；不能以继续修复为由扩大范围或绕过限制。重复失败的修复必须改变已失败的方法并寻求新证据，不能把同一无效尝试无限重跑。review 无效或证据不完整时，仍应保留可复现问题并恢复有效审核条件，不能将预算耗尽或续审本身视为通过。

## 6. 隔离与证据的实际边界

云适配是一套指令层编排契约，不是原生 `SA-FULL-V2-P2` / P3 验证器的替代实现。通用 spawn 没有原版的命名 `agent_type` 或逐 Agent sandbox 参数；不能把任务名当成已注册角色，不能给工具传入不支持的隔离参数。

Reviewer 与 Implementer 共享文件系统。Reviewer 的只读行为来自明确指令：不得编辑、新建、删除、格式化、安装、发布，也不得运行写入缓存或构建产物的命令。必要的写入型检查交给 Implementer 或已授权的隔离测试区域。每个审核窗口，包括最后 Reviewer 的每次续审，都应暂停候选写入，记录当前候选及相关证据在审核前后的状态；出现无法解释的变更、候选不匹配或无法比较时，该 review 无效。

**前后 hash 相同只能支持窗口状态一致，不能证明强隔离，也不能发现写入后恢复的短暂变更。** 如果验收要求强制只读隔离，当前云适配应停止在该阶段，等待宿主提供真实隔离。官方子 Agent 权限与原生配置说明见 [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)；实际可用控制仍以当前宿主为准。

保存真实 spawn 请求、成功回执和返回身份。显式配置被接受且宿主保证应用参数时，可记录为 `accepted-call-configuration`；这不是独立 runtime attestation。若公开运行时元数据可用，应比对；未暴露的字段标记为未观察，不用 Agent 自报补齐，也不伪造原生角色、沙箱或 P2/P3 回执。

2026-10-09 的 `0.10.1` 实际云端 fixture E2E 已记录：18 个单元测试通过；独立 Reviewer 执行 22,765 个穷举案例和 2,000 个随机案例；注入缺陷被发现、交回 Implementer 修复，并经 fresh Reviewer 复审；两个审核窗口的 hash 保持一致。这是历史单次云运行的验收记录，未验证预算耗尽后的 same-context 续审，不能作为 `0.10.2` 新规则的运行证明。本文未公开私人任务或原始记录，也未重新运行该历史 E2E。

2026-10-10，个人插件 `0.10.2` 已成功发布，10 个变更文件逐字回读一致。云契约检查 8 项、原生 review-round 检查 18 项通过；全量测试 245 项中 242 项通过，另有 3 项与旧基线相同的环境或包缺件错误，没有新增失败。这些是发布回读和静态 / 回归检查结果，不是全量通过，也不能单独证明实际云 Agent 续审。

同日，独立云端动态烟测通过，账号工具直接确认当前版本为 `0.10.2`。真实候选序列为：

| 候选 | 审核上下文 | 结果与后续动作 |
|---|---|---|
| C1 | Reviewer 1，fresh | 拒绝零值漏洞，交回同一 Implementer 修复。 |
| C2 | Reviewer 2，fresh | 拒绝 Unicode 数字漏洞，再交回同一 Implementer 修复。 |
| C3 | 精确同一 Reviewer 2，`followup_task` 续接，same-context | 对修正后的新候选复审通过。 |
| C4 | 同一 Reviewer 2 第二次续接，same-context | 对等价重构后的新候选再次复审通过。 |

全程只有两位 Reviewer，没有 Reviewer 3；四轮候选及证据窗口稳定。该烟测验证了身份预算耗尽后的连续复审路径；Reviewer 1 提前通过、最后 Reviewer 不可恢复的分支仅静态验证。模型证据仍是 `accepted-call-configuration`，只读仍是行为约束，不是独立运行时证明或强制沙箱隔离。记录还包含 Root 过早枚举工具名称、Reviewer 2 误枚举工作区文件名两项程序偏差，未产生业务修改；因此不能声称全会话所有步骤都完美遵循程序。本文只汇总运行结果，不公开私人身份、账号或任务链接。

## 7. 故障排查与更新

| 现象 | 检查与处理 |
|---|---|
| Personal 中没有插件 | 确认归档已成功保存到当前账号 / 工作区，区分个人目录与仅本地目录；不要重复创建未知状态的同名插件。 |
| 新任务找不到 Skill | 在 Installed 核对安装状态，确认账号 / 工作区正确，再建新云任务；检查 manifest、Skill frontmatter 与目录布局。 |
| Skill 仍要求原生 TOML 或找不到适配说明 | 很可能安装了原版或旧包；检查实际 Skill 是否链接 `cloud-adapter.md`。没有适配包时报告缺前提，不冒充 cloud-full。 |
| 模型或调度能力不可用 | 查看实际 spawn schema 和模型访问；报告受影响阶段阻塞，不换模型、不降等级、不绕过权限。 |
| Reviewer 写入文件或候选变化 | 使该 review 无效，保留可复现问题，恢复稳定候选及有效审核条件；有剩余身份槽则新建下一位 fresh Reviewer，用完则续接最后 Reviewer 并绑定当前候选。无法恢复条件时报告阻碍。 |
| 第二位 Reviewer 仍有阻塞 | 交回同一阶段 Implementer 修正和验证，冻结新候选，再续接同一个 Reviewer 2 作 same-context 复审，保留全部历史问题；不自动新建 Reviewer 3。 |
| 最后 Reviewer 无法恢复 | 报告受影响阶段阻碍；不能复用旧 verdict，不能默默换回更早 Reviewer 或新建替代身份。 |
| 临时证据丢失 | 重建必要证据并重新审核；临时目录不能保证跨任务持久恢复。需要持久证据时提前指定经授权的存储位置。 |

更新云版时，取得新适配包，核对版本、Skill 链接、协议和原生文件保留情况；通过 Plugin Creator 的更新流程更新同一账号插件，并确认 Installed 后再创建新云任务。先做发现检查，再用小型无私人数据的 fixture 验证真实开发、审核、修正与接受流程。回滚也应重新确认安装版本并新建任务。

**既有任务迁移：** 插件升级或文档更新不会自动热更新运行中的任务，也不会自动改变冻结的旧策略。继续旧任务前，应明确选择迁移到 `0.10.2` 的身份预算与最后 Reviewer 续审规则，读取实际更新后的适配指引，创建新的策略记录并引用原记录；保留旧候选、历史 review、问题与证据，不改写旧规则或把旧结果追认为新策略验收。统计本阶段已消耗的 Reviewer 身份及预算，保留最后 Reviewer 的实际身份；迁移不清零身份计数。重新冻结并绑定当前完整候选、验收输入和累计问题，再按剩余身份槽或最后 Reviewer 续接规则取得新的候选绑定审核结果。

若当前旧任务读不到新适配、缺少必要证据或无法恢复最后 Reviewer，报告迁移阻碍，不承诺原地续接。新建任务时也须明确携带旧任务历史及身份预算；无法恢复既有 Reviewer 的上下文时，不能仅靠换任务声称获得 same-context 复审，需由用户决定新的预算或阶段安排。`0.10.2` 的实际验证应覆盖 Reviewer 2 拒绝后的同一 Implementer 修正、同一 Reviewer 2 续审及新候选绑定，而不只覆盖首次 fresh review。

README 中的 `codex plugin marketplace upgrade sol-advisor` 更新原版 marketplace，不会自动更新单独的账号云适配包。反过来，个人包升级不会修改 GitHub `main`。更新记录应分别记载源码基线、适配包版本与宿主验证结果。
