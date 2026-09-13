已最小修正并停止写入，等待 root 验收。

- **失效结论**：CLOSURE.md 的“缺少入口检查”和“merge 可排除”均不成立。原代码在 prepare 将时间从 10 推进至过期边界 20 后，两个入口都返回 `True` 并追加输出。
- **原因与方法变化**：入口检查不能证明最终发布资格。现在冻结入口 `owner_id/token/acquired_at`，在 prepare 返回后重新检查身份、scope 和当前到期时间；资格字段被删除也拒绝。
- **影响范围**：[publisher.py](/Users/devon/claude/sol-advisor-v072-evidence-20260913/evaluations/iteration-1/eval-closure/with_skill/outputs/project/publisher.py) 的 publish、merge 及两个私有 helper；新增 [test_publisher.py](/Users/devon/claude/sol-advisor-v072-evidence-20260913/evaluations/iteration-1/eval-closure/with_skill/outputs/project/test_publisher.py)。公开签名和正常输出保持原样。
- **排除范围**：CONTRACT.md、CLOSURE.md 未编辑；没有访问其他案例、父仓库、记忆、隐藏测试或其他安装技能，没有网络、spawn、配置或 Git 操作。

实际验证命令（项目目录内）：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_publisher.py
```

结果：6 个测试、28 个场景全部通过，涵盖两个入口的过期边界、身份/scope 变化、资格字段删除、到期时间缩短、入口已过期以及正常输出；同时验证 owner 保留 prepare 所作修改，拒绝时原 output 保持不变。

另执行独立探针：`now()` 依次返回 10、21，prepare 原样返回值；publish 和 merge 均得到 `False`、`['prior']`。验证前后四个输入文件摘要一致。

最终 SHA256：

```text
publisher.py      817264108585d987da0b8dcfbf8bd45becc60829c10cb981a66c96629fbb4277
test_publisher.py b0c7fcb49c1d873879aa89410e8cd063836352021366812a3b0e64070e110096
```

**未验证**：真实并发线程、自定义带副作用的 mapping/clock/output；当前结论限于该同步内存夹具。首次 Python 复现可能生成本地 `__pycache__`，未清理。

**过程偏差**：首次读取技能时同批执行了项目 `rg --files`，早于 SELECTIVE ROUTE 声明，违反技能声明前置要求；后续任务操作均在 solo 声明之后。
