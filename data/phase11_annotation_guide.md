# Phase 11 人工标注操作说明

标注文件由以下命令生成：

```powershell
Set-Location F:\lrz_workplace\Agent\Foundation\FoundationPal\api
F:\Anaconda\envs\fundagent\python.exe manage.py export_phase11_annotation_template --settings=app.settings.test
```

输出文件是 `F:\lrz_workplace\Agent\Foundation\FoundationPal\data\phase11_annotation_template.json`，共 165 条。请复制为 `phase11_frozen_eval_v1.json` 后再编辑，保留原模板作为审计底稿。

每条必须人工填写以下字段：

| 字段 | 允许值或填写规则 |
| --- | --- |
| `annotation_status` | 复核完成后填 `human_confirmed` |
| `domain` | `grant_rule`、`user_evidence` 或 `mixed` |
| `answer_state` | `answerable`、`no_applicable_rule` 或 `missing_evidence` |
| `requirement_ids` | 规则题或混合题可回答时填写当前数据库的 GrantRequirement ID |
| `user_evidence_ids` | 用户证据题或混合题可回答时填写当前数据库的 UserEvidence ID |
| `gold_chunk_ids` | 确认支撑答案的 AIChunk ID。无答案题保持空数组 |
| `annotation_notes` | 记录年份、项目类别、角色、数值或冲突等判定依据 |

判定规则：

1. 只问基金要求、资格、材料、格式、经费、提交规则时标 `grant_rule`。
2. 只问申请人论文、项目、角色、设备、实验、数值时标 `user_evidence`。
3. 同时需要规则和个人事实才能回答时标 `mixed`。
4. 当前规则包不适用时填 `no_applicable_rule`。
5. 没有可授权且可核验的用户事实时填 `missing_evidence`。
6. 不确定或资料不足时不要填 `human_confirmed`，在 `annotation_notes` 说明原因。

完成后运行校验：

```powershell
Set-Location F:\lrz_workplace\Agent\Foundation\FoundationPal\api
F:\Anaconda\envs\fundagent\python.exe manage.py validate_phase11_frozen_eval --dataset ..\data\phase11_frozen_eval_v1.json --settings=app.settings.test
```

校验成功才会输出 `phase11_frozen_eval_ready`。若失败，查看 `api\reports\phase11-frozen-validation.json` 中的 `rejections`，逐条修正后重跑。
