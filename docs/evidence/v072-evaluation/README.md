# 0.7.2可移植验证结果

本目录是本次离线源码行为评估和root运行的合成证据摘录。原始私有会话、
本机缓存、.git对象和pyc未导出；结果文本中的绝对路径保留运行来源。

- [W3原包17场景失败的无损输出](w3-frozen-package-counterexamples.json)：
  JSON解码恢复原始console字节，SHA256可验证；本机原txt保持原样。
- [五类结果](behavioral-summary.json)：routine/shared/handoff/closure/review；
  每个子目录含实际结果、分级、可读执行记录、被测项目和独立root检查。
- [最终19+5维护检查](verifier-after-uuid.txt)、[命令](checks-after-uuid.json)。
  19是既有candidate测试；5是原始缺陷夹具校准，非五类行为的自动评分。
- [UUID恢复与拒绝](uuid-recovery-refusal-probe.json)：两个实际unique恢复
  接原inspector，八个错误关联向量和一个实际path-as-UUID调用被拒。
- [metadata容器挑战](metadata-container-probe.json)：合法字段通过、内存坏结构拒绝。
- prior-sequence-failures保存两轮四次声明晚于工具的失败，没有被后续通过覆盖。
- initial-source-review-*保存首次真实源码fix-first、UUID关联依据与
  准确read-only前后状态；该verdict不能签收后来修改的候选。

新版description在评估中加载前可见，不代表实际安装缓存已升级。
最终源码main/role-contracts/convergence字节与第三轮一致；operations的
UUID恢复说明随后纠正并单独验证。首次坏UI形状在本地历史快照保留。

最终fresh终审状态将记录在[最终签收](FINAL-ACCEPTANCE.md)；本目录预先
冻结供终审，不能把目前链接视作已提前获得ship。发布后的commit/remote
核验另存本地externalfinal-acceptance，不改动被审输入去复用旧候选。

这些是5类、11个新上下文的前向检查，不是old/new性能对照；线程模型
启动被harness限制，副本控制代表delegate已实现阶段。成本、隐式触发、
端到端原生路由、安装采纳和真实业务仍未据此验证。
