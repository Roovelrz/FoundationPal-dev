# Phase 11 交付指南

## 一键启动与最小验证

在项目根目录启动完整服务：

```powershell
docker compose -f app-compose.yml up --build
```

在另一个终端运行最小后端验证：

```powershell
cd <项目根目录>\api
F:\Anaconda\envs\fundagent\python.exe manage.py test ai.tests.test_main_workflow_e2e ai.tests.test_proposal_graph ai.tests.test_observability --verbosity 1
F:\Anaconda\envs\fundagent\python.exe manage.py check
```

运行匿名自动评测并写入报告：

```powershell
F:\Anaconda\envs\fundagent\python.exe manage.py run_phase10_auto_eval --output-dir reports
Get-Content reports\phase10-auto-eval.md -Encoding utf8
```

## Reviewer 退回 Writer 失败案例

`ai.tests.test_proposal_graph.ProposalGraphTests.test_rewrite_routes_back_to_writer` 固定验证 Reviewer 返回 rewrite 后，执行顺序为 planner、writer:0、reviewer:0、writer:1、reviewer:1、human。它证明 Reviewer 不直接改写正文，而是把草稿退回 Writer。

复现命令：

```powershell
F:\Anaconda\envs\fundagent\python.exe manage.py test ai.tests.test_proposal_graph.ProposalGraphTests.test_rewrite_routes_back_to_writer --verbosity 1
```

## Checkpoint 恢复案例

`ai.tests.test_proposal_graph.ProposalGraphTests.test_finalize_only_runs_after_existing_human_approval` 固定验证已批准章节可通过 resume_after_approval 进入 finalize，而未批准草稿不能绕过审批。

复现命令：

```powershell
F:\Anaconda\envs\fundagent\python.exe manage.py test ai.tests.test_proposal_graph.ProposalGraphTests.test_finalize_only_runs_after_existing_human_approval --verbosity 1
```

## RAG 证据追溯案例

`ai.tests.test_run_timeline.RunTimelineTests.test_timeline_aggregates_observability_without_evidence_text` 验证 run_id 返回证据别名、排名、相似度、是否注入提示词及是否被模型引用，但绝不返回证据快照正文。

复现命令：

```powershell
F:\Anaconda\envs\fundagent\python.exe manage.py test ai.tests.test_run_timeline.RunTimelineTests.test_timeline_aggregates_observability_without_evidence_text --verbosity 1
```

## 实测指标表

来源：[Phase 10 自动报告](../api/reports/phase10-auto-eval.json)。范围为 3 个匿名冻结案例、9 次工作流运行和 DeepSeek 自动裁判。

| 指标 | 结果 |
| --- | ---: |
| Context Recall@3 | 0.6667 |
| 无答案正确率 | 0.3333 |
| Faithfulness | 0.6667 |
| 证据覆盖率 | 1.0000 |
| 工具调用成功率 | 1.0000 |
| 顺序工作流平均耗时 | 29.93ms |
| LangGraph 单工作流平均耗时 | 31.93ms |
| Multi Agent 平均耗时 | 36.41ms |

## 敏感资料隔离与权限边界

- 资料按 organization_id 和 proposal_id 过滤，跨工作区工具调用被拒绝。
- RAG 运行记录只保留 EvidenceUsage 元数据和快照引用；运行时间线不返回证据正文。
- AIJobContext 保存脱敏后的提示词快照，redaction_map 只保存类别而不保存原始值。
- 工具调用以 ToolInvocation 审计，包含调用角色、运行 ID、状态、错误码、延迟和幂等重试次数。
- 自动 Phase 10 评测只使用匿名固定案例，不读取真实申报书或本地证据正文。
- 真实模型调用前仅注入最少证据；生产使用时应将向量库与源文件保留在本地或受控内网。

## 演示结论

建议在面试中先展示 Phase 10 报告，再演示 Reviewer rewrite、Checkpoint 恢复和 RAG 证据追溯。所有结论都可从测试名、run_id 或报告文件复现。
