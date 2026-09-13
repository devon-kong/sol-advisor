已完成最小修正并停止写入，等待 root 的后续授权。

- **改变的旧结论**：`CLOSURE.md` 的“原因是缺少入口到期检查”“merge 排除”“无未验证项”均不能成立。prepare 后到实际 append 前，两入口都缺少最终资格校验。
- **方法变化**：从仅测试入口状态，改为在 prepare 内推进时钟、改变身份/范围，并检查拒绝结果、已有输出及调用方状态。
- **修改范围**：[publisher.py](/Users/devon/claude/sol-advisor-v072-evidence-20260913/evaluations/iteration-2/eval-closure/with_skill/outputs/project/publisher.py) 保存入口身份，并在 prepare 后校验当前范围、到期时间和三项身份；新增 [test_publisher.py](/Users/devon/claude/sol-advisor-v072-evidence-20260913/evaluations/iteration-2/eval-closure/with_skill/outputs/project/test_publisher.py)。公开签名及有效输出保持。
- **实际验证**：在该 project 执行 `python3 -B -m unittest -v test_publisher`。修正前退出 1、12 个失败；修正后退出 0、6 个方法覆盖 18 个情形全部通过。另执行 Python heredoc，将 prepare 内 `expires_at` 缩至 1、时钟保持 2；publish/merge 均返回 False、保留 `['prior']` 和调用方变更。
- **稳定证据**：主测试前后 SHA-256 一致：publisher `a333e9be2378f6b3eb81af4a905ba2158c1b8f7eee49415c52d15e2aa478a6c1`；测试 `296a94ee44bcdc793824910414a1a705c82f81d399d4f5c356b4b78776f9cdab`。
- **影响与排除**：publish、merge 均确认受影响；入口预检查保留并验证。CONTRACT.md、CLOSURE.md 仅读取，未修改。project 外、真实插件、网络、全局配置及隐藏测试均未检查。
- **剩余不确定性**：未验证跨线程校验与 append 的原子性、可变身份对象或带副作用时钟；结论限定于同步内存 fixture。
- **执行偏差**：首次加载技能误同时执行了 `pwd && rg --files`，早于 route 声明；已明确报告。之后按声明的 solo 执行，无原生 spawn。
