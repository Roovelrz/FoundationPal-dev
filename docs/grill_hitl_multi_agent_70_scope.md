# Grill Me、HITL 与 Multi Agent 70 分收口清单

状态：实施前冻结  
范围：仅 Grill Me、HITL、Multi Agent 三个模块  
原则：复用现有 Django、React、LangGraph、Proposal.content.grill、HumanApprovalTask、WorkflowRun 和 ToolInvocation，不引入新依赖或新基础设施。

## 目标

本轮只交付一个可演示、可刷新、可审计、可人工接管的最小闭环：

补充规划信息 → 固定三角色受控协作 → 章节人工审批 → 既有定稿流程

70 分的含义是核心路径稳定可用、有定向测试证据、边界清楚。它不代表生产级自治、多智能体协商或服务重启恢复能力。

## TODO

### 1. Grill Me

- [x] 恢复已有 Grill 会话未确认时禁止直接规划的门禁。
  - 仅当项目已经开启 Grill 会话且尚未确认时拦截。
  - 从未开启 Grill 的项目仍可按当前流程规划。

- [x] 在现有项目工作区增加紧凑的补充规划信息入口。
  - 复用既有固定问题、跳过、完成、确认和刷新恢复能力。
  - 一次只展示一个问题，不增加追问、自由扩展问题或新模型调用。

- [x] 规划接口返回未确认状态时，前端回到该补充信息入口。

- [x] 仅验证并保留本地修改的现有边界。
  - 修改建议可生成。
  - 不自动覆盖章节草稿。

- [x] 补充定向回归。
  - 未确认时无法规划。
  - 回答或跳过并确认后可以规划。
  - 刷新页面后会话状态仍可恢复。

完成标准：用户能在不增加问题数量的前提下完成或跳过补充信息，并稳定进入规划。

### 2. Multi Agent

- [x] 固定为 Planner、Writer、Reviewer 三个角色和既有顺序。
  - 保留既有最多两次 Writer 改写上限。
  - 保留 Reviewer 只提出结论和退回意见，不直接改写正文。

- [x] 让 Writer 保存草稿、Reviewer 提交评审经过既有工具执行层。
  - 使用已有权限校验。
  - 生成已有 ToolInvocation 审计记录。
  - Planner 继续复用已有规划服务，不为其新增工具或能力。

- [x] 在 WorkflowRun 中保留角色交接与工具执行结果，供演示页面或接口读取。

- [x] 补充定向回归。
  - 正常路径存在 Planner → Writer → Reviewer 交接。
  - Writer 和 Reviewer 各有真实工具审计记录。
  - 角色调用未授权工具时被拒绝。

完成标准：这是固定三角色受控协作，不是动态 sub-agent 系统。

### 3. HITL

- [x] 只接入一个人工节点：章节审批。
  - 工作流到达审批点时创建或复用已有 HumanApprovalTask。
  - 保存关联的项目、章节、草稿摘要、评审摘要和流程标识。

- [x] 使用已有三个审批动作。
  - 通过：进入既有定稿和归档流程。
  - 退回修改：保留草稿，回到原有编辑入口。
  - 拒绝：结束本次审批，不锁定草稿。

- [x] 在现有页面增加一个待审批卡片。
  - 可查看当前任务。
  - 可通过、退回修改或拒绝。
  - 刷新页面后仍能继续处理同一待审批任务。

- [x] 补充定向回归。
  - 工作流暂停时只创建一个待审批任务。
  - 通过后章节锁定并完成。
  - 退回或拒绝后不锁定草稿。
  - 重复提交审批返回冲突。

完成标准：人工可以在刷新后继续处理审批任务，但不宣称进程重启后的 LangGraph checkpoint 恢复。

### 4. 最小验证与交付证据

- [x] 仅运行 Grill、Proposal Graph、HITL、Agent 边界、工具审计和相关前端交互的定向测试。
- [x] 修复本轮引入的失败，不以全仓库历史失败阻断交付。
- [x] 在本文件末尾填写实际通过的测试名称、日期和遗留项。

## 70 分停止线

| 模块 | 达到停止线的证据 |
| --- | --- |
| Grill Me | 未确认会拦截，确认后可规划，刷新可恢复 |
| Multi Agent | 三角色固定交接，关键动作有权限与工具审计 |
| HITL | 一个持久化审批任务，三个动作语义正确，可刷新继续处理 |

当三行证据均成立时，立即停止本轮开发，进入项目包装准备。

## DONT

- [ ] 不新增 Python 包、Node 包、模型提供商、数据库、消息队列、缓存服务、Docker 服务或环境变量。
- [ ] 不新增数据表、迁移或审批中心。已有 HumanApprovalTask 足够支撑本轮。
- [ ] 不配置 PostgreSQL checkpointer，不处理服务重启恢复，不宣称持久化 LangGraph checkpoint。
- [ ] 不做动态 sub-agent 创建、Agent 自由协商、Agent 间聊天、角色市场或自动扩容。
- [ ] 不修改 RAG、MCP、检索策略、评测体系、模型能力、权限模型或导出流程。
- [ ] 不让 Grill Me 对每个项目强制启动，不增加无限追问或自定义问题编排。
- [ ] 不让 Reviewer 直接覆盖草稿，不让人工退回修改自动改写正文。
- [ ] 不重做 Dashboard，不新增全局通知、审批列表、角色管理页或复杂可视化。
- [ ] 不因历史全量测试失败而扩展修复范围。
- [ ] 不修改本文件以外的规划文档或文档索引，除非用户明确要求同步。

## 预计改动边界

仅允许触及以下类型的现有文件：

- api/ai/views.py
- api/ai/proposal_graph.py
- 与上述流程直接相关的现有后端测试
- 一个现有前端工作区组件及其定向测试
- 本文档

若某项工作需要跳出此边界，先记录为遗留项，不在本轮扩展实现。

## 实施后填写

| 日期 | 通过的定向测试 | 遗留项 |
| --- | --- | --- |
| 2026-08-03 | Grill Me、HITL 与 Multi Agent：ai.tests.test_grill、ai.tests.test_proposal_graph、ai.tests.test_hitl、ai.tests.test_agent_boundaries、ai.tests.test_tools、ai.tests.test_run_timeline、workflow-bug-regressions、author-intent-and-revision、Django check、npm lint | 未实现动态 sub-agent、checkpoint 重启恢复及其他 DONT 项 |
| 2026-08-03 | 补充校验：Reviewer 退回意见进入 Writer 改写，主页面提交进入既有工作流并由审批卡片锁定章节。后端 28 项，前端 12 项，Django check 与 npm lint 通过。 | 未新增依赖、迁移、RAG、MCP、导出或动态 sub-agent。 |
