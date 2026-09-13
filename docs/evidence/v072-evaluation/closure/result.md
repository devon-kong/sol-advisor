已完成最小修正并停止编辑，等待 root 后续授权。

- **改变的结论**：CLOSURE.md 的“仅缺入口检查”“merge 已排除”“无未验证项”被反例推翻。修正前，两入口在 prepare 将时间从 1 推进至 6、期限为 5 后，仍返回 True 并追加结果。
- **原因与方法变化**：检查发生在 prepare 前，无法保证实际追加时权限仍有效。本次冻结入口身份，并在 prepare 后、append 前重新核验 scope、期限及 owner_id/token/acquired_at。
- **修改范围**：[publisher.py](/Users/devon/claude/sol-advisor-v072-evidence-20260913/evaluations/iteration-3/eval-closure/with_skill/outputs/project/publisher.py:4) 的 publish、merge 均确认受影响并修正；新增 [test_publisher.py](/Users/devon/claude/sol-advisor-v072-evidence-20260913/evaluations/iteration-3/eval-closure/with_skill/outputs/project/test_publisher.py:1)。公共签名和有效输出格式保持不变；拒绝保留 prepare 后的 caller-owned owner 和既有输出。CONTRACT.md、CLOSURE.md 未修改，项目外位置未检查或修改。
- **实际验证**：项目目录执行 `python3 -m unittest -v test_publisher.py`，7 个测试方法、20 个场景通过，涵盖两个入口的期限边界、各身份字段变化、scope/期限变化及有效路径。另用 `python3 -B - <<'PY'` 独立断言跨期与整套身份替换，即使新期限延至 100，也均返回 False，输出与 owner 保留；前后 SHA-256 相同。
- **已验证字节**：publisher.py `9dad91643a0e15b786563c56fe1065555a8b8674bc9bc0e6071269e86b3e6b3b`；test_publisher.py `0d7e83e07406a3dcc95a61df7ce6ae45129213b97f6335dc2d4c05a9da3e8c2a`。
- **未验证**：缺失必需字段、具有副作用的 now/append，以及真实并发原子性；本次证据限定于指定同步内存夹具。未启动代理、联网、使用浏览器或进行 Git 操作。
