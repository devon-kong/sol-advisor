REVIEWED_CANDIDATE: sha256:8c1116c6ea5a349a3fe5c38d71afccfaa134ed2034d42dee8156b291e55cd99f
VERDICT: fix-first
REASON: 已复现准备期间授权过期后仍发布；必需测试文件缺失，2 项通过不能证明完整验收。

FINDINGS:

- FINDING: REVIEW-001
  CLASS: implementation
  REQUIREMENT: ACCEPTANCE.md:2-3，授权必须在实际 append 时仍有效，包括 prepare 耗时。
  IMPACT: 过期授权仍写入 output，并返回 True。
  EVIDENCE: publisher.py:2 只在 prepare 前检查；第 4-5 行准备后直接追加。只读内存挑战将时间从 90 推进到 101，expires_at=100，实际得到 True 和 `["x"]`；契约要求 False 和 `[]`。相邻有效路径返回 True、初始过期路径返回 False。
  RELATED SURFACE: publisher.py 的 publish；候选中唯一直接消费者为 test_basic.py。
  OWNERSHIP: root
  REQUIRED NEXT ACTION: 保证追加时授权有效，验证准备期间过期的拒绝路径及相邻有效路径。

- FINDING: REVIEW-002
  CLASS: verification
  REQUIREMENT: ACCEPTANCE.md:4；REQUIRED.json:1 要求 test_basic.py、test_late.py，以及 expiry-during-prepare 场景。
  IMPACT: 必需场景未被现有测试覆盖，完整验收尚未成立。
  EVIDENCE: 实际文件及候选 manifest 均缺少 test_late.py；test_basic.py 仅覆盖 valid、expired。独立执行 `python3 -B -m unittest discover -p 'test_*.py'` 确认仅运行 2 项并通过。
  RELATED SURFACE: REQUIRED.json、test_basic.py、缺失的 test_late.py、ROOT-EVIDENCE.md。
  OWNERSHIP: root
  REQUIRED NEXT ACTION: 补齐契约要求的测试与场景，重跑并记录完整证据；纠正后重新绑定候选并取得 fresh review。

RESIDUAL RISK: 本次仅有离线内存行为证据；宿主未强制只读，审查全程未执行写入，前后状态一致性由 root 核验。
