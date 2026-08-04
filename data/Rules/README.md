# 2026年三类基金项目规则包

本目录包含三套可用于基金申报Agent的规则包：

1. 国家自然科学基金青年科学基金项目C类
2. 2026年四川省自然科学基金
3. 2026年四川省高等教育高质量发展专项教学改革研究项目及西南民族大学补充层

## 目录结构

```text
grant_rule_packs_2026/
├── source_registry.json
├── rule_pack.schema.json
├── comparison_matrix.md
├── nsfc_youth_c_2026/
│   ├── pack.json
│   ├── README.md
│   └── source_documents/
├── sichuan_nsf_2026/
│   ├── pack.json
│   ├── README.md
│   └── source_documents/
└── swun_teaching_reform_2026/
    ├── pack.json
    ├── README.md
    ├── missing_source_request.json
    └── source_documents/
```

## 导入建议

- `pack.json` 进入规则数据库，拆分为Requirement、EligibilityRule、SectionSchema、RequiredMaterial和ValidationRule。
- `source_documents` 进入规则RAG索引，并以pack_id、year、issuer、project_type和authority_level作为元数据。
- `source_registry.json` 保存来源等级、原始网址和文件哈希。
- 组织内部通知以Overlay形式覆盖公共规则包，不直接修改公共包。
- 任何`unresolved_items`均应转为Grill Me或人工确认任务。

## 重要限制

公开网页无法替代申报系统中的实时模板和依托单位内部通知。正式使用前应执行一次版本确认，并要求用户上传系统导出的当年模板和本单位校内通知。
