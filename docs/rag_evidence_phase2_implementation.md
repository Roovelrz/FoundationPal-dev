# RAG 与证据可追溯阶段 2 实施记录

实施日期：2026-07-24

## 本次范围

本次只完成文档与证据数据模型，以及可提取文本 PDF 的确定性预处理链路。未提前实现 Writer RAG 注入、Evidence API、前端证据面板、真实中文 Embedding、RAG Eval 或 E2E。

## 代码盘点与复用结论

复用了既有 AIResource、AIChunk、AIJob、WorkflowRun、AIJobContext、ingestion.py、retrieval.py 和 EmbeddingService。未新建平行资源库或向量数据库。

原有能力包括 Hash Embedding、资源与 Chunk 持久化、基础检索和 AIJobContext 检索元数据占位。原有能力缺少组织隔离、项目范围、解析版本、页码、稳定 Chunk 标识、文档删除策略和一次调用的证据快照。

## 已完成改动

1. AIResource 增加 organization_id、proposal_id、source_type、evidence_purpose、文件元信息、解析与 Embedding 元信息、页数、状态、错误码和软删除标记。
2. 同组织、相同 SHA256、相同 parser_version 建立唯一约束。内容变化将创建新资源版本，不会覆盖历史证据。
3. AIChunk 增加 stable_chunk_id、规范化文本及哈希、页码、标题路径、分块序号、Embedding 模型与维度。稳定标识由文件哈希、解析版本、分块序号和规范化文本生成。它不做全局唯一限制，以允许相同文件被不同组织隔离入库。
4. 新增 EvidenceUsage，保存一次模型调用中检索、注入和模型声明引用的证据状态，并保存文本、文档名、页码和标题快照。AIJob、Chunk、角色组合有唯一约束，避免重试重复创建。
5. 已引用 Chunk 使用保护性删除。含已引用 Chunk 的资源删除改为软删除。
6. 新增可提取文本 PDF 入库函数。链路执行 PDF 头检查、按页解析、规范化、按标题和句子边界的结构化分块、稳定 ID、Embedding 和资源持久化。
7. 分块初始规则采用待人工核验建议：目标 700 字符、最大 1000 字符、重叠 100 字符，优先段落和句子边界。
8. 扫描件返回 ocr_required，损坏或非 PDF 返回 pdf_parse_failed，空内容返回 empty_document。

## 关键取舍

旧实现的近似文本去重会把有轻微内容差异的文档复用为同一资源。该行为与文档更新必须创建新版本的证据追溯要求冲突，因此本阶段只保留文件 SHA256 与解析版本的幂等去重。

## 修改文件

- api/ai/models.py
- api/ai/migrations/0012_rag_evidence_models.py
- api/ai/ingestion.py
- api/ai/retrieval.py
- api/ai/admin.py
- api/ai/tests/test_ingestion_similarity_dedupe.py
- api/ai/tests/test_ingestion_retrieval_dedupe.py
- api/ai/tests/test_rag_evidence_models.py

## 验证记录

执行目录：项目根目录下的 api

执行命令：

    F:\Anaconda\envs\fundagent\python.exe manage.py makemigrations --check --dry-run ai
    F:\Anaconda\envs\fundagent\python.exe manage.py test ai.tests.test_ingestion_retrieval ai.tests.test_ingestion_retrieval_dedupe ai.tests.test_ingestion_similarity_dedupe ai.tests.test_rag_evidence_models --verbosity 1

结果：迁移检查无新增变更，9 项测试全部通过。测试环境同时报告 requests 与 urllib3 版本组合警告，未影响本次测试结果，后续依赖整理时应单独核验。

## 待人工核验与下一步前置条件

1. 提供并确认 3 至 5 份脱敏 PDF 的 source_type 与 evidence_purpose。
2. 抽检至少 30 个 Chunk，确认语义完整性、页码、标题、条款编号及金额和日期等关键内容。
3. 确认正式中文 Embedding 模型及固定版本。当前 Hash Embedding 仅保留给测试环境，未可作为正式运行路径。
4. 提供 10 至 20 个人工标注检索问题和 gold_chunk_ids，之后再实施 RetrievalService 与 RAG Eval。
5. 阶段 2 人工确认通过后，才进入 Writer 证据注入、EvidenceUsage 写入、接口和前端面板。
