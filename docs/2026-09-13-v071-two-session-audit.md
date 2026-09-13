# Sol Advisor 0.7.1：两个真实会话的流程与收敛审计

审计日期：2026-09-13。结论：**部分优化已生效，不能认定旧问题已经解决。角色路由、独立主验、候选绑定和诚实停止基本生效；相关消费者遗漏及最终审核漏检仍然存在，而且已在原获 SHIP 的安装包上复现。**

## 1. 对象与证据边界

- [修复 W3 R1–R7 验收问题](codex://threads/01a099c7-9a96-7981-a250-5aa1c3d1b986)：7 个用户轮次，其中4批实际修复，用户明确指定 full。
- [检查 ego-gpt 与 GitHub 对齐](codex://threads/01a099d1-727b-7562-95d4-186604356027)：3个用户轮次，其中1轮明确指定 delegate 优化。
- 读取两个任务全部可见轮次、工具输出，并读取8个实际实施/审核子任务的记录。没有启动新的子 Agent，也没有向这些任务发送消息。
- 当前源码 HEAD 为 `41ad962`；安装缓存 `sol-advisor/sol-advisor/0.7.1` 全部14个文件与源码逐字节一致。两条任务实际读取的也是该版本。
- 依据当前 [SKILL.md](/Users/devon/claude/sol-advisor/plugins/sol-advisor/skills/orchestration/SKILL.md)、[operations.md](/Users/devon/claude/sol-advisor/plugins/sol-advisor/skills/orchestration/references/operations.md)、[role-contracts.md](/Users/devon/claude/sol-advisor/plugins/sol-advisor/skills/orchestration/references/role-contracts.md)，与[优化前复盘](/Users/devon/claude/sol-advisor/docs/2026-09-10-W1R-复盘与编排优化.md)对照。
- 区分原会话的真实执行、历史产物、此次独立复跑和当前工作区。没有重新认证当前 W3，也没有把其他 Agent 的报告直接当作验收结果。

## 2. 最重要的发现：正确绑定的 SHIP 仍漏掉同类风险

W3 原最终 fresh Reviewer `01a09ab3-5a37-7262-ba2d-5bdb907e0c49` 确实返回 `ship`，候选为：

`sha256:78b120c1f6b7db66bbafec48c575b89fd2fad9725b803b628cd316d593511f84`

根侧全量532/532、源码50/50、安装86/86、旧关键反例两边各41/41均有实际输出。源码50是44+补跑5+原停止反例1，安装86是80+补跑5+1；没有把它们伪装成单次运行。原审前、审后及最终 expected-ID 均MATCH，Reviewer返回ID相同。

但是，后续独立报告指出仍有风险。本次没有止于转述：先核对原包 SHA256，再比对原包与被测试安装目录的61个打包文件，全部相同；随后亲自运行冻结安装目录的27项新边界测试，结果为 **10 pass / 17 fail / 0 cancelled / 0 skipped / 0 todo，exit 1**。网络守卫12次注入，真实网络调用0。

- 原包 SHA256：`d4d951b653c0a46b76d427b5aaeba9690f96214ac5a4d4330ebaae6b599c3a60`。
- [本次复跑命令、包身份及计数](/Users/devon/claude/sol-advisor/scratch/session-audit-20260913/frozen-package-recheck.json)
- [本次实际失败输出](/Users/devon/claude/sol-advisor/scratch/session-audit-20260913/frozen-package-counterexamples.txt)
- [被复跑的安装入口测试](/Users/devon/claude/12306-http-api-mvp/scratch/w3-independent-depth-final-20260913/installed-new-boundaries-complete.test.mjs)

有代表性的同类遗漏：

| 机制 | 原最终候选仍存在的行为 | 与旧问题的关系 |
| --- | --- | --- |
| canonical发布资格 | 最后一次异步读取期间owner/activity失效，仍提交新revision | 把检查窗口从一个await挪到另一个await，未在实际发布边界整体证明资格 |
| owner身份 | owner结束按完整身份处理，send/health却仍接受部分身份相同的记录 | 同一资格在多个消费者中定义不一致 |
| 必要刷新期限 | 已过期，但成功回执先于下一tick到达时仍放行 | 只测“先观察超时再到达回执”，没有检查等价事件顺序 |
| 相邻健康消费者 | setup错误scope、旧revision、未来回执仍可SETUP_OK | 因果影响面大于原修改白名单，需要记录排除或另行纳入，不能从局部绿测推导全覆盖 |

17是失败场景数，不是17个独立bug，也不能全叫修复新增回归。setup原先不在生产白名单，不能据此要求当时偷偷修改；即使排除setup，R1 send/health/canonical等授权范围内仍有明确失败，足以证明消费者收敛没有完成。本次没有复跑后续报告追加的第18个场景。

**判定：候选身份机制有效，语义验收仍有逃逸。不能因为hash正确就把fresh ship当作完整性质已证明。**

## 3. W3 full：主干符合，但四批修复仍呈现逐点追补

| 修复批次 | 根侧全量 | 当批结束状态 | 主要未闭合点 |
| --- | --- | --- | --- |
| 初始R1–R7 | 497/498 | PARTIAL/BLOCKED、fix-first | 旧owner覆盖新owner status |
| 用户授权续修status | 502/502 | PARTIAL/BLOCKED、fix-first | 续租fsync跨旧期限仍恢复资格 |
| 用户授权续修expiry | 511/511 | PARTIAL/BLOCKED、fix-first | owner释放UNKNOWN仍返回已停止 |
| 用户授权续修owner-end | 532/532 | scoped ship | 当时列举反例通过；此次原包复跑仍揭示相邻遗漏 |

共2个Terra实施线程（前一个复用多批）、5个fresh Sol审核线程，顺序执行；正式返回4次fix-first、1次ship。其中status批补充真实反例后绑定新候选、再做负面终审，保留同一finding，并非换Reviewer消掉问题。

各批使用用户要求的3轮上限，前三批诚实停止，随后用户明确要求继续才恢复。**不能把4批合计直接指控为擅自突破三轮限制。** 四个修复turn时长合计约209分钟，只是本任务时间记录，没有可比旧版对照，不能据此宣称省时或更慢。

符合预期的行为：

- 实际Terra为`gpt-5.6-terra/high`、Reviewer为`gpt-5.6-sol/high`；spawn使用精确角色、`fork_turns:none`，无模型覆盖。所选阶段有preflight及精确线程runtime核查，没有无关主模型setup门。
- root编写独立反例、核对实际diff、全测和安装包；生产修复交回实施者，没有用root替代实施者完成同一生产修改。
- root确实找出实施者遗漏；Reviewer也独立发现过expiry问题。Reviewer读取累计生产diff，并非只接受实施者总结。
- 修正测试观测点、夹具和错误预期时说明了依据，保留红证据；没有把全量通过覆盖掉有效失败。
- 接受基准、impact surface、closure/resume和外部证据都存在。第四批明确记录activity原先被错误排除，再用真实反例推翻排除，说明新规则有实际作用。

仍不满足优化目标的部分：

- 第一批已发现R2“最终异步读取后资格变化”，但其他publish/send/consumer的等价窗口没有同步形成充分证据；status→renew→finally→activity→重复刷新继续逐点发现。
- 第四批[impact-surface](/Users/devon/claude/12306-http-api-mvp/scratch/w3-owner-end-closure-20260913-root/impact-surface.md:8)先把共享activity视作保留/排除，随后动态反例推翻。这是一次正确纠偏，同时说明最初排除尚不足以支撑收敛结论。
- 对照SKILL第121–132行，不能说“完全没做扫描或没改变方法”；准确结论是**做了，但因果清单与证明不足，未稳定达成同类缺陷系统收口**。
- 最后Reviewer明确没有重跑测试，主要查diff、既有日志和11728项候选输入。当前规则不强制Reviewer另写测试，因此“未跑测试”本身不是违规；实际漏检表明高风险终审的行为挑战要求仍偏弱。

## 4. ego-gpt delegate：角色分工正确，但发生了验收与编辑冲突

本轮只有1个Terra线程 `01a099d5-8fd8-7de2-b496-ac90bb6d7af7`，没有额外Reviewer；符合delegate，而不是“少做一道full步骤”。root负责真实浏览器和独立测试，Terra负责wrapper/Skill/契约文件。

root独立抓到多行输入丢失、request_id前缀碰撞、slider属性读取错误、动态网页脚本转义错误；将模型/档位不可用、身份歧义和迟到副作用纳入验证。真实生成使用GPT-5.5/High，Latest及各Pro只保留通用兼容、未作生成实测；最终报告没有夸大token或时延收益。当前wrapper SHA256仍等于报告最终值。

**明确执行缺陷：验收时被执行的Bash仍可被实施者改写。** T3浏览器执行成功后，Terra原位改了运行中的Shell，导致exit127和`n_output_tmp): command not found`。root事后冻结编辑、恢复原始结果、确认发送后没有重发，另用T4补正常验收。这是成功恢复，不是可以忽略的编排错误。

证据：[验收报告第85–89行](/Users/devon/claude/ego-gpt/evals/260913-browser-v2-report.md:85)。职责应同时落在root的验证阶段协调与实施者的交接冻结上。即使delegate不需要正式candidate manifest，也应有“停止编辑→验证稳定字节→如再修改则相关结果失效”的规则。

## 5. 明确流程偏差与应避免的误判

| 项目 | 判定 | 依据及后果 |
| --- | --- | --- |
| 首次工具前声明路由 | 两条首次调用均不符合字面要求 | W3先读skill、memory、git/规范后声明；ego-gpt先读skill和git/AGENTS后声明。即便豁免加载skill，仍有任务工具在声明前；SKILL第23–34行没有该豁免。属于低严重度顺序偏差，不是生产安全事故 |
| inspector输入类型 | ego-gpt发生一次已恢复误用 | 先传`/root/browser_v2_implementation`被拒，后用精确UUID核验成功，没有据失败结果放行 |
| 验收文件选择 | W3有已补救的证据缺口 | 全局字符串替换把root-r1测试名变成root-r3，导致5个必需文件未执行；root发现后按真实文件名在源码和安装各补5项，正式结论前已闭合。说明exit0/skip0本身不能证明必需场景全跑 |
| 固定报告字段 | 部分返回只在语义上提供内容 | 多个IMPLEMENTATION REPORT未逐项提供IMPACT SURFACE/EVIDENCE MAP/JUDGMENT CALLS/GAPS；部分Reviewer也用自然语言代替固定finding字段。与role-contracts格式有偏差，不应等同于所有证据缺失 |
| reviewer只读 | 宿主未强制只读，原报告已披露 | 实际danger-full-access/disabled；命令记录未见Reviewer文件修改，root保留候选前后对比。属于当前operations允许的行为只读路径，不可称强隔离；candidate一致性也不是全部瞬态行为证明 |
| catalog最小外扩 | 不能简单判为越权 | 用户要求名单外文件先记录原因和最小方案，没有明确要求再次批准；原任务先多加了批准门，后在改前记录解释并纠正。属于不必要中断及恢复，不应要求插件今后一律多问一次 |
| 三轮后继续 | 有后续用户授权 | 多批恢复不是自动开第四轮；需要保留每批与累计信息以免读者混淆 |

初始委派prompt在子任务UI中未完整呈现为用户消息，不能仅凭该接口逐字证明所有prompt模板字段齐全；角色、实际执行、返回报告和对应接受文档已核对。

## 6. 优化前的问题是否解决

| 旧问题 | 本次判定 |
| --- | --- |
| 不必要主模型/全角色配置检查 | 这两个样本中已改善，未造成该类阻塞 |
| 多Agent重复实现、普通任务强加终审 | 样本符合预期；delegate没有Reviewer，full按需审核 |
| 只信实施者自测、mock掩盖真实接线 | 明显改善；root真实链/独立反例/新安装包证据有效 |
| 修改后复用旧ship | 原会话中未见；expected-ID和fresh候选重新审查实际生效 |
| 全测绿就完成、到上限假报通过 | 明显改善；前三批保留PARTIAL/BLOCKED |
| 同类遗漏和反复局部补丁 | **未解决**；四批内反复发生，原ship包仍有动态失败 |
| Reviewer发现剩余高风险边界 | 有收益但不充分；一次独立发现expiry，最终仍漏掉同类消费者 |
| 节省token和时间 | 未验证；这两个样本没有旧新配对成本数据 |

## 7. 下一版最小修改建议（本次未实施）

1. **所有模式加验证冻结交接。** 在SKILL/operations中要求实施者明确停止写入；root记录被测文件/包身份；并行准备反例可以继续，正式验收必须针对稳定副本或稳定字节。再次修改作废受影响证据。无需给delegate强加Reviewer或整套manifest。
2. **同类失败后检查“接口×资格×事件顺序”。** 在convergence中补一个小示例：claim/renew/send/commit/health/status/release/consumer分别检查身份字段、最后await、时间、错误返回、相邻正例。排除项要有证据，不能只写“保留旧契约”。第二次同类失败时root必须先完成这一诊断，再发修复任务。
3. **高风险Reviewer提供新的行为挑战或明确等价推导。** 保留当前三角色与四路由，不默认新增Tester；允许只读/内存探针，需真实落盘的复现实验交回root。在结论中区分独立证明与核读现有日志。
4. **验收入口核对必需场景清单。** 检查文件存在、实际执行的test名称/数量与必需清单一致；不要只依赖exit0/skip0。用本次5个缺失文件作为小型回归fixture。
5. **让流程约束可检查且不增加仪式负担。** 明确skill加载是否豁免首次声明；spawn前固定有效UUID获取方式；缺失报告字段显式写none/unverified；不因补齐格式自动重复业务全测。

应保留candidate工具，它解决身份问题；不应靠多加hash、更多Reviewer或更严格固定轮数来代替因果诊断。11728项候选包含大量历史/证据文件，后续可改善输入组织，但不能为了减量偷偷排除影响结论的材料。

## 8. 当前状态与本次改动

当前工作区再次验证旧W3候选返回`changed`，含生产文件变化：[此次检查](/Users/devon/claude/sol-advisor/scratch/session-audit-20260913/current-candidate-check.json)。这证明旧ship不能接受现在的工作区，不证明变化发生在原Reviewer执行期间。上面的17个失败是在哈希已确认的历史包上复现，所以不受当前续修影响。

本次只新增本报告与`scratch/session-audit-20260913`的审计输出；保留原有未跟踪安装准入报告。未改插件、业务生产代码、原测试或历史验收材料，未commit/push；未进行真实浏览器生成、12306请求或线上诊断。没有宣称当前W3已修复或重新签收。
