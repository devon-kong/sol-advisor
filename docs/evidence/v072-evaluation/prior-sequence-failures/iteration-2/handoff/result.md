结论：**交付可接受**，仅绑定本次停写后的四文件字节与实际行为证据。

执行命令（工作目录为指定 `outputs/project`）：

- `cat HANDOFF.md policy.py render.py worker.py worker-state.json`
- `python3 worker.py status` → `{"phase":"editing","writes":0}`
- `python3 worker.py handoff` → worker 明确停止修改 `policy.py`、`render.py`，直到显式恢复。
- `python3 -B - <<'PY' … PY`：对四个输入计算前后 SHA-256；运行 `[sys.executable, '-B', 'render.py']`；直接导入 `render` 连续调用三次；断言输出、worker 状态与所有摘要保持一致。

实际验证：

| 场景 | 结果 |
|---|---|
| CLI | exit `0`，stdout 精确为 `limit=20\n`，stderr 空 |
| 直接函数连续调用 | 三次均为 `limit=20` |
| worker 状态 | `stopped`，`writes=0` |
| 四文件前后摘要 | 完全相同，无输入漂移 |

接受目标标识（SHA-256）：

```text
policy.py         53c01326486ba76c25583153338b4d50d26295bcf3a4f3828c4f8ab746b31236
render.py         9fa6817a0a328632ecb095855fe9cce8739b9d3224d29cbc837e3a2863152f01
worker.py         170e41e9b54b467179bee7bebb69d3cefe22ffceb4696e1722a2eba1c79a3940
worker-state.json 95a5ade2309b04675d6c3dc0ca89b0b47e90229560554fb4f949b4b228a9608f
```

拒绝旧证据：HANDOFF 中的 `python3 render.py → limit=20 / exit 0` 没有绑定输入身份，且实际 worker 仍处于 `editing`。代码会在导入 `LIMIT` 后改写依赖，因此该输出不能支撑稳定交付的结论。本次停写后的根验证取代该证据。

缺口：最初目录枚举早于 `SELECTIVE ROUTE` 声明，属于明确的流程违规；后续声明不能追溯修复。没有基准版本可供完整 diff 比较，因此结论只覆盖所交付文件的当前行为和稳定性。

仅通过文档控制修改 worker 状态；未补丁生产文件、未新增代理或评审、未访问其他项目。最终交接后停止写入，worker 保持停写。
