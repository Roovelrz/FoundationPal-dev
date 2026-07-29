# Shared dual-RAG knowledge-domain contract.

from django.db.models import TextChoices


class KnowledgeDomain(TextChoices):
    GRANT_RULE = 'grant_rule', 'grant_rule'
    USER_EVIDENCE = 'user_evidence', 'user_evidence'


PENDING_CLASSIFICATION = 'pending_classification'


def is_knowledge_domain(value: str) -> bool:
    return value in KnowledgeDomain.values
