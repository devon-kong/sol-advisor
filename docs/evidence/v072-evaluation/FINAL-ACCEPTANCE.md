# 最终签收口径与记录位置

本文件在源码fresh终审前冻结；不是提前签署ship。最终发布必须满足：

1. V072-RUNTIME-UUID-001已纠正并取得unique恢复/拒绝路径的实际证据。
2. 新候选在allowlist暂存之后绑定，root验证与不同freshReviewer指向同一ID。
3. Reviewer返回ship，完整仓库与材料的准确审前/后状态一致；宿主仍非强只读。
4. 原expected-ID在审前、审后、提交前及提交后仍支持同一字节/index身份。
5. 推送不用force，远端main SHA及全部allowlist文件与已审提交一致。

实际新fresh verdict、原reviewedcandidate ID和Reviewer线程ID写入**本次
0.7.2发布提交的commit body**（`git log --format=fuller`可查看），不会在
审核后修改这里的输入/重新暂存文件来复用旧verdict。原生返回、guard、
最终commit/remote核验另存本机外部证据目录
`/Users/devon/claude/sol-advisor-v072-evidence-20260913/`的final-acceptance.json。

本机安装被用户明确禁止，不能从GitHub发布推断本机缓存或角色已升级。
